import os
import sys

# Windows protobuf parsing fix for MediaPipe (reread / relaunch if not set at OS level)
if os.environ.get('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION') != 'python':
    os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
    os.execv(sys.executable, [sys.executable] + sys.argv)

import streamlit as st
import asyncio
import edge_tts
import glob
import time
import json
import cv2
import mediapipe as mp
import threading
import numpy as np
from google import genai
from google.genai import types

# ページ基本設定
st.set_page_config(
    page_title="AI面接練習システム | プロトタイプ",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# フェイシャル特徴量の解析ヘルパー関数
def analyze_face_features(landmarks):
    left_outer = landmarks[33]
    left_inner = landmarks[133]
    left_iris = landmarks[468]
    
    right_inner = landmarks[362]
    right_outer = landmarks[263]
    right_iris = landmarks[473]
    
    left_top = landmarks[159]
    left_bottom = landmarks[145]
    right_top = landmarks[386]
    right_bottom = landmarks[374]
    
    # 1. EAR (Eye Aspect Ratio) によるまばたき検知
    left_dx = abs(left_inner.x - left_outer.x)
    left_ear = (left_bottom.y - left_top.y) / left_dx if left_dx != 0 else 0.0
    
    right_dx = abs(right_outer.x - right_inner.x)
    right_ear = (right_bottom.y - right_top.y) / right_dx if right_dx != 0 else 0.0
    
    ear = (left_ear + right_ear) / 2.0
    is_blink = ear < 0.15
    
    # 2. 視線比率の計算
    left_ratio = (left_iris.x - left_outer.x) / left_dx if left_dx != 0 else 0.5
    right_ratio = (right_iris.x - right_inner.x) / right_dx if right_dx != 0 else 0.5
    gaze_x = (left_ratio + right_ratio) / 2.0
    
    left_dy = left_bottom.y - left_top.y
    left_v_ratio = (left_iris.y - left_top.y) / left_dy if left_dy != 0 else 0.5
    right_dy = right_bottom.y - right_top.y
    right_v_ratio = (right_iris.y - right_top.y) / right_dy if right_dy != 0 else 0.5
    gaze_y = (left_v_ratio + right_v_ratio) / 2.0
    
    # 3. 顔の向き (Head Pose - Yaw, Pitch) の計算
    nose = landmarks[4]
    chin = landmarks[152]
    
    eye_mid_x = (left_outer.x + right_outer.x) / 2.0
    eye_dist_x = abs(right_outer.x - left_outer.x)
    yaw = (nose.x - eye_mid_x) / eye_dist_x if eye_dist_x != 0 else 0.0
    
    eye_mid_y = (left_outer.y + right_outer.y) / 2.0
    nose_to_eye_y = nose.y - eye_mid_y
    nose_to_chin_y = chin.y - nose.y
    pitch = nose_to_eye_y / nose_to_chin_y if nose_to_chin_y != 0 else 0.0
    
    return gaze_x, gaze_y, ear, yaw, pitch, is_blink

# ログを確実にファイル出力するためのヘルパー関数
def log_gaze(msg: str):
    try:
        with open("gaze_recorder.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

# バックグラウンドでの視線録画・トラッキングクラス
class GazeRecorder:
    def __init__(self, camera_index=0, h_range=(0.40, 0.60), v_range=(0.38, 0.62)):
        self.camera_index = camera_index
        self.h_range = h_range
        self.v_range = v_range
        self.is_recording = False
        self.frames = []
        self.gaze_points = []
        self.thread = None
        self.lock = threading.Lock()
        
        # キャリブレーション用パラメータ
        self.calibrated = False
        self.calibration_frames = []
        self.center_x = 0.5
        self.center_y = 0.5
        self.base_yaw = 0.0
        self.base_pitch = 0.5
        self.trail_points = []
        
    def start(self):
        log_gaze("[GazeRecorder] start() called")
        self.is_recording = True
        self.frames = []
        self.gaze_points = []
        self.trail_points = []
        self.thread = threading.Thread(target=self._record_loop)
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self):
        log_gaze("[GazeRecorder] stop() called")
        self.is_recording = False
        if self.thread:
            self.thread.join(timeout=3)
            log_gaze("[GazeRecorder] stop() thread joined")
            
    def _record_loop(self):
        log_gaze(f"[GazeRecorder] _record_loop thread started with camera_index={self.camera_index}")
        try:
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                log_gaze(f"[GazeRecorder] _record_loop failed to open camera_index={self.camera_index}")
                return
            log_gaze(f"[GazeRecorder] _record_loop successfully opened camera_index={self.camera_index}")
            
            mp_face_mesh = mp.solutions.face_mesh
            
            # MediaPipeの初期化を試みる
            mp_active = True
            face_mesh = None
            try:
                face_mesh = mp_face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
            except Exception as e:
                log_gaze(f"[GazeRecorder] MediaPipe FaceMesh initialization failed: {e}")
                mp_active = False
            
            last_capture_time = 0
            while self.is_recording and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    log_gaze("[GazeRecorder] _record_loop cap.read() returned False - breaking loop")
                    break
                
                now = time.time()
                # 約5 FPS (0.2秒に1枚) でキャプチャ
                if now - last_capture_time < 0.2:
                    time.sleep(0.01)
                    continue
                last_capture_time = now
                
                # 鏡のように反転
                frame = cv2.flip(frame, 1)
                h, w, c = frame.shape
                
                gaze_x_compensated, gaze_y_compensated = 0.5, 0.5
                looking_away = False
                is_blink = False
                is_valid = False
                is_calibrating = False
                
                if mp_active and face_mesh is not None:
                    try:
                        # MediaPipe用にRGBに変換
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        results = face_mesh.process(rgb_frame)
                        
                        if results.multi_face_landmarks:
                            landmarks = results.multi_face_landmarks[0].landmark
                            is_valid = True
                            
                            # 特徴量の解析
                            gaze_x, gaze_y, ear, yaw, pitch, is_blink = analyze_face_features(landmarks)
                            
                            if is_blink:
                                gaze_x_compensated, gaze_y_compensated = 0.5, 0.5
                                looking_away = False
                                self.trail_points.append(None)
                            else:
                                if not self.calibrated:
                                    # キャリブレーションフェーズ
                                    is_calibrating = True
                                    self.calibration_frames.append((gaze_x, gaze_y, yaw, pitch))
                                    gaze_x_compensated, gaze_y_compensated = 0.5, 0.5
                                    looking_away = False
                                    self.trail_points.append(None)
                                    
                                    if len(self.calibration_frames) >= 15:
                                        self.center_x = sum(f[0] for f in self.calibration_frames) / 15.0
                                        self.center_y = sum(f[1] for f in self.calibration_frames) / 15.0
                                        self.base_yaw = sum(f[2] for f in self.calibration_frames) / 15.0
                                        self.base_pitch = sum(f[3] for f in self.calibration_frames) / 15.0
                                        self.calibrated = True
                                else:
                                    # 通常トラッキングフェーズ (頭向き補正 & キャリブレーション基準シフト)
                                    gaze_x_compensated = gaze_x + 0.25 * (yaw - self.base_yaw) - (self.center_x - 0.5)
                                    gaze_y_compensated = gaze_y + 0.25 * (pitch - self.base_pitch) - (self.center_y - 0.5)
                                    
                                    # しきい値判定
                                    if not (self.h_range[0] <= gaze_x_compensated <= self.h_range[1]) or not (self.v_range[0] <= gaze_y_compensated <= self.v_range[1]):
                                        looking_away = True
                                        
                                    # 目の中心位置（瞳の平均座標）を軌跡用に記録
                                    pt_left = landmarks[468]
                                    pt_right = landmarks[473]
                                    mx = int((pt_left.x + pt_right.x) / 2.0 * w)
                                    my = int((pt_left.y + pt_right.y) / 2.0 * h)
                                    self.trail_points.append((mx, my))
                                        
                            # 描画色決定
                            if is_blink:
                                color = (255, 165, 0)  # オレンジ
                            elif is_calibrating:
                                color = (255, 255, 0)  # イエロー
                            else:
                                color = (0, 0, 255) if looking_away else (0, 255, 0)
                                
                            # 描画処理: 虹彩にドット、目に線を引く (まばたき時はスキップ)
                            if not is_blink:
                                for idx in [468, 473]:
                                    pt = landmarks[idx]
                                    cv2.circle(frame, (int(pt.x * w), int(pt.y * h)), 4, color, -1)
                                
                                for pts in [[33, 133], [362, 263]]:
                                    pt1 = landmarks[pts[0]]
                                    pt2 = landmarks[pts[1]]
                                    cv2.line(frame, (int(pt1.x * w), int(pt1.y * h)), (int(pt2.x * w), int(pt2.y * h)), color, 1)
                        else:
                            is_valid = False
                            self.trail_points.append(None)
                    except Exception:
                        is_valid = False
                        self.trail_points.append(None)
                else:
                    self.trail_points.append(None)
                    
                # 視線のペイント軌跡（線）を描画
                num_pts = len(self.trail_points)
                if num_pts > 1:
                    for i in range(num_pts - 1):
                        p1 = self.trail_points[i]
                        p2 = self.trail_points[i+1]
                        if p1 is None or p2 is None:
                            continue
                        alpha = i / (num_pts - 1)
                        # 紫 (BGR: 202, 40, 121) から シアン (BGR: 201, 206, 0)
                        b = int(202 * (1 - alpha) + 201 * alpha)
                        g = int(40 * (1 - alpha) + 206 * alpha)
                        r = int(121 * (1 - alpha) + 0 * alpha)
                        cv2.line(frame, p1, p2, (b, g, r), 3)
                        
                # 画面右上に簡易レーダー（視線プロット）をオーバーレイ
                radar_w, radar_h = 100, 100
                radar_x = w - radar_w - 15
                radar_y = 15
                
                # レーダー背景
                cv2.rectangle(frame, (radar_x, radar_y), (radar_x + radar_w, radar_y + radar_h), (30, 30, 30), -1)
                cv2.rectangle(frame, (radar_x, radar_y), (radar_x + radar_w, radar_y + radar_h), (180, 180, 180), 1)
                # 補助線
                cv2.line(frame, (radar_x + 50, radar_y), (radar_x + 50, radar_y + 100), (70, 70, 70), 1)
                cv2.line(frame, (radar_x, radar_y + 50), (radar_x + 100, radar_y + 50), (70, 70, 70), 1)
                
                # レーダー座標へのマッピング (0.5中心、感度増幅)
                px = int(radar_x + 50 + (gaze_x_compensated - 0.5) * 300)
                py = int(radar_y + 50 + (gaze_y_compensated - 0.5) * 300)
                px = max(radar_x + 5, min(radar_x + radar_w - 5, px))
                py = max(radar_y + 5, min(radar_y + radar_h - 5, py))
                
                if is_blink:
                    dot_color = (255, 165, 0)
                elif is_calibrating:
                    dot_color = (255, 255, 0)
                else:
                    dot_color = (0, 0, 255) if looking_away else (0, 255, 0)
                cv2.circle(frame, (px, py), 5, dot_color, -1)
                
                # 状態テキスト
                if mp_active:
                    if is_blink:
                        status_text = "BLINK"
                    elif is_calibrating:
                        status_text = f"CALIB ({len(self.calibration_frames)}/15)"
                    else:
                        status_text = "LOOKING AWAY" if looking_away else "LOOKING AT SCREEN"
                else:
                    status_text = "CAMERA ACTIVE (NO MESH)"
                cv2.putText(frame, status_text, (radar_x - 10, radar_y + radar_h + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, dot_color, 1)
                
                # 軽量化のためリサイズして保存 (320x240)
                small_frame = cv2.resize(frame, (320, 240))
                
                with self.lock:
                    self.frames.append(small_frame)
                    self.gaze_points.append({
                        "time": now,
                        "gaze_x": gaze_x_compensated,
                        "gaze_y": gaze_y_compensated,
                        "looking_away": looking_away,
                        "is_blink": is_blink,
                        "is_valid": is_valid,
                        "is_calibrating": is_calibrating
                    })
            if face_mesh is not None:
                try:
                    face_mesh.close()
                except Exception:
                    pass
            cap.release()
            log_gaze("[GazeRecorder] _record_loop thread finished normally")
        except Exception as e:
            log_gaze(f"[GazeRecorder] Exception in _record_loop: {e}")
            if 'cap' in locals() and cap.isOpened():
                cap.release()
                
    def save_timelapse(self, output_path: str) -> bool:
        log_gaze(f"[GazeRecorder] save_timelapse() called. Output path: {output_path}")
        with self.lock:
            if not self.frames:
                log_gaze("[GazeRecorder] save_timelapse() failed: self.frames is empty")
                return False
            try:
                h, w, c = self.frames[0].shape
                log_gaze(f"[GazeRecorder] save_timelapse() writing {len(self.frames)} frames of resolution {w}x{h} to {output_path}")
                # ブラウザ互換性（HTML5での再生）を最大化するため、WebMコンテナ用のVP8コーデック（'VP80'）を使用します
                fourcc = cv2.VideoWriter_fourcc(*'VP80')
                out = cv2.VideoWriter(output_path, fourcc, 5.0, (w, h))
                for frame in self.frames:
                    out.write(frame)
                out.release()
                log_gaze("[GazeRecorder] save_timelapse() completed successfully")
                return True
            except Exception as e:
                log_gaze(f"[GazeRecorder] save_timelapse() failed with exception: {e}")
                return False
                
    def generate_gaze_map(self, output_path: str):
        # 300x300のダークキャンバスを作成
        canvas = np.zeros((300, 300, 3), dtype=np.uint8)
        canvas[:] = (25, 20, 35)  # ダークバイオレット
        
        # 同心円レーダーの描画
        cv2.circle(canvas, (150, 150), 50, (60, 50, 75), 1)
        cv2.circle(canvas, (150, 150), 100, (60, 50, 75), 1)
        cv2.line(canvas, (150, 0), (150, 300), (60, 50, 75), 1)
        cv2.line(canvas, (0, 150), (300, 150), (60, 50, 75), 1)
        
        points_data = []
        with self.lock:
            for gp in self.gaze_points:
                if not gp.get("is_valid", True) or gp.get("is_blink", False):
                    continue
                gx = int(150 + (gp["gaze_x"] - 0.5) * 500)
                gy = int(150 + (gp["gaze_y"] - 0.5) * 500)
                gx = max(10, min(290, gx))
                gy = max(10, min(290, gy))
                points_data.append((gx, gy, gp))
                
        # 軌跡（線）をフェード色で描画
        if len(points_data) > 1:
            for i in range(len(points_data) - 1):
                pt1 = (points_data[i][0], points_data[i][1])
                pt2 = (points_data[i+1][0], points_data[i+1][1])
                alpha = i / len(points_data)
                color = (
                    int(201 * (1 - alpha) + 230 * alpha), 
                    int(206 * (1 - alpha) + 92 * alpha), 
                    int(0 * (1 - alpha) + 108 * alpha)
                )
                cv2.line(canvas, pt1, pt2, color, 2)
                
        # 散布ポイントのプロット
        for gx, gy, gp in points_data:
            pt = (gx, gy)
            color = (0, 0, 255) if gp["looking_away"] else (0, 255, 0)
            cv2.circle(canvas, pt, 4, color, -1)
            
        # 凡例
        cv2.putText(canvas, "Green: Looked at Screen", (10, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
        cv2.putText(canvas, "Red: Looked Away", (10, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
        cv2.putText(canvas, f"Points: {len(points_data)}", (10, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        
        cv2.imwrite(output_path, canvas)

def scan_available_cameras():
    available = []
    # 0から3までのインデックスをチェック
    for i in range(4):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                available.append(i)
            cap.release()
    if not available:
        available = [0]
    return available

def test_camera_capture(camera_index: int):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None, "カメラデバイスを開くことができませんでした。インデックスが正しいか、他のアプリ（ZoomやTeamsなど）で使用されていないか確認してください。"
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        return None, "カメラからフレームを取得できませんでした。デバイスが正しく動作しているか確認してください。"
    
    # 鏡のように反転
    frame = cv2.flip(frame, 1)
    h, w, c = frame.shape
    
    # MediaPipe用にRGB変換
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    mp_face_mesh = mp.solutions.face_mesh
    face_detected = False
    
    try:
        with mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as face_mesh:
            results = face_mesh.process(rgb_frame)
            if results.multi_face_landmarks:
                face_detected = True
                landmarks = results.multi_face_landmarks[0].landmark
                
                # 虹彩 (468, 473) にグリーンマーカー
                for idx in [468, 473]:
                    pt = landmarks[idx]
                    cv2.circle(frame, (int(pt.x * w), int(pt.y * h)), 4, (0, 255, 0), -1)
                
                # 目頭・目尻 (33-133, 362-263) にイエローライン
                for pts in [[33, 133], [362, 263]]:
                    pt1 = landmarks[pts[0]]
                    pt2 = landmarks[pts[1]]
                    cv2.line(frame, (int(pt1.x * w), int(pt1.y * h)), (int(pt2.x * w), int(pt2.y * h)), (255, 255, 0), 2)
        
        # BGRからRGBに変換
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        if face_detected:
            return frame_rgb, "SUCCESS: カメラとの接続を確認し、顔および目を正常に検出しました。視線トラッキングの準備は完了しています。"
        else:
            return frame_rgb, "WARNING: カメラ画像は取得できましたが、顔が検出されませんでした。カメラの正面に座り、部屋が暗すぎないか確認してください。"
            
    except Exception as e:
        # MediaPipe解析が失敗した場合でも、取得したカメラ画像自体は返す
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame_rgb, f"WARNING: カメラ画像は取得できましたが、目線解析モデル(MediaPipe)の初期化中にエラーが発生しました ({e})。視線追跡はスキップされ、評価画面では固定値(78%)が表示されますが、面接自体は実施可能です。"

def verify_api_key(api_key: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "APIキーが入力されていません。"
    try:
        client = genai.Client(api_key=api_key.strip())
        # 簡易疎通テスト
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="PING"
        )
        if response.text:
            return True, f"接続成功! モデル (gemini-2.5-flash) が利用可能です。\n(応答例: {response.text.strip()[:60]}...)"
        return False, "APIからの応答が空でした。"
    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg or "UNAVAILABLE" in error_msg:
            return False, "ERROR 503: Gemini APIは現在一時的に高負荷なため、利用できません。時間をおいて再試行してください。"
        elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            return False, "ERROR 429: APIキーの利用制限（クォータ）を超過しました。無料枠の上限に達した可能性があります。"
        elif "400" in error_msg or "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower():
            return False, "ERROR 400: APIキーが無効であるか、形式が正しくありません。Google AI Studioのキーを正確に入力してください。"
        return False, f"接続エラーが発生しました: {error_msg}"

# 非同期での音声生成
async def generate_tts_async(text: str, filename: str):
    voice = "ja-JP-NanamiNeural"  # 自然な日本語女性音声
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)

def generate_tts(text: str, filename: str) -> bool:
    try:
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except AttributeError:
            pass
        
        asyncio.run(generate_tts_async(text, filename))
        return True
    except Exception as e:
        st.error(f"音声生成エラー: {e}")
        return False

# Gemini API の呼び出し関数
def call_gemini(system_instruction: str, prompt: str, api_key: str) -> str:
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json"
            )
        )
        return response.text
    except Exception as e:
        raise RuntimeError(f"Gemini API 呼び出し中にエラーが発生しました: {e}")

# 一時ファイルのクリーンアップ処理
def cleanup_temp_files():
    # 音声ファイル
    for f in glob.glob("temp_audio_*.mp3"):
        try: os.remove(f)
        except Exception: pass
    # ビデオファイル（新形式のwebmと旧形式のmp4の双方をクリーンアップ）
    for ext in ["*.webm", "*.mp4"]:
        for f in glob.glob(f"temp_gaze_timelapse_{ext}"):
            try: os.remove(f)
            except Exception: pass
    # マップ画像ファイル
    for f in glob.glob("temp_gaze_map_*.png"):
        try: os.remove(f)
        except Exception: pass

# セッション状態の初期化と初回ローディング画面
if "initialized" not in st.session_state:
    st.markdown("""
        <style>
            .stApp {
                background: linear-gradient(135deg, #0e0b1e 0%, #141029 50%, #06030e 100%) !important;
                color: #e2e8f0;
                font-family: 'Outfit', 'Inter', -apple-system, sans-serif;
            }
            .loading-container {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 70vh;
                width: 100%;
            }
            .loading-spinner {
                border: 4px solid rgba(255, 255, 255, 0.05);
                border-top: 4px solid #6c5ce7;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                animation: spin 1s cubic-bezier(0.5, 0, 0.5, 1) infinite;
                margin-bottom: 20px;
                box-shadow: 0 0 25px rgba(108, 92, 231, 0.5);
            }
            .loading-text {
                font-size: 1.6rem;
                font-weight: 700;
                background: linear-gradient(90deg, #a29bfe, #6c5ce7, #00cec9);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                letter-spacing: 2px;
                animation: blink 2s infinite ease-in-out;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            @keyframes blink {
                0%, 100% { opacity: 0.5; }
                50% { opacity: 1; }
            }
        </style>
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <div class="loading-text">Loading...</div>
        </div>
    """, unsafe_allow_html=True)
    
    # 各セッション情報の初期化
    st.session_state.step = "SETUP"  # SETUP -> QUESTION -> DEEP_DIVE -> EVALUATION
    st.session_state.name = ""
    st.session_state.es_pr = ""
    st.session_state.job_type = ""
    st.session_state.mode = "MOCK"  # MOCK or AI
    st.session_state.api_key = ""
    st.session_state.audio_path = ""
    st.session_state.question_1 = ""
    st.session_state.user_answer_1 = ""
    st.session_state.deep_dive_text = ""
    st.session_state.deep_dive_audio_path = ""
    st.session_state.user_answer_2 = ""
    st.session_state.eval_text = ""
    st.session_state.eval_audio_path = ""
    st.session_state.consistency_score = 90
    st.session_state.content_quality_score = 90
    st.session_state.eye_contact_score = 78
    st.session_state.overall_score = 90
    st.session_state.rank = "A"
    st.session_state.gaze_video_path = ""
    st.session_state.gaze_map_path = ""
    st.session_state.camera_index = 0
    st.session_state.api_test_result = None
    st.session_state.camera_test_result = None
    st.session_state.h_range = (0.40, 0.60)
    st.session_state.v_range = (0.38, 0.62)
    
    # カメラデバイスのスキャン（重い処理）
    st.session_state.available_cameras = scan_available_cameras()
    
    # 初期化完了フラグ
    st.session_state.initialized = True
    st.rerun()

# 以前の残存している視線トラッキングスレッドがあれば停止
if "recorder" in st.session_state and st.session_state.step == "SETUP":
    if st.session_state.recorder.is_recording:
        st.session_state.recorder.stop()

# プレミアムなダークモードUIデザインのインジェクション
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0e0b1e 0%, #141029 50%, #06030e 100%);
        color: #e2e8f0;
        font-family: 'Outfit', 'Inter', -apple-system, sans-serif;
    }
    label, 
    div[data-testid="stWidgetLabel"] p, 
    div[data-testid="stWidgetLabel"] label,
    div[data-testid="stRadio"] label,
    div[data-testid="stRadio"] label p,
    div[data-testid="stCheckbox"] label,
    div[data-testid="stCheckbox"] label p {
        color: #f1f5f9 !important;
        font-weight: 500 !important;
    }
    .header-container {
        text-align: center;
        padding: 30px 10px;
        margin-bottom: 20px;
    }
    .main-title {
        background: linear-gradient(90deg, #6c5ce7, #a29bfe, #00cec9);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.8rem;
        font-weight: 800;
        margin-bottom: 5px;
    }
    .sub-title {
        color: #a0aec0;
        font-size: 1.1rem;
        font-weight: 400;
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 20px;
        padding: 30px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        margin-bottom: 25px;
    }
    .interviewer-panel {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 20px;
        padding: 25px;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }
    .avatar-wrapper {
        margin: 0 auto 20px auto;
        width: 160px;
        height: 160px;
        position: relative;
    }
    .avatar-img {
        border-radius: 50%;
        border: 4px solid #6c5ce7;
        box-shadow: 0 0 25px rgba(108, 92, 231, 0.6);
        width: 100%;
        height: 100%;
        object-fit: cover;
        animation: subtlePulse 2.5s infinite alternate;
    }
    @keyframes subtlePulse {
        0% {
            transform: scale(1.0);
            box-shadow: 0 0 20px rgba(108, 92, 231, 0.5);
        }
        100% {
            transform: scale(1.03);
            box-shadow: 0 0 35px rgba(108, 92, 231, 0.8), 0 0 15px rgba(0, 206, 201, 0.4);
        }
    }
    .status-badge {
        display: inline-block;
        padding: 6px 16px;
        border-radius: 30px;
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        margin-top: 10px;
    }
    .status-speaking {
        background: rgba(235, 77, 75, 0.15);
        color: #ff7675;
        border: 1px solid rgba(235, 77, 75, 0.3);
    }
    .status-listening {
        background: rgba(9, 132, 227, 0.15);
        color: #74b9ff;
        border: 1px solid rgba(9, 132, 227, 0.3);
    }
    .chat-bubble {
        padding: 20px;
        border-radius: 18px;
        margin-bottom: 20px;
        font-size: 1.05rem;
        line-height: 1.6;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.15);
    }
    .interviewer-bubble {
        background: linear-gradient(135deg, rgba(108, 92, 231, 0.12) 0%, rgba(108, 92, 231, 0.03) 100%);
        border-left: 5px solid #6c5ce7;
        border-top-left-radius: 4px;
    }
    .audio-container {
        background: rgba(255, 255, 255, 0.02);
        border-radius: 10px;
        padding: 10px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        margin-top: 10px;
        margin-bottom: 15px;
    }
    .stButton>button {
        background: linear-gradient(90deg, #6c5ce7 0%, #00cec9 100%);
        color: #ffffff;
        font-weight: 700;
        border: none;
        border-radius: 10px;
        padding: 12px 28px;
        font-size: 1rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(108, 92, 231, 0.4);
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(108, 92, 231, 0.6), 0 0 15px rgba(0, 206, 201, 0.4);
        color: #ffffff;
    }
    .stButton>button:active {
        transform: translateY(1px);
    }
    .reset-btn>div>button {
        background: transparent;
        color: #a0aec0;
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: none;
    }
    .reset-btn>div>button:hover {
        background: rgba(255, 255, 255, 0.05);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.4);
        box-shadow: none;
    }
    .rank-container {
        text-align: center;
        margin-bottom: 25px;
    }
    .rank-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 110px;
        height: 110px;
        border-radius: 50%;
        background: linear-gradient(135deg, #ff007f 0%, #7928ca 100%);
        color: white;
        font-size: 3.5rem;
        font-weight: 900;
        box-shadow: 0 0 35px rgba(121, 40, 202, 0.7);
        margin: 10px auto;
        border: 4px solid rgba(255, 255, 255, 0.25);
        animation: glowPulse 2s infinite alternate;
    }
    @keyframes glowPulse {
        0% { box-shadow: 0 0 25px rgba(121, 40, 202, 0.6); }
        100% { box-shadow: 0 0 45px rgba(255, 0, 127, 0.8), 0 0 25px rgba(121, 40, 202, 0.6); }
    }
    .rank-label {
        font-size: 1rem;
        color: #cbd5e1;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
    }
    .metric-row {
        margin-bottom: 20px;
    }
    .metric-name {
        font-weight: 600;
        font-size: 1rem;
        color: #94a3b8;
    }
    .metric-val {
        float: right;
        font-weight: 700;
        color: #00cec9;
        font-size: 1.1rem;
    }
    .metric-bar-bg {
        background: rgba(255, 255, 255, 0.08);
        height: 12px;
        border-radius: 6px;
        margin-top: 8px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.03);
    }
    .metric-bar-fill {
        height: 100%;
        border-radius: 6px;
    }
    .tracking-title {
        color: #00cec9;
        font-weight: 700;
        border-left: 4px solid #00cec9;
        padding-left: 10px;
        margin-bottom: 20px;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ヘッダー
st.markdown("""
<div class="header-container">
    <div class="main-title">🤖 AI面接練習システム</div>
    <div class="sub-title">視線トラッキング搭載 評価プロトタイプ</div>
</div>
""", unsafe_allow_html=True)

avatar_path = "interviewer_avatar.png"

# -----------------
# 1. SETUP フェーズ
# -----------------
if st.session_state.step == "SETUP":
    # 2カラムレイアウトで表示
    col_setup_left, col_setup_right = st.columns([1, 1], gap="large")
    
    with col_setup_left:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("⚙️ 動作設定")
        
        mode_selection = st.radio(
            "システム動作モードを選択してください",
            ["AIモード (Google AI Studio連携)", "モックモード (オフラインデモ)"],
            index=0 if st.session_state.mode == "AI" else 1
        )
        st.session_state.mode = "AI" if "AIモード" in mode_selection else "MOCK"
        
        if st.session_state.mode == "AI":
            env_key_exists = "GEMINI_API_KEY" in os.environ
            help_txt = "環境変数 GEMINI_API_KEY が検出されました。入力しなくても動作可能です。" if env_key_exists else "Google AI StudioのAPIキーを入力してください。"
            
            # APIキー入力とテストボタンを横並びにする
            col_key, col_btn = st.columns([2, 1])
            with col_key:
                gemini_key = st.text_input(
                    "Google AI Studio APIキー",
                    type="password",
                    value=st.session_state.api_key if st.session_state.api_key else os.environ.get("GEMINI_API_KEY", ""),
                    placeholder="AI Studio API Key (AIモードに必須)",
                    help=help_txt
                )
                st.session_state.api_key = gemini_key.strip()
            with col_btn:
                st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True) # 余白合わせ
                if st.button("🔑 接続テスト"):
                    with st.spinner("API接続確認中..."):
                        success, msg = verify_api_key(st.session_state.api_key)
                        st.session_state.api_test_result = {"success": success, "msg": msg}
            
            # API接続テスト結果の表示
            if st.session_state.api_test_result:
                res = st.session_state.api_test_result
                if res["success"]:
                    st.success(res["msg"])
                else:
                    st.error(res["msg"])
        
        st.markdown("<hr style='border: 0.5px solid rgba(255,255,255,0.1)'>", unsafe_allow_html=True)
        st.subheader("📝 エントリーシート（ES）と志望職種の入力")
        
        name_input = st.text_input("お名前", placeholder="例: 面接 太郎", value="プロト 太郎")
        
        job_options = ["技術職 (エンジニア)", "総合職・営業職", "企画・マーケティング職", "事務・管理職", "その他（自由記入）"]
        job_index = 0
        if st.session_state.job_type in job_options:
            job_index = job_options.index(st.session_state.job_type)
        
        job_selection = st.selectbox("希望する職種", job_options, index=job_index)
        
        if job_selection == "その他（自由記入）":
            custom_job = st.text_input("職種名を入力してください（例: デザイナー、データサイエンティスト）")
            st.session_state.job_type = custom_job.strip()
        else:
            st.session_state.job_type = job_selection
            
        es_input = st.text_area(
            "自己PR（強みやこれまでの具体的な経験など）",
            placeholder="例: 私の強みは計画性と行動力です。大学時代はイベントの実行委員長として、10名のチームを率いて前年比1.5倍の集客を達成しました。",
            value="私の強みは行動力です。気になる技術があればすぐに個人開発で小さなプロトタイプを作り、ユーザーの反応を見ながら改善を繰り返す活動を続けてきました。",
            height=180
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with col_setup_right:
        st.markdown('<div class="glass-card" style="height: 100%;">', unsafe_allow_html=True)
        st.subheader("📹 カメラ設定とトラッキングテスト")
        st.markdown("""
        面接中の学生の視線を正しく追跡するため、カメラデバイスと検出のテストを行います。
        下のリアルタイム診断モードを有効にすることで、目線の動きに応じた座標（X, Y）の変化を確認しながら、判定のしきい値を調整できます。
        """)
        
        col_cam_sel, col_cam_scan = st.columns([2, 1])
        with col_cam_sel:
            # 使用可能なカメラの選択肢を表示
            cam_options = st.session_state.available_cameras
            cam_labels = [f"カメラ {i}" for i in cam_options]
            
            # 安全に初期インデックスを設定
            default_sel_idx = 0
            if st.session_state.camera_index in cam_options:
                default_sel_idx = cam_options.index(st.session_state.camera_index)
            
            selected_cam_idx = st.selectbox(
                "使用するカメラを選択",
                options=range(len(cam_options)),
                format_func=lambda x: cam_labels[x],
                index=default_sel_idx
            )
            st.session_state.camera_index = cam_options[selected_cam_idx]
            
        with col_cam_scan:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True) # 余白合わせ
            if st.button("🔄 再検出"):
                with st.spinner("カメラをスキャン中..."):
                    st.session_state.available_cameras = scan_available_cameras()
                    st.rerun()
                    
        st.markdown("<hr style='border: 0.5px solid rgba(255,255,255,0.1)'>", unsafe_allow_html=True)
        st.subheader("⚙️ 視線判定しきい値の調整")
        st.markdown("数値範囲を狭くすると判定が厳しくなり、広くすると甘くなります（デフォルト：水平 0.40〜0.60 / 垂直 0.38〜0.62）。")
        
        h_range = st.slider(
            "水平方向の許容範囲 (左右の目線そらしの感度)",
            min_value=0.20,
            max_value=0.80,
            value=st.session_state.h_range,
            step=0.01
        )
        st.session_state.h_range = h_range
        
        v_range = st.slider(
            "垂直方向の許容範囲 (上下の目線そらしの感度)",
            min_value=0.20,
            max_value=0.80,
            value=st.session_state.v_range,
            step=0.01
        )
        st.session_state.v_range = v_range
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # リアルタイム診断モードのトグル（チェックボックス）
        live_cam_active = st.checkbox("📹 リアルタイム診断モードを開始する", value=False)
        
        if live_cam_active:
            cap = cv2.VideoCapture(st.session_state.camera_index)
            if not cap.isOpened():
                st.error("カメラデバイスを開くことができませんでした。インデックスが正しいか確認してください。")
            else:
                frame_placeholder = st.empty()
                
                mp_face_mesh = mp.solutions.face_mesh
                mp_active = True
                face_mesh = None
                try:
                    face_mesh = mp_face_mesh.FaceMesh(
                        max_num_faces=1,
                        refine_landmarks=True,
                        min_detection_confidence=0.5,
                        min_tracking_confidence=0.5
                    )
                except Exception as e:
                    mp_active = False
                    st.warning(f"目線解析モデルの初期化に失敗しました (モックプレビューになります): {e}")
                
                try:
                    trail_points = []
                    while live_cam_active:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        
                        frame = cv2.flip(frame, 1)
                        h, w, c = frame.shape
                        
                        gaze_x_compensated, gaze_y_compensated = 0.5, 0.5
                        looking_away = False
                        is_blink = False
                        
                        if mp_active and face_mesh is not None:
                            try:
                                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                results = face_mesh.process(rgb_frame)
                                if results.multi_face_landmarks:
                                    landmarks = results.multi_face_landmarks[0].landmark
                                    
                                    # 特徴量の解析
                                    gaze_x, gaze_y, ear, yaw, pitch, is_blink = analyze_face_features(landmarks)
                                    
                                    if is_blink:
                                        gaze_x_compensated, gaze_y_compensated = 0.5, 0.5
                                        looking_away = False
                                        trail_points.append(None)
                                    else:
                                        # 診断プレビュー用の簡易頭向き補正 (基準値は中央 0.5 / yaw=0 / pitch=0.5 とする)
                                        gaze_x_compensated = gaze_x + 0.25 * yaw
                                        gaze_y_compensated = gaze_y + 0.25 * (pitch - 0.5)
                                        
                                        # しきい値判定
                                        if not (st.session_state.h_range[0] <= gaze_x_compensated <= st.session_state.h_range[1]) or not (st.session_state.v_range[0] <= gaze_y_compensated <= st.session_state.v_range[1]):
                                            looking_away = True
                                            
                                        # 瞳の中心位置を記録
                                        pt_left = landmarks[468]
                                        pt_right = landmarks[473]
                                        mx = int((pt_left.x + pt_right.x) / 2.0 * w)
                                        my = int((pt_left.y + pt_right.y) / 2.0 * h)
                                        trail_points.append((mx, my))
                                            
                                    if is_blink:
                                        color = (255, 165, 0) # まばたきはオレンジ
                                    else:
                                        color = (0, 0, 255) if looking_away else (0, 255, 0)
                                        
                                    if not is_blink:
                                        for idx in [468, 473]:
                                            pt = landmarks[idx]
                                            cv2.circle(frame, (int(pt.x * w), int(pt.y * h)), 4, color, -1)
                                        for pts in [[33, 133], [362, 263]]:
                                            pt1 = landmarks[pts[0]]
                                            pt2 = landmarks[pts[1]]
                                            cv2.line(frame, (int(pt1.x * w), int(pt1.y * h)), (int(pt2.x * w), int(pt2.y * h)), color, 1)
                                else:
                                    trail_points.append(None)
                            except Exception:
                                trail_points.append(None)
                        else:
                            trail_points.append(None)
                            
                        # 直近40フレームまでに制限（キューのローリング）
                        if len(trail_points) > 40:
                            trail_points.pop(0)
                            
                        # 視線のペイント軌跡（線）を直近40フレーム分描画
                        num_pts = len(trail_points)
                        if num_pts > 1:
                            for i in range(num_pts - 1):
                                p1 = trail_points[i]
                                p2 = trail_points[i+1]
                                if p1 is None or p2 is None:
                                    continue
                                alpha = i / (num_pts - 1)
                                b = int(202 * (1 - alpha) + 201 * alpha)
                                g = int(40 * (1 - alpha) + 206 * alpha)
                                r = int(121 * (1 - alpha) + 0 * alpha)
                                cv2.line(frame, p1, p2, (b, g, r), 3)
                        
                        # 右上レーダー
                        radar_w, radar_h = 100, 100
                        radar_x = w - radar_w - 15
                        radar_y = 15
                        cv2.rectangle(frame, (radar_x, radar_y), (radar_x + radar_w, radar_y + radar_h), (30, 30, 30), -1)
                        cv2.rectangle(frame, (radar_x, radar_y), (radar_x + radar_w, radar_y + radar_h), (180, 180, 180), 1)
                        cv2.line(frame, (radar_x + 50, radar_y), (radar_x + 50, radar_y + 100), (70, 70, 70), 1)
                        cv2.line(frame, (radar_x, radar_y + 50), (radar_x + 100, radar_y + 50), (70, 70, 70), 1)
                        
                        px = int(radar_x + 50 + (gaze_x_compensated - 0.5) * 300)
                        py = int(radar_y + 50 + (gaze_y_compensated - 0.5) * 300)
                        px = max(radar_x + 5, min(radar_x + radar_w - 5, px))
                        py = max(radar_y + 5, min(radar_y + radar_h - 5, py))
                        
                        if is_blink:
                            dot_color = (255, 165, 0)
                        else:
                            dot_color = (0, 0, 255) if looking_away else (0, 255, 0)
                        cv2.circle(frame, (px, py), 5, dot_color, -1)
                        
                        # 判定に応じたテキストおよび太枠（インジケータ色変更）
                        if is_blink:
                            status_txt = "BLINKING"
                        else:
                            status_txt = "LOOKING AWAY (OUT OF RANGE)" if looking_away else "LOOKING AT SCREEN (OK)"
                        cv2.putText(frame, status_txt, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, dot_color, 2)
                        
                        # 座標と設定限界値を表示
                        cv2.putText(frame, f"Gaze X: {gaze_x_compensated:.3f} (Limit: {st.session_state.h_range[0]:.2f} - {st.session_state.h_range[1]:.2f})", (15, h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                        cv2.putText(frame, f"Gaze Y: {gaze_y_compensated:.3f} (Limit: {st.session_state.v_range[0]:.2f} - {st.session_state.v_range[1]:.2f})", (15, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                        
                        # 太い縁取りを追加
                        cv2.rectangle(frame, (0, 0), (w, h), dot_color, 6)
                        
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frame_placeholder.image(frame_rgb, caption="リアルタイム目線追跡プレビュー（緑＝正面判定、赤＝視線外れ判定、橙＝まばたき）", use_container_width=True)
                        time.sleep(0.04)
                finally:
                    if face_mesh is not None:
                        face_mesh.close()
                    cap.release()
                    frame_placeholder.empty()
        else:
            st.info("リアルタイム診断を行うには、上のチェックボックスをオンにしてください。")
            
        st.markdown('</div>', unsafe_allow_html=True)

    # 開始ボタンは下部に大きく配置
    st.markdown("<br><div style='text-align: center;'>", unsafe_allow_html=True)
    if st.button("🚀 面接練習を開始する", use_container_width=True):
        if not name_input.strip() or not es_input.strip() or not st.session_state.job_type.strip():
            st.warning("お名前、職種、自己PRを入力してください。")
        elif st.session_state.mode == "AI" and not st.session_state.api_key.strip():
            st.error("AIモードで実行するには、APIキーを設定してください。")
        else:
            cleanup_temp_files()
            st.session_state.name = name_input.strip()
            st.session_state.es_pr = es_input.strip()
            
            # 視線トラッキングスレッドの開始 (Webカメラ起動)
            st.session_state.recorder = GazeRecorder(
                camera_index=st.session_state.camera_index,
                h_range=st.session_state.h_range,
                v_range=st.session_state.v_range
            )
            st.session_state.recorder.start()
            
            q1_text = ""
            
            # --- AIモード時の第一問生成 ---
            if st.session_state.mode == "AI":
                system_instruction = (
                    "あなたは優秀な企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）と志望職種を読み、本番の面接と同じクオリティの最初の質問を1つ生成してください。\n"
                    "職種（特に技術職などの場合）に応じた具体的な内容を含めてください。\n"
                    "最初の質問では、まず自己紹介を促し、続いてESに書かれた強みや経歴について簡潔に説明するように求めてください。\n\n"
                    "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
                    "{\n"
                    '    "question": "最初の質問文"\n'
                    "}"
                )
                prompt = json.dumps({
                    "name": st.session_state.name,
                    "job_type": st.session_state.job_type,
                    "es_pr": st.session_state.es_pr
                }, ensure_ascii=False)
                
                with st.spinner("AI面接官がエントリーシートを読み込み、質問の流れを構成しています..."):
                    try:
                        response = call_gemini(system_instruction, prompt, st.session_state.api_key)
                        res_json = json.loads(response)
                        q1_text = res_json.get("question", "")
                    except Exception as e:
                        st.warning(f"AIでの質問生成に失敗したため、モックデータで代替します。({e})")
                        st.session_state.mode = "MOCK"
            
            # --- モックモード時の第一問作成 ---
            if not q1_text:
                q1_text = f"はじめまして、{st.session_state.name}さん。面接官のナナミです。本日はよろしくお願いいたします。それでは早速ですが、{st.session_state.job_type}の面接として、自己紹介をお願いいたします。併せて、エントリーシートに記載されたご自身の強みについてもお話しください。"
            
            st.session_state.question_1 = q1_text
            
            # 音声ファイルを生成
            timestamp = int(time.time())
            filename = f"temp_audio_q1_{timestamp}.mp3"
            
            with st.spinner("面接官の音声（TTS）を生成中..."):
                success = generate_tts(q1_text, filename)
                if success:
                    st.session_state.audio_path = filename
                st.session_state.step = "QUESTION"
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# -----------------
# 2. QUESTION フェーズ（第一問回答）
# -----------------
elif st.session_state.step == "QUESTION":
    st.info("👁️ 視線トラッキング中：面接中はカメラをまっすぐ見つめるよう意識してください。")
    
    col1, col2 = st.columns([1, 2], gap="large")
    
    with col1:
        st.markdown('<div class="interviewer-panel">', unsafe_allow_html=True)
        if os.path.exists(avatar_path):
            st.image(avatar_path, width='stretch')
        else:
            st.markdown("""
            <div class="avatar-wrapper">
                <div class="avatar-img" style="background: #333; display: flex; align-items: center; justify-content: center;">👤</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown('<h3>面接官 ナナミ</h3>', unsafe_allow_html=True)
        st.markdown(f'<div class="status-badge" style="background:rgba(108, 92, 231, 0.15); color:#a29bfe; border: 1px solid rgba(108, 92, 231, 0.3);">💼 {st.session_state.job_type}面接</div>', unsafe_allow_html=True)
        st.markdown('<div class="status-badge status-speaking">🔊 話しています</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col2:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("🎤 面接官からの質問（自己紹介）")
        
        st.markdown(f"""
        <div class="chat-bubble interviewer-bubble">
            <strong>ナナミ:</strong><br>
            {st.session_state.question_1}
        </div>
        """, unsafe_allow_html=True)
        
        # 音声再生
        if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
            st.markdown('<div class="audio-container">', unsafe_allow_html=True)
            st.audio(st.session_state.audio_path, format="audio/mp3", autoplay=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("<hr style='border: 0.5px solid rgba(255,255,255,0.1)'>", unsafe_allow_html=True)
        st.subheader("✍️ あなたの回答")
        
        user_ans = st.text_area(
            "ここに回答を入力してください（タイピング）",
            placeholder="例: はじめまして、プロト太郎と申します。大学では情報工学を専攻しており、強みである行動力を活かして個人でPythonのアプリ開発を行っています。特にReactとStreamlitの連携に力を入れています。",
            height=150
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("回答を送信する"):
            if not user_ans.strip():
                st.warning("回答を入力してください。")
            else:
                st.session_state.user_answer_1 = user_ans.strip()
                
                deep_dive_txt = ""
                feedback_intro = "ご回答ありがとうございます。"
                
                # --- AIモード時の深掘り質問生成 ---
                if st.session_state.mode == "AI":
                    system_instruction = (
                        "あなたは企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）、志望職種、第一問の質問、およびそれに対する学生の回答を読み、回答内容を深く掘り下げる「深掘り質問」を1つ生成してください。\n"
                        "回答の中で曖昧な部分や、特に強調されている専門用語（例: 開発言語、手法など）に焦点を当て、具体的にどのような行動をとったか、あるいはどのような困難を克服したかを聞いてください。\n"
                        "また、回答に対する面接官らしい一言リアクション（肯定・共感・技術や経験に対する興味）を添えてください。\n\n"
                        "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
                        "{\n"
                        '    "feedback_intro": "回答への一言リアクション・評価（1〜2文）",\n'
                        '    "question": "深掘り質問の文章"\n'
                        "}"
                    )
                    prompt = json.dumps({
                        "es_pr": st.session_state.es_pr,
                        "job_type": st.session_state.job_type,
                        "question_1": st.session_state.question_1,
                        "answer_1": st.session_state.user_answer_1
                    }, ensure_ascii=False)
                    
                    with st.spinner("AI面接官があなたの回答を評価し、深掘り質問を構成しています..."):
                        try:
                            response = call_gemini(system_instruction, prompt, st.session_state.api_key)
                            res_json = json.loads(response)
                            feedback_intro = res_json.get("feedback_intro", "")
                            deep_dive_txt = res_json.get("question", "")
                        except Exception as e:
                            st.warning(f"AIでの深掘り質問生成に失敗したため、モックデータで代替します。({e})")
                            st.session_state.mode = "MOCK"
                
                # --- モックモード時の深掘り質問生成 ---
                if not deep_dive_txt:
                    es = st.session_state.es_pr
                    ans = st.session_state.user_answer_1
                    keywords = ["行動力", "計画性", "リーダーシップ", "コミュニケーション", "開発", "プロトタイプ", "解決"]
                    selected_kw = "行動力"
                    for kw in keywords:
                        if kw in es or kw in ans:
                            selected_kw = kw
                            break
                    feedback_intro = f"ご回答ありがとうございます、{st.session_state.name}さん。ご自身の強みである「{selected_kw}」を意識して、自発的に取り組まれている様子がよく伝わりました。"
                    deep_dive_txt = f"それでは、その「{selected_kw}」を発揮した活動の中で、直面した「最も大きな困難」と、それをどのように乗り越えたかについて詳しく教えていただけますか？"
                
                st.session_state.deep_dive_text = f"{feedback_intro}\n\n{deep_dive_txt}"
                deep_dive_tts = f"{feedback_intro} {deep_dive_txt}"
                
                # 音声ファイル生成
                timestamp = int(time.time())
                filename = f"temp_audio_q2_{timestamp}.mp3"
                
                with st.spinner("面接官が質問を考えています..."):
                    success = generate_tts(deep_dive_tts, filename)
                    if success:
                        st.session_state.deep_dive_audio_path = filename
                    st.session_state.step = "DEEP_DIVE"
                    st.rerun()
                    
        st.markdown('</div>', unsafe_allow_html=True)

# -----------------
# 3. DEEP_DIVE フェーズ（第二問回答）
# -----------------
elif st.session_state.step == "DEEP_DIVE":
    st.info("👁️ 視線トラッキング中：面接官（カメラ）を見ながら、回答文をタイピングしてください。")
    
    col1, col2 = st.columns([1, 2], gap="large")
    
    with col1:
        st.markdown('<div class="interviewer-panel">', unsafe_allow_html=True)
        if os.path.exists(avatar_path):
            st.image(avatar_path, width='stretch')
        else:
            st.markdown("""
            <div class="avatar-wrapper">
                <div class="avatar-img" style="background: #333; display: flex; align-items: center; justify-content: center;">👤</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown('<h3>面接官 ナナミ</h3>', unsafe_allow_html=True)
        st.markdown(f'<div class="status-badge" style="background:rgba(108, 92, 231, 0.15); color:#a29bfe; border: 1px solid rgba(108, 92, 231, 0.3);">💼 {st.session_state.job_type}面接</div>', unsafe_allow_html=True)
        st.markdown('<div class="status-badge status-speaking">🔊 話しています</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col2:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("🎤 面接官からの質問（深掘り）")
        
        st.markdown(f"""
        <div class="chat-bubble interviewer-bubble">
            <strong>ナナミ:</strong><br>
            {st.session_state.deep_dive_text.replace('\n', '<br>')}
        </div>
        """, unsafe_allow_html=True)
        
        # 音声再生
        if st.session_state.deep_dive_audio_path and os.path.exists(st.session_state.deep_dive_audio_path):
            st.markdown('<div class="audio-container">', unsafe_allow_html=True)
            st.audio(st.session_state.deep_dive_audio_path, format="audio/mp3", autoplay=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown("<hr style='border: 0.5px solid rgba(255,255,255,0.1)'>", unsafe_allow_html=True)
        st.subheader("✍️ あなたの回答（深掘りに対する回答）")
        
        user_ans_2 = st.text_area(
            "ここに回答を入力してください（タイピング）",
            placeholder="例: 最大の困難は、個人開発で外部APIの連携エラーの解決に何日も詰まってしまったことです。しかし、公式ドキュメントやGitHub of Issueを読み漁り、オープンコミュニティに英語で質問を投稿するなどしてエラーを解消し、最終的にアプリを完成させることができました。",
            height=150
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("回答を送信して評価へ進む"):
            if not user_ans_2.strip():
                st.warning("回答を入力してください。")
            else:
                st.session_state.user_answer_2 = user_ans_2.strip()
                
                # 視線トラッキングの停止とタイムラプス動画の出力
                if "recorder" in st.session_state:
                    with st.spinner("カメラをオフにし、結果の解析を行っています..."):
                        st.session_state.recorder.stop()
                        ts = int(time.time())
                        # ブラウザでの再生互換性確保のため、.mp4ではなく.webm形式でタイムラプス動画を出力します
                        video_fn = f"temp_gaze_timelapse_{ts}.webm"
                        map_fn = f"temp_gaze_map_{ts}.png"
                        
                        # 静止画の生成は高速なので同期で実行
                        st.session_state.recorder.generate_gaze_map(map_fn)
                        
                        st.session_state.gaze_video_path = video_fn
                        st.session_state.gaze_map_path = map_fn
                        
                        # 動画ファイルの書き出しを非同期でバックグラウンド実行
                        t = threading.Thread(
                            target=st.session_state.recorder.save_timelapse,
                            args=(video_fn,)
                        )
                        t.daemon = True
                        t.start()
                        st.session_state.gaze_video_thread = t
                        
                        # 視線安定度スコアを動的計算 (まばたき・検出エラー除外)
                        gps = st.session_state.recorder.gaze_points
                        if gps:
                            total_frames = len(gps)
                            valid_face_count = sum(1 for gp in gps if gp.get("is_valid", True))
                            
                            # 有効フレーム (顔が正しく認識され、かつまばたきをしていないフレーム)
                            valid_gaze_frames = [gp for gp in gps if gp.get("is_valid", True) and not gp.get("is_blink", False)]
                            
                            if len(valid_gaze_frames) > 0:
                                away_count = sum(1 for gp in valid_gaze_frames if gp.get("looking_away", False))
                                st.session_state.eye_contact_score = int((1 - away_count / len(valid_gaze_frames)) * 100)
                            else:
                                st.session_state.eye_contact_score = 0
                                
                            # 有効に顔を認識できた割合が全体の50%未満の場合、警告フラグを設定
                            if total_frames > 0 and (valid_face_count / total_frames) < 0.5:
                                st.session_state.gaze_measurement_warning = True
                            else:
                                st.session_state.gaze_measurement_warning = False
                        else:
                            st.session_state.eye_contact_score = 0
                            st.session_state.gaze_measurement_warning = True
                
                eval_json = None
                
                # --- AIモード時の総合評価生成 ---
                if st.session_state.mode == "AI":
                    system_instruction = (
                        "あなたは優秀なキャリアアドバイザー、および企業の採用面接官（名前：ナナミ）です。学生のエントリーシート（ES）、志望職種、および面接の対話ログを元に、総合的な面接の評価レポートを作成してください。\n\n"
                        "以下の項目について評価してください：\n"
                        "1. consistency_score (0〜100点): 回答の一貫性。ESの内容と実際の回答が矛盾なく繋がっているか。\n"
                        "2. content_quality_score (0〜100点): 回答の適切さ・具体性。エピソードの具体性や課題解決の深さ、職種へのマッチ度。\n\n"
                        "評価に基づき、総合スコア（0〜100点）と総合判定ランク（S, A, B, Cのいずれか）を決定してください。\n"
                        "また、全体の総評（会話の一貫性や強みがアピールできていた点へのフィードバック）と、今後の具体的な改善アドバイスを記述してください。\n\n"
                        "出力フォーマットは必ず以下のJSONフォーマットのみにしてください（他の余計な文は一切含めないでください）：\n"
                        "{\n"
                        '    "overall_score": 総合スコア（数値）,\n'
                        '    "rank": "総合判定ランク（文字列：S、A、B、Cのいずれか）",\n'
                        '    "consistency_score": 一貫性スコア（数値）,\n'
                        '    "content_quality_score": 適切さスコア（数値）,\n'
                        '    "evaluation_summary": "面接官からの総評・フィードバック内容",\n'
                        '    "improvement_advice": "具体的な改善アドバイス内容"\n'
                        "}"
                    )
                    
                    prompt = json.dumps({
                        "es_pr": st.session_state.es_pr,
                        "job_type": st.session_state.job_type,
                        "conversation_log": [
                            {"speaker": "interviewer", "text": st.session_state.question_1},
                            {"speaker": "student", "text": st.session_state.user_answer_1},
                            {"speaker": "interviewer", "text": st.session_state.deep_dive_text},
                            {"speaker": "student", "text": st.session_state.user_answer_2}
                        ]
                    }, ensure_ascii=False)
                    
                    with st.spinner("AI面接官が全体の回答を分析し、評価レポートをまとめています..."):
                        try:
                            response = call_gemini(system_instruction, prompt, st.session_state.api_key)
                            eval_json = json.loads(response)
                        except Exception as e:
                            st.warning(f"AIでの評価生成に失敗したため、モックデータで代替します。({e})")
                            st.session_state.mode = "MOCK"
                
                # --- AI評価の取得またはモックデータの生成 ---
                if eval_json:
                    st.session_state.overall_score = eval_json.get("overall_score", 85)
                    st.session_state.rank = eval_json.get("rank", "A")
                    st.session_state.consistency_score = eval_json.get("consistency_score", 80)
                    st.session_state.content_quality_score = eval_json.get("content_quality_score", 85)
                    
                    summary = eval_json.get("evaluation_summary", "")
                    advice = eval_json.get("improvement_advice", "")
                    
                    st.session_state.eval_text = (
                        f"お疲れ様でした、{st.session_state.name}さん！非常に実りある面接でした。\n\n"
                        f"【総評】\n"
                        f"{summary}\n\n"
                        f"【今後の改善アドバイス】\n"
                        f"{advice}"
                    )
                else:
                    st.session_state.overall_score = 88
                    st.session_state.rank = "A"
                    st.session_state.consistency_score = 90
                    st.session_state.content_quality_score = 85
                    st.session_state.eval_text = (
                        f"お疲れ様でした、{st.session_state.name}さん！非常に熱意の伝わる素晴らしい面接でした。\n\n"
                        f"【総評】\n"
                        f"エントリーシートでアピールされていた強みと、実際の質問回答内容に強い一貫性があります。具体例も伴っており説得力があります。\n\n"
                        f"【今後の改善アドバイス】\n"
                        f"さらに評価を高めるためには、行動の動機（なぜそれをしようと思ったのか）や、活動を通じて得られた学びをどう活かすかについて少し言及を加えると良いでしょう。"
                    )
                
                eval_tts = f"面接練習お疲れ様でした。あなたのアピールポイントと改善点を含めた詳細な診断評価レポートを作成しましたので、画面をご確認ください。本日はお疲れ様でした！"
                
                # 音声ファイル生成
                timestamp = int(time.time())
                filename = f"temp_audio_eval_{timestamp}.mp3"
                
                with st.spinner("面接官がフィードバックをまとめています..."):
                    success = generate_tts(eval_tts, filename)
                    if success:
                        st.session_state.eval_audio_path = filename
                    st.session_state.step = "EVALUATION"
                    st.rerun()
                    
        st.markdown('</div>', unsafe_allow_html=True)

# -----------------
# 4. EVALUATION フェーズ（評価画面）
# -----------------
elif st.session_state.step == "EVALUATION":
    st.success("🎉 面接のすべてのステップが終了しました！評価レポートを表示します。")
    if st.session_state.get("gaze_measurement_warning", False):
        st.warning("⚠️ 適切に計測できませんでした（カメラ位置や照明を確認してください）")
    
    col_l, col_r = st.columns([1, 2], gap="large")
    
    with col_l:
        st.markdown('<div class="glass-card" style="text-align: center;">', unsafe_allow_html=True)
        st.subheader("📊 診断結果")
        
        st.markdown(f"""
        <div class="rank-container">
            <div class="rank-badge">{st.session_state.rank}</div>
            <div class="rank-label">総合判定 ({st.session_state.overall_score}点)</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 評価基準進行バー
        metrics = [
            {"name": "回答の一貫性 (AI分析)", "val": st.session_state.consistency_score, "color": "linear-gradient(90deg, #ff9f43, #feca57)"},
            {"name": "回答の適切さ (AI分析)", "val": st.session_state.content_quality_score, "color": "linear-gradient(90deg, #ff6b6b, #ff8787)"},
            {"name": "視線の安定度 (実測データ)", "val": st.session_state.eye_contact_score, "color": "linear-gradient(90deg, #2e86de, #54a0ff)"},
            {"name": "笑顔の割合 (表情検知モック)", "val": 85, "color": "linear-gradient(90deg, #10ac84, #1dd1a1)"}
        ]
        
        for m in metrics:
            st.markdown(f"""
            <div class="metric-row">
                <span class="metric-name">{m['name']}</span>
                <span class="metric-val">{m['val']}%</span>
                <div class="metric-bar-bg">
                    <div class="metric-bar-fill" style="width: {m['val']}%; background: {m['color']};"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 面接官アバター
        st.markdown('<div class="interviewer-panel">', unsafe_allow_html=True)
        if os.path.exists(avatar_path):
            st.image(avatar_path, width='stretch')
        else:
            st.markdown("""
            <div class="avatar-wrapper">
                <div class="avatar-img" style="background: #333; display: flex; align-items: center; justify-content: center;">👤</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('<h3>面接官 ナナミ</h3>', unsafe_allow_html=True)
        
        if st.session_state.eval_audio_path and os.path.exists(st.session_state.eval_audio_path):
            st.markdown('<div class="audio-container">', unsafe_allow_html=True)
            st.audio(st.session_state.eval_audio_path, format="audio/mp3", autoplay=True)
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col_r:
        # タブ機能を使って「総合評価」と「視線分析」を切り替え表示
        tab1, tab2 = st.tabs(["💡 総合指導 & ログ", "👁️ 視線トラッキング分析 (タイムラプス)"])
        
        with tab1:
            st.markdown('<div class="glass-card" style="margin-top:15px; border:none; padding:10px; background:transparent;">', unsafe_allow_html=True)
            st.subheader("💡 面接官ナナミからの総評 ＆ 改善指導")
            st.markdown(f"""
            <div class="chat-bubble interviewer-bubble" style="white-space: pre-line; font-size: 1.05rem; border-left-color: #ff007f;">
                {st.session_state.eval_text}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<hr style='border: 0.5px solid rgba(255,255,255,0.1)'>", unsafe_allow_html=True)
            
            st.subheader("📝 本日の面接ログ")
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.02); padding: 20px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05);">
                <p style="color: #a0aec0; margin-bottom: 2px;"><strong>【自己紹介と強みの質問への回答】</strong></p>
                <p style="color: #e2e8f0; font-size: 1rem; border-left: 3px solid #6c5ce7; padding-left: 10px; margin-bottom: 20px;">
                    {st.session_state.user_answer_1}
                </p>
                <p style="color: #a0aec0; margin-bottom: 2px;"><strong>【深掘り質問への回答】</strong></p>
                <p style="color: #e2e8f0; font-size: 1rem; border-left: 3px solid #00cec9; padding-left: 10px;">
                    {st.session_state.user_answer_2}
                </p>
            </div>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with tab2:
            st.markdown('<div class="glass-card" style="margin-top:15px; border:none; padding:10px; background:transparent;">', unsafe_allow_html=True)
            st.markdown('<h3 class="tracking-title">👁️ 視線トラッキング分析タイムラプス</h3>', unsafe_allow_html=True)
            st.write("面接中にカメラから取得した目線の動きを分析した結果です。")
            
            col_v, col_m = st.columns([1, 1], gap="medium")
            
            with col_v:
                st.markdown("##### 🎥 視線タイムラプス動画")
                thread = st.session_state.get("gaze_video_thread")
                if thread and thread.is_alive():
                    with st.spinner("タイムラプス動画を生成中..."):
                        thread.join(timeout=1.0)
                
                if thread and thread.is_alive():
                    st.info("🎥 動画ファイルをエンコード中です。しばらくしてからタブを切り替えるか、ブラウザをリロードしてください。")
                elif st.session_state.gaze_video_path and os.path.exists(st.session_state.gaze_video_path):
                    st.video(st.session_state.gaze_video_path, autoplay=True, loop=True)
                    st.caption("録画された顔の映像に「緑の虹彩マーク」と右上「視線プロットレーダー」が描画されたタイムラプスです。")
                else:
                    st.info("カメラが有効でなかったか、動画の書き込みに失敗したため、動画はありません。")
                    
            with col_m:
                st.markdown("##### 📍 視線移動トレイルマップ")
                if st.session_state.gaze_map_path and os.path.exists(st.session_state.gaze_map_path):
                    st.image(st.session_state.gaze_map_path, use_container_width=True)
                    st.caption("面接開始から終了までの、目線座標の推移を描いたプロットです。線は時間の経過とともに色が変化（パープル側が最新）します。")
                else:
                    st.info("トラッキングデータがないため、マップ画像はありません。")
            
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # リセットボタン
        st.markdown('<div class="reset-btn">', unsafe_allow_html=True)
        if st.button("面接練習を最初からやり直す"):
            cleanup_temp_files()
            st.session_state.step = "SETUP"
            st.session_state.name = ""
            st.session_state.es_pr = ""
            st.session_state.audio_path = ""
            st.session_state.question_1 = ""
            st.session_state.user_answer_1 = ""
            st.session_state.deep_dive_text = ""
            st.session_state.deep_dive_audio_path = ""
            st.session_state.user_answer_2 = ""
            st.session_state.eval_text = ""
            st.session_state.eval_audio_path = ""
            st.session_state.gaze_video_path = ""
            st.session_state.gaze_map_path = ""
            st.session_state.eye_contact_score = 78
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)