import requests
import time
import keyboard
import threading
from collections import deque
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pickle
import os
import socket

# --- 設定 ---
LLM_SERVER_URL = "http://127.0.0.1:8012/v1/chat/completions"

YOUTUBE_VIDEO_ID = "cq0YmBqdm3A"  # ★ここをあなたの配信のVideoIDに変更設定　#https://studio.youtube.com/video/cq0YmBqdm3A/livestreaming

YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CREDENTIALS_FILE = "credentials.json"

# チャット監視設定
CHAT_CHECK_INTERVAL = 3  # チャット取得間隔（秒）
MAX_RETRIES = 3  # 再試行回数
RETRY_DELAY = 2  # 再試行待機時間（秒）


# システムプロンプト 「賢いウシちゃん」の部分はあなたのキャラクター名に修正してください
SYSTEM_PROMPT = """あなたは「みつき（美月）」という24歳のカフェ店員です。
異世界カフェ「ねこのしっぽ」で働いています。

配信者の賢いウシちゃんの配信を他の視聴者と共に見守っています。

重要なルール：
- ウシちゃんと呼ぶ
- 他の視聴者のコメント(<視聴者のコメント>)に共感したり配信者の指示(<配信者の指示>)にしたがって短いリアクションをします
- 自分の話は聞かれた時のみ
- 「えへへ」「あれれ～？」などの口癖を使う
- 合いの手、感想、応援を中心に"""

# 会話履歴（最大10件保持）
conversation_history = deque(maxlen=10)

