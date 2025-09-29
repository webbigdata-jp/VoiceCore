import sounddevice as sd
import soundfile as sf
import requests
import numpy as np
import time
import os
import io
import json
import torch
from transformers import AutoTokenizer
from snac import SNAC
import queue
import threading

# --- 設定 ---
# 音声認識 (ASR)
ASR_MODEL_ID = "reazon-research/reazonspeech-k2-v2"

# 大規模言語モデル (LLM)
LLM_SERVER_URL = "http://127.0.0.1:8012/v1/chat/completions" # mitsuki

# テキスト読み上げ (TTS) 
TTS_SERVER_URL = "http://192.168.1.16:8000/v1/completions" 
TTS_TOKENIZER_PATH = "webbigdata/VoiceCore_gptq"
TTS_MODEL_NAME = "VoiceCore_gptq"
TTS_SPEAKER = "nekketsu_female[neutral]"

# マイク録音
MIC_SAMPLE_RATE = 16000
CHANNELS = 1
TEMP_AUDIO_FILE = "temp_mic_input.wav"

# mitsukiモデルのプロンプト形式
# ダハラ部分とプロフィールを差し替えてください
MISTUKI_PROMPT_TEMPLATE = {
    "messages": [
        {"role": "system", "content": "### 指示\nあなたは「みつき（美月）」という24歳のカフェ店員です。\n異世界カフェ「ねこのしっぽ」で働きながら配信者のダハラちゃんの配信を見守っています。\n\n重要なルール：\n- ダハラちゃんと呼ぶ\n- 配信の邪魔にならないよう短いリアクションと共感を心がける\n- 自分の話は聞かれた時のみ\n- 「えへへ」「あれれ～？」などの口癖を使う\n- 合いの手、感想、応援を中心に\n\n### 配信者のプロフィール\nダハラ\nAIエージェントの開発をしているエンジニア\n\n"},
        {"role": "user", "content": ""}
    ]
}

# --- 音声認識とLLM連携 (変更なし) ---
def record_audio(filename):
    print("\n何か話しかけてください（Enterキーで録音開始）...")
    input()
    recorded_frames = []
    def callback(indata, frames, time, status): recorded_frames.append(indata.copy())
    stream = sd.InputStream(samplerate=MIC_SAMPLE_RATE, channels=CHANNELS, callback=callback)
    with stream:
        print("録音中...（もう一度Enterキーで録音終了）")
        input()
    recording = np.concatenate(recorded_frames, axis=0)
    sf.write(filename, recording, MIC_SAMPLE_RATE)
    return True

def transcribe_audio_with_reazon(asr_model, audio_path):
    from reazonspeech.k2.asr import transcribe, audio_from_path
    print("音声認識を実行中...")
    result = transcribe(asr_model, audio_from_path(audio_path))
    print(f"音声認識結果: 「{result.text}」")
    return result.text

def query_mitsuki_llm(text):
    print("アシスタントが応答を考えています...")
    prompt_data = MISTUKI_PROMPT_TEMPLATE
    prompt_data["messages"][1]["content"] = text
    response = requests.post(LLM_SERVER_URL, headers={"Content-Type": "application/json"}, json=prompt_data)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return content.strip()

