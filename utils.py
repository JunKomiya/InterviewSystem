import os
import glob
import time

TEMP_DIR = "temp_assets"

def log_gaze(msg: str):
    """ログを確実にファイル出力するためのヘルパー関数"""
    try:
        with open("gaze_recorder.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def cleanup_temp_files():
    """一時ファイルフォルダ内のテンポラリアセットをクリーンアップします。"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # 音声ファイル
    for f in glob.glob(os.path.join(TEMP_DIR, "temp_audio_*.mp3")):
        try:
            os.remove(f)
        except Exception:
            pass
            
    # ビデオファイル（webmとmp4）
    for ext in ["*.webm", "*.mp4"]:
        for f in glob.glob(os.path.join(TEMP_DIR, f"temp_gaze_timelapse_{ext}")):
            try:
                os.remove(f)
            except Exception:
                pass
                
    # マップ画像ファイル
    for f in glob.glob(os.path.join(TEMP_DIR, "temp_gaze_map_*.png")):
        try:
            os.remove(f)
        except Exception:
            pass
