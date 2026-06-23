import os
import time
import cv2
import mediapipe as mp
import threading
import numpy as np
from src.utils import log_gaze

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

# 共通描画ユーティリティ：瞳孔のマーキングと目の輪郭線描画
def draw_face_landmarks(frame, landmarks, color, is_blink=False):
    h, w, c = frame.shape
    if not is_blink:
        for idx in [468, 473]:
            pt = landmarks[idx]
            cv2.circle(frame, (int(pt.x * w), int(pt.y * h)), 4, color, -1)
        
        for pts in [[33, 133], [362, 263]]:
            pt1 = landmarks[pts[0]]
            pt2 = landmarks[pts[1]]
            cv2.line(frame, (int(pt1.x * w), int(pt1.y * h)), (int(pt2.x * w), int(pt2.y * h)), color, 1)

# 共通描画ユーティリティ：右上ミニレーダー表示
def draw_radar_overlay(frame, gaze_x_compensated, gaze_y_compensated, is_blink, is_calibrating, looking_away, calibration_frames_count=0):
    h, w, c = frame.shape
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
        dot_color = (255, 165, 0) # オレンジ
        status_text = "BLINK"
    elif is_calibrating:
        dot_color = (255, 255, 0) # イエロー
        status_text = f"CALIB ({calibration_frames_count}/15)"
    else:
        dot_color = (0, 0, 255) if looking_away else (0, 255, 0)
        status_text = "LOOKING AWAY" if looking_away else "LOOKING AT SCREEN"
        
    cv2.circle(frame, (px, py), 5, dot_color, -1)
    cv2.putText(frame, status_text, (radar_x - 10, radar_y + radar_h + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, dot_color, 1)
    return dot_color

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
                            draw_face_landmarks(frame, landmarks, color, is_blink)
                        else:
                            is_valid = False
                            self.trail_points.append(None)
                    except Exception as e:
                        log_gaze(f"[GazeRecorder] Error inside landmarks processing: {e}")
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
                        b = int(202 * (1 - alpha) + 201 * alpha)
                        g = int(40 * (1 - alpha) + 206 * alpha)
                        r = int(121 * (1 - alpha) + 0 * alpha)
                        cv2.line(frame, p1, p2, (b, g, r), 3)
                        
                # 右上レーダー描画
                draw_radar_overlay(
                    frame=frame,
                    gaze_x_compensated=gaze_x_compensated,
                    gaze_y_compensated=gaze_y_compensated,
                    is_blink=is_blink,
                    is_calibrating=is_calibrating,
                    looking_away=looking_away,
                    calibration_frames_count=len(self.calibration_frames)
                )
                
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
        canvas = np.zeros((300, 300, 3), dtype=np.uint8)
        canvas[:] = (25, 20, 35)  # ダークバイオレット
        
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
                
        for gx, gy, gp in points_data:
            pt = (gx, gy)
            color = (0, 0, 255) if gp["looking_away"] else (0, 255, 0)
            cv2.circle(canvas, pt, 4, color, -1)
            
        cv2.putText(canvas, "Green: Looked at Screen", (10, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
        cv2.putText(canvas, "Red: Looked Away", (10, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
        cv2.putText(canvas, f"Points: {len(points_data)}", (10, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        
        cv2.imwrite(output_path, canvas)

def scan_available_cameras():
    available = []
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
    
    frame = cv2.flip(frame, 1)
    h, w, c = frame.shape
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
                draw_face_landmarks(frame, landmarks, (0, 255, 0), is_blink=False)
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        if face_detected:
            return frame_rgb, "SUCCESS: カメラとの接続を確認し、顔および目を正常に検出しました。視線トラッキングの準備は完了しています。"
        else:
            return frame_rgb, "WARNING: カメラ画像は取得できましたが、顔が検出されませんでした。カメラの正面に座り、部屋が暗すぎないか確認してください。"
            
    except Exception as e:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame_rgb, f"WARNING: カメラ画像は取得できましたが、目線解析モデル(MediaPipe)の初期化中にエラーが発生しました ({e})。視線追跡はスキップされ、評価画面では固定値(78%)が表示されますが、面接自体は実施可能です。"

def collect_calibration_sample(camera_index: int, duration: float = 2.0) -> tuple[float, float] | None:
    """カメラから複数フレームの視線データを指定した秒数（duration）取得し、平均的な座標（X, Y）を算出します。"""
    import cv2
    import mediapipe as mp
    import platform
    import time
    
    if platform.system() == "Windows":
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index)
        
    if not cap.isOpened():
        return None
        
    mp_face_mesh = mp.solutions.face_mesh
    gaze_xs = []
    gaze_ys = []
    
    try:
        with mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as face_mesh:
            
            start_time = time.time()
            # 指定された時間ループして有効なサンプルを集める
            while (time.time() - start_time) < duration:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue
                    
                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb_frame)
                
                if results.multi_face_landmarks:
                    landmarks = results.multi_face_landmarks[0].landmark
                    gaze_x, gaze_y, ear, yaw, pitch, is_blink = analyze_face_features(landmarks)
                    
                    if not is_blink:
                        # 補正済みの座標を算出
                        gaze_x_compensated = gaze_x + 0.25 * yaw
                        gaze_y_compensated = gaze_y + 0.25 * (pitch - 0.5)
                        gaze_xs.append(gaze_x_compensated)
                        gaze_ys.append(gaze_y_compensated)
                
                time.sleep(0.04)
    finally:
        cap.release()
        
    if len(gaze_xs) > 0:
        avg_x = sum(gaze_xs) / len(gaze_xs)
        avg_y = sum(gaze_ys) / len(gaze_ys)
        return avg_x, avg_y
    return None