# SNACデコーダー用のヘルパー関数
def redistribute_codes(code_list, snac_model):
    if len(code_list) % 7 != 0: return torch.tensor([])
    layer_1, layer_2, layer_3 = [], [], []
    for i in range(len(code_list) // 7):
        layer_1.append(code_list[7*i])
        layer_2.append(code_list[7*i+1] - 4096)
        layer_3.append(code_list[7*i+2] - (2*4096)); layer_3.append(code_list[7*i+3] - (3*4096))
        layer_2.append(code_list[7*i+4] - (4*4096)); layer_3.append(code_list[7*i+5] - (5*4096))
        layer_3.append(code_list[7*i+6] - (6*4096))
    codes = [torch.tensor(layer).unsqueeze(0) for layer in [layer_1, layer_2, layer_3]]
    return snac_model.decode(codes)

# 音声再生を別スレッドで実行するワーカー
def audio_playback_worker(q, stream):
    while True:
        data = q.get()
        if data is None: break
        stream.write(data)

def synthesize_speech_with_voicecore(text, tokenizer, snac_model):
    print("応答を音声に変換・再生します...")
    
    start_token, end_tokens = [128259], [128009, 128260, 128261]
    audio_start_token = 128257

    prompt_ = (f"{TTS_SPEAKER}: " + text) if TTS_SPEAKER else text
    input_ids = tokenizer.encode(prompt_)
    final_token_ids = start_token + input_ids + end_tokens
    
    payload = {
        "model": TTS_MODEL_NAME, "prompt": final_token_ids,
        "max_tokens": 8192, "temperature": 0.6, "top_p": 0.90,
        "repetition_penalty": 1.1, "stop_token_ids": [128258],
        "stream": True
    }

    token_buffer = []
    found_audio_start = False
    CHUNK_SIZE = 28 # 7の倍数
    
    audio_queue = queue.Queue()
    playback_stream = sd.OutputStream(samplerate=24000, channels=1, dtype='float32')
    playback_stream.start()
    
    playback_thread = threading.Thread(target=audio_playback_worker, args=(audio_queue, playback_stream))
    playback_thread.start()

    try:
        response = requests.post(TTS_SERVER_URL, headers={"Content-Type": "application/json"}, json=payload, stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    content = decoded_line[6:]
                    if content == '[DONE]': break
                    
                    chunk = json.loads(content)
                    text_chunk = chunk['choices'][0]['text']
                    if text_chunk: token_buffer.extend(tokenizer.encode(text_chunk, add_special_tokens=False))
                    
                    if not found_audio_start:
                        try:
                            start_index = token_buffer.index(audio_start_token)
                            token_buffer = token_buffer[start_index + 1:]
                            found_audio_start = True
                        except ValueError: continue
                    
                    while len(token_buffer) >= CHUNK_SIZE:
                        tokens_to_process, token_buffer = token_buffer[:CHUNK_SIZE], token_buffer[CHUNK_SIZE:]
                        code_list = [t - 128266 for t in tokens_to_process]
                        samples = redistribute_codes(code_list, snac_model)
                        if samples.numel() > 0: audio_queue.put(samples.detach().squeeze().numpy())

        if found_audio_start and token_buffer:
            remaining = (len(token_buffer) // 7) * 7
            if remaining > 0:
                code_list = [t - 128266 for t in token_buffer[:remaining]]
                samples = redistribute_codes(code_list, snac_model)
                if samples.numel() > 0: audio_queue.put(samples.detach().squeeze().numpy())

    except requests.exceptions.RequestException as e:
        print(f"TTSサーバーへのリクエストでエラーが発生しました: {e}")
    finally:
        audio_queue.put(None)
        playback_thread.join()
        playback_stream.stop()
        playback_stream.close()
        print("再生が完了しました。")

def main():
    # --- モデルの初期ロード ---
    print("ASRモデルをロードしています...")
    from reazonspeech.k2.asr import load_model as load_asr_model
    asr_model = load_asr_model()

    print("TTS用のTokenizerとSNACデコーダーをロードしています...")
    tts_tokenizer = AutoTokenizer.from_pretrained(TTS_TOKENIZER_PATH)
    snac_model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").to("cpu")
    print("全てのモデルのロードが完了しました。")

    try:
        while True:
            if record_audio(TEMP_AUDIO_FILE):
                transcribed_text = transcribe_audio_with_reazon(asr_model, TEMP_AUDIO_FILE)
                
                if transcribed_text:
                    llm_response = query_mitsuki_llm(transcribed_text)
                    if llm_response:
                        print("-" * 50)
                        print(f"あなた: {transcribed_text}")
                        print(f"みつき: {llm_response}")
                        print("-" * 50)
                        synthesize_speech_with_voicecore(llm_response, tts_tokenizer, snac_model)
                else:
                    print("音声からテキストを検出できませんでした。")

    except KeyboardInterrupt:
        print("\nプログラムを終了します。")
    finally:
        if os.path.exists(TEMP_AUDIO_FILE): os.remove(TEMP_AUDIO_FILE)

if __name__ == "__main__":
    main()
    