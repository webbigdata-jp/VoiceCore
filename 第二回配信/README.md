# AI VTuberへの道 その２

使用スクリプトの公開場所


## 動画
https://www.youtube.com/watch?v=n3IZwutfjZI


## チャットモデル(SLM)
### モデル詳細
https://huggingface.co/dahara1/gemma-3-270m_mitsuki_gguf

### WindowsPCでの起動コマンド例
.\llama-server -hf dahara1/gemma-3-270m_mitsuki_gguf:gemma-3-270m_mitsuki-BF16.gguf --host 127.0.0.1 --port 8012

## メインスクリプト
### WindowsPCでの起動コマンド例
python mitsuki_with_viewers.py

## セットアップ概要と使い方

[視聴者に同調して配信を盛り上げるAI Agentシステムの紹介]( https://webbigdata.jp/post-21300/)

セットアップ完了後、

1. llama-serverでgemma-3-270m_mitsuki_ggufを起動
2. youtube studioで配信を開始し、配信URLからVIDEOIDを取得
3. mitsuki_with_viewers.py内のVIDEOIDを差し替え
3. python mitsuki_with_viewers.pyでメインスクリプトを起動
　この時点でチャットはできるようになっている
4. OBSスタジオ等で配信を開始

