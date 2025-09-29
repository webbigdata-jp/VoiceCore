# AI VTuberへの道 その１

使用スクリプト


# 動画
https://youtu.be/8s9flNYbj9k


# 合成音声のServer側の起動コマンド
python -m vllm.entrypoints.openai.api_server --model webbigdata/VoiceCore_gptq --host 0.0.0.0 --port 8000 --max-model-len 9000
## モデル詳細
https://huggingface.co/webbigdata/VoiceCore_gptq

# llmの起動コマンド例
.\llama-server -hf dahara1/gemma-3-270m_mitsuki_gguf:gemma-3-270m_mitsuki-BF16.gguf --host 127.0.0.1 --port 8012 -ngl 99
## モデル詳細
https://huggingface.co/dahara1/gemma-3-270m_mitsuki_gguf

# メインスクリプト(音声認識とその他の処理)
python main.py
## モデル詳細
https://huggingface.co/reazon-research/reazonspeech-k2-v2