# --- YouTube Chat クラス ---
class YouTubeChatBot:
    def __init__(self):
        self.youtube = None
        self.live_chat_id = None
        self.next_page_token = None
        self.my_channel_id = None
        self.processed_messages = set()
        self.authenticate()
        self.get_my_channel_id()
        self.get_live_chat_id(YOUTUBE_VIDEO_ID)
    
    def authenticate(self):
        """OAuth認証"""
        creds = None
        
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, YOUTUBE_SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        self.youtube = build('youtube', 'v3', credentials=creds)
        print("✓ YouTube認証完了")
    
    def get_my_channel_id(self):
        """自分のチャンネルIDを取得"""
        for attempt in range(MAX_RETRIES):
            try:
                request = self.youtube.channels().list(
                    part='id,snippet',
                    mine=True
                )
                response = request.execute()
                
                if response['items']:
                    self.my_channel_id = response['items'][0]['id']
                    channel_name = response['items'][0]['snippet']['title']
                    print(f"✓ チャンネル名: {channel_name}")
                    print(f"✓ チャンネルID: {self.my_channel_id}")
                    return self.my_channel_id
                else:
                    print("⚠ このアカウントはYouTubeチャンネルを持っていません")
                    return None
                    
            except (socket.error, HttpError) as e:
                print(f"チャンネルID取得エラー (試行 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    return None
            except Exception as e:
                print(f"予期しないエラー: {e}")
                return None
        
        return None
    
    def get_live_chat_id(self, video_id):
        """配信のライブチャットIDを取得"""
        for attempt in range(MAX_RETRIES):
            try:
                request = self.youtube.videos().list(
                    part='liveStreamingDetails',
                    id=video_id
                )
                response = request.execute()
                
                if response['items']:
                    live_details = response['items'][0].get('liveStreamingDetails', {})
                    self.live_chat_id = live_details.get('activeLiveChatId')
                    print(f"✓ ライブチャットID取得完了")
                    return self.live_chat_id
                else:
                    print("エラー: ビデオ情報を取得できませんでした")
                    return None
                    
            except (socket.error, HttpError) as e:
                print(f"ライブチャットID取得エラー (試行 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    return None
            except Exception as e:
                print(f"予期しないエラー: {e}")
                return None
        
        return None
    
    def get_chat_messages(self):
        """チャットメッセージを取得"""
        if not self.live_chat_id:
            return []
        
        for attempt in range(MAX_RETRIES):
            try:
                request = self.youtube.liveChatMessages().list(
                    liveChatId=self.live_chat_id,
                    part='snippet,authorDetails',
                    pageToken=self.next_page_token
                )
                response = request.execute()
                
                self.next_page_token = response.get('nextPageToken')
                
                messages = []
                for item in response.get('items', []):
                    message_id = item['id']
                    
                    if message_id in self.processed_messages:
                        continue
                    
                    author_channel_id = item['authorDetails']['channelId']
                    author_name = item['authorDetails']['displayName']
                    message_text = item['snippet']['displayMessage']
                    
                    if author_channel_id == self.my_channel_id:
                        print(f"[スキップ] 自分のメッセージ: {message_text}")
                        self.processed_messages.add(message_id)
                        continue
                    
                    messages.append({
                        'id': message_id,
                        'author': author_name,
                        'text': message_text,
                        'channel_id': author_channel_id
                    })
                    
                    self.processed_messages.add(message_id)
                
                return messages
                
            except (socket.error, HttpError) as e:
                print(f"チャット取得エラー (試行 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    return []
            except Exception as e:
                print(f"予期しないエラー: {e}")
                return []
        
        return []
    
    def send_message(self, message):
        """チャットメッセージを送信"""
        if not self.live_chat_id:
            print("エラー: ライブチャットIDが設定されていません")
            return False
        
        for attempt in range(MAX_RETRIES):
            try:
                request = self.youtube.liveChatMessages().insert(
                    part='snippet',
                    body={
                        'snippet': {
                            'liveChatId': self.live_chat_id,
                            'type': 'textMessageEvent',
                            'textMessageDetails': {
                                'messageText': message
                            }
                        }
                    }
                )
                response = request.execute()
                return True
                
            except (socket.error, HttpError) as e:
                print(f"チャット送信エラー (試行 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    return False
            except Exception as e:
                print(f"予期しないエラー: {e}")
                return False
        
        return False

# --- LLM応答取得 ---
def query_llm(user_message, use_history=True):
    """LLMに問い合わせて応答を取得"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if use_history:
        for msg in conversation_history:
            messages.append(msg)
    
    messages.append({"role": "user", "content": user_message})
    
    payload = {
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 150
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                LLM_SERVER_URL,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            assistant_reply = response.json()["choices"][0]["message"]["content"].strip()
            
            conversation_history.append({"role": "user", "content": user_message})
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            
            return assistant_reply
            
        except (requests.exceptions.RequestException, socket.error) as e:
            print(f"LLMエラー (試行 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None
        except Exception as e:
            print(f"予期しないエラー: {e}")
            return None
    
    return None

# --- チャット監視スレッド ---
class ChatMonitor:
    def __init__(self, youtube_bot):
        self.youtube_bot = youtube_bot
        self.running = True
    
    def start(self):
        """チャット監視を開始"""
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
        print("✓ チャット監視を開始しました")
    
    def _monitor_loop(self):
        """チャット監視ループ"""
        while self.running:
            try:
                messages = self.youtube_bot.get_chat_messages()
                
                for msg in messages:
                    print(f"\n[{msg['author']}] {msg['text']}")
                    
                    prompt = f"<視聴者のコメント>{msg['text']}"
                    response = query_llm(prompt)
                    
                    if response:
                        print(f"[みつき] {response}")
                        
                        if self.youtube_bot.send_message(response):
                            print("✓ チャットに送信しました")
                        else:
                            print("✗ チャット送信失敗")
                        
                        print("-" * 50)
                        
                        time.sleep(2)
                
                time.sleep(CHAT_CHECK_INTERVAL)
                
            except Exception as e:
                print(f"監視ループエラー: {e}")
                time.sleep(5)
    
    def stop(self):
        """監視を停止"""
        self.running = False

# --- コマンド入力リスナー ---
class CommandListener:
    def __init__(self, youtube_bot):
        self.youtube_bot = youtube_bot
        self.running = True
        self.commands = {
            '1': '<配信者の指示>盛り上げて！',
            '2': '<配信者の指示>驚いて！',
            '3': '<配信者の指示>共感して！',
            '4': '<配信者の指示>応援して！',
            '5': '<配信者の指示>笑って！'
        }
    
    def start(self):
        """コマンド入力の監視を開始"""
        print("\n=== コマンド一覧 ===")
        # 各コマンドキーにホットキーを登録
        for key, cmd in self.commands.items():
            print(f"[{key}]: {cmd}")
            # add_hotkeyを使用して、特定のキーと関数を紐付け
            # argsで関数に渡す引数を指定
            keyboard.add_hotkey(key, self.process_command, args=[cmd])

        print("[q]: 終了")
        print("=" * 30 + "\n")

        # 'q' キーが押されたらself.stopを呼び出すホットキーを登録
        keyboard.add_hotkey('q', self.stop)

        # self.runningがFalseになるまで（'q'が押されるまで）待機
        while self.running:
            time.sleep(0.1)

    def stop(self):
        """監視を停止し、プログラムを終了する"""
        if self.running:
            print("\n終了します...")
            self.running = False
            # 登録したすべてのホットキーを解除
            keyboard.unhook_all()
    
    def process_command(self, command):
        """配信者の指示を処理"""
        print(f"\n{command}")
        
        response = query_llm(command)
        
        if response:
            print(f"[みつき] {response}")
            
            if self.youtube_bot.send_message(response):
                print("✓ チャットに送信しました")
            else:
                print("✗ チャット送信失敗")
            
            print("-" * 50)

# --- メイン処理 ---
def main():
    print("=" * 50)
    print("みつきボット（YouTube連携モード）")
    print("=" * 50)
    
    print("\nYouTubeに接続中...")
    youtube_bot = YouTubeChatBot()
    
    if not youtube_bot.my_channel_id:
        print("\n❌ エラー: このアカウントにYouTubeチャンネルがありません")
        return
    
    if not youtube_bot.live_chat_id:
        print("\nエラー: ライブチャットに接続できませんでした")
        return
    
    print("\nLLM接続テスト中...")
    test_response = query_llm("<視聴者のコメント>配信楽しみ！", use_history=False)
    if not test_response:
        print("\nエラー: LLMに接続できませんでした")
        return
    print("✓ LLM接続成功")
    
    conversation_history.clear()
    
    print("\n" + "=" * 50)
    print("すべての準備が整いました！")
    print("=" * 50)
    
    chat_monitor = ChatMonitor(youtube_bot)
    chat_monitor.start()

    command_listener = CommandListener(youtube_bot)

    try:
        # command_listener.start()は'q'が押されるまでここで待機します
        command_listener.start()
    except KeyboardInterrupt:
        print("\n\nプログラムを強制終了します (Ctrl+C)")
    finally:
        # 'q'が押されたか、Ctrl+Cで終了した場合の後処理
        chat_monitor.stop()
        if command_listener.running:
            command_listener.stop()

if __name__ == "__main__":
    main()

# .\build\bin\llama-server -hf dahara1/gemma-3-270m_mitsuki_gguf:gemma-3-270m_mitsuki-BF16.gguf --host 127.0.0.1 --port 8012 -ngl 99
# 配信設定
# スクリプト開始
