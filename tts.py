import asyncio
import edge_tts
import os

# 喋らせたいテキストと、声の種類（日本の女性の声）を指定
TEXT = "こんにちは。面接練習システムへようこそ。本日はよろしくお願いいたします。"
VOICE = "ja-JP-NanamiNeural"
OUTPUT_FILE = "welcome.mp3"

async def amain() -> None:
    # 音声ファイルを生成する
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save(OUTPUT_FILE)
    
    # 生成された音声をパソコンで再生する
    print("音声ファイルを再生します...")
    os.system(f"start {OUTPUT_FILE}")

if __name__ == "__main__":
    # Windowsで動かすための決まり文句
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(amain())