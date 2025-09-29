# AI VTuberへの道 その１

使用スクリプトの公開場所


## 動画
https://youtu.be/8s9flNYbj9k


## 合成音声(TTS)
### モデル詳細
https://huggingface.co/webbigdata/VoiceCore_gptq

### Linux Serverでの起動コマンド例
python -m vllm.entrypoints.openai.api_server --model webbigdata/VoiceCore_gptq --host 0.0.0.0 --port 8000 --max-model-len 9000

## チャットモデル(SLM)
### モデル詳細
https://huggingface.co/dahara1/gemma-3-270m_mitsuki_gguf

### WindowsPCでの起動コマンド例
.\llama-server -hf dahara1/gemma-3-270m_mitsuki_gguf:gemma-3-270m_mitsuki-BF16.gguf --host 127.0.0.1 --port 8012 -ngl 99

## 音声認識(ASR)
### モデル詳細
https://huggingface.co/reazon-research/reazonspeech-k2-v2

### WindowsPCでの起動コマンド例
メインスクリプト(音声認識とその他の処理も含む)  
python main.py



