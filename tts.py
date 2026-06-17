import asyncio
import edge_tts
import os

VOICE = "ja-JP-NanamiNeural"

async def generate_tts_async(text: str, filename: str, voice: str = VOICE):
    """非同期での音声生成を行います。"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)

def generate_tts(text: str, filename: str, voice: str = VOICE) -> bool:
    """同期ラッパーを用いて音声ファイルを生成します。"""
    try:
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except AttributeError:
            pass
        
        asyncio.run(generate_tts_async(text, filename, voice))
        return True
    except Exception as e:
        print(f"音声生成エラー: {e}")
        return False

if __name__ == "__main__":
    # 既存の動作確認用のメイン処理を維持
    TEXT = "こんにちは。面接練習システムへようこそ。本日はよろしくお願いいたします。"
    OUTPUT_FILE = "welcome.mp3"
    
    print("テスト用の音声を生成中...")
    if generate_tts(TEXT, OUTPUT_FILE):
        # 生成された音声をパソコンで再生する
        print("音声ファイルを再生します...")
        os.system(f"start {OUTPUT_FILE}")
    else:
        print("音声生成に失敗しました。")