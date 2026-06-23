import os
import time
import streamlit as st
from src.gemini_interviewer import GeminiInterviewer
from src.database import get_interview_history
from src.tts import generate_tts
from src.utils import TEMP_DIR, cleanup_temp_files
from src.gaze_tracker import (
    GazeRecorder,
    scan_available_cameras,
    analyze_face_features,
    draw_face_landmarks,
    draw_radar_overlay,
    collect_calibration_sample
)

def on_options_dismiss():
    st.session_state.show_options = False

@st.dialog("環境設定・オプション", width="large", on_dismiss=on_options_dismiss)
def show_options_modal():
    st.markdown("システムの動作環境（デバイス、各種機能のオン/オフおよびパラメータ）を調整します。")
    
    st.markdown("### 👁️ 視線・表情検知の設定")
    
    # 「カメラを利用する」トグル
    if "use_camera" not in st.session_state:
        st.session_state.use_camera = True
        
    use_camera = st.toggle("カメラを利用する (視線トラッキング)", value=st.session_state.use_camera, key="toggle_use_camera")
    st.session_state.use_camera = use_camera
    
    if use_camera:
        with st.container(border=True):
            st.subheader("📹 カメラ設定")
            col_cam_sel, col_cam_scan = st.columns([2, 1])
            with col_cam_sel:
                cam_options = st.session_state.available_cameras
                cam_labels = [f"カメラ {i}" for i in cam_options]
                
                default_sel_idx = 0
                if st.session_state.camera_index in cam_options:
                    default_sel_idx = cam_options.index(st.session_state.camera_index)
                
                selected_cam_idx = st.selectbox(
                    "使用するカメラを選択",
                    options=range(len(cam_options)),
                    format_func=lambda x: cam_labels[x],
                    index=default_sel_idx,
                    key="dialog_camera_selectbox"
                )
                st.session_state.camera_index = cam_options[selected_cam_idx]
                
            with col_cam_scan:
                st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                if st.button("🔄 再検出", key="dialog_camera_scan_btn"):
                    with st.spinner("カメラをスキャン中..."):
                        st.session_state.available_cameras = scan_available_cameras()
                        st.rerun()
                        
            st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08); margin: 15px 0;'>", unsafe_allow_html=True)
            
            st.subheader("📐 視線許容範囲の自動調整 (キャリブレーション)")
            
            # セッションにウィザード用の変数を作成
            if "calib_wizard_step" not in st.session_state:
                st.session_state.calib_wizard_step = 1
            if "calib_center_res" not in st.session_state:
                st.session_state.calib_center_res = None
            if "calib_limit_res" not in st.session_state:
                st.session_state.calib_limit_res = None
                
            if st.session_state.calib_wizard_step == 1:
                st.markdown("カメラを実際に見つめて、あなたの目線の動きに合わせた最適な許容範囲を自動計測します。")
                if st.button("📐 自動調整（キャリブレーション）を開始する", use_container_width=True, type="primary", key="btn_start_calib"):
                    st.session_state.calib_wizard_step = 2
                    st.rerun()
                    
            elif st.session_state.calib_wizard_step == 2:
                st.markdown(
                    """
                    <div class="calib-container">
                        <div class="calib-step-indicator">ステップ 2 / 8: 正面注視ターゲット提示</div>
                        <div class="calib-target-wrapper">
                            <div class="calib-target-center"></div>
                        </div>
                        <div style="margin-top: 15px; font-weight: bold; color: #0d9488;">アバター（またはWebカメラ）をまっすぐ正面に見つめてください。</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                col_btn1, col_btn2 = st.columns([2, 1])
                with col_btn1:
                    if st.button("正面サンプリング（データ集め）を開始する", use_container_width=True, key="btn_go_step3", type="primary"):
                        st.session_state.calib_wizard_step = 3
                        st.rerun()
                with col_btn2:
                    if st.button("キャンセル", use_container_width=True, key="btn_cancel_step2"):
                        st.session_state.calib_wizard_step = 1
                        st.rerun()
                        
            elif st.session_state.calib_wizard_step == 3:
                # カウントダウンを同一コンテナ内で表示するためのプレースホルダー
                countdown_placeholder = st.empty()
                for i in range(3, 0, -1):
                    countdown_placeholder.markdown(
                        f"""
                        <div class="calib-container">
                            <div class="calib-step-indicator">ステップ 3 / 8: 正面データ収集（データ集め準備）</div>
                            <div class="calib-target-wrapper">
                                <div class="calib-target-center"></div>
                            </div>
                            <div style="margin-top: 15px; font-size: 2.5rem; font-weight: 800; color: #0d9488;">{i}</div>
                            <div style="margin-top: 5px; font-weight: bold; color: #64748b;">測定開始まで {i} 秒... 画面中央を見つめてください。</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    time.sleep(1.0)
                
                # 測定中の表示に切り替え
                countdown_placeholder.markdown(
                    """
                    <div class="calib-container">
                        <div class="calib-step-indicator">ステップ 3 / 8: 正面データ収集（データ集め中）</div>
                        <div class="calib-target-wrapper">
                            <div class="calib-target-center"></div>
                        </div>
                        <div style="margin-top: 15px; font-weight: bold; color: #0d9488; animation: blink 1s infinite;">● 測定中 (約2秒間)...</div>
                        <div style="margin-top: 5px; font-weight: bold; color: #64748b;">視線を動かさないでください。</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                # 測定開始
                res = collect_calibration_sample(st.session_state.camera_index, duration=2.0)
                countdown_placeholder.empty()
                
                if res:
                    st.session_state.calib_center_res = res
                else:
                    st.session_state.calib_center_res = None
                st.session_state.calib_wizard_step = 4
                st.rerun()
                    
            elif st.session_state.calib_wizard_step == 4:
                st.markdown('<div class="calib-container">', unsafe_allow_html=True)
                st.markdown('<div class="calib-step-indicator">ステップ 4 / 8: 正面データ解析</div>', unsafe_allow_html=True)
                
                res = st.session_state.calib_center_res
                if res:
                    st.markdown(
                        f"""
                        <div style="margin-top: 10px; margin-bottom: 20px;">
                            <span style="color: #0d9488; font-size: 1.2rem; font-weight: bold;">✓ 正面解析完了</span><br>
                            <div style="font-size: 1.1rem; margin-top: 10px;">基準の視線座標が正常に計算されました。</div>
                            <div style="font-size: 1rem; color: #64748b; margin-top: 5px;">中心座標 (X: {res[0]:.3f}, Y: {res[1]:.3f})</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    col_btn1, col_btn2 = st.columns([2, 1])
                    with col_btn1:
                        if st.button("次へ（よそ見限界の調整）", use_container_width=True, key="btn_go_step5", type="primary"):
                            st.session_state.calib_wizard_step = 5
                            st.rerun()
                    with col_btn2:
                        if st.button("もう一度やり直す", use_container_width=True, key="btn_retry_step4"):
                            st.session_state.calib_wizard_step = 2
                            st.session_state.calib_center_res = None
                            st.rerun()
                else:
                    st.markdown(
                        """
                        <div style="margin-top: 10px; margin-bottom: 20px;">
                            <span style="color: #ff7675; font-size: 1.2rem; font-weight: bold;">⚠ 解析失敗</span><br>
                            <div style="font-size: 1.1rem; margin-top: 10px; color: #ff7675;">顔または視線が検出できませんでした。</div>
                            <div style="font-size: 0.9rem; color: #64748b; margin-top: 5px;">部屋の照明を明るくするか、カメラの角度を調整してください。</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    col_btn1, col_btn2 = st.columns([2, 1])
                    with col_btn1:
                        if st.button("もう一度サンプリングする", use_container_width=True, key="btn_retry_step4_err", type="primary"):
                            st.session_state.calib_wizard_step = 2
                            st.session_state.calib_center_res = None
                            st.rerun()
                    with col_btn2:
                        if st.button("キャンセル", use_container_width=True, key="btn_cancel_step4"):
                            st.session_state.calib_wizard_step = 1
                            st.session_state.calib_center_res = None
                            st.rerun()
                            
            elif st.session_state.calib_wizard_step == 5:
                st.markdown(
                    """
                    <div class="calib-container">
                        <div class="calib-step-indicator">ステップ 5 / 8: よそ見ターゲット提示</div>
                        <div class="calib-target-wrapper">
                            <div class="calib-target-away"></div>
                        </div>
                        <div style="margin-top: 15px; font-weight: bold; color: #ff7675;">「これ以上目をそらしたら『よそ見』と判定させたい限界位置（画面の端など）」を見つめてください。</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                col_btn1, col_btn2 = st.columns([2, 1])
                with col_btn1:
                    if st.button("よそ見サンプリング（データ集め）を開始する", use_container_width=True, key="btn_go_step6", type="primary"):
                        st.session_state.calib_wizard_step = 6
                        st.rerun()
                with col_btn2:
                    if st.button("戻る", use_container_width=True, key="btn_back_step5"):
                        st.session_state.calib_wizard_step = 4
                        st.rerun()
                        
            elif st.session_state.calib_wizard_step == 6:
                # カウントダウンを同一コンテナ内で表示するためのプレースホルダー
                countdown_placeholder = st.empty()
                for i in range(3, 0, -1):
                    countdown_placeholder.markdown(
                        f"""
                        <div class="calib-container">
                            <div class="calib-step-indicator">ステップ 6 / 8: よそ見データ収集（データ集め準備）</div>
                            <div class="calib-target-wrapper">
                                <div class="calib-target-away"></div>
                            </div>
                            <div style="margin-top: 15px; font-size: 2.5rem; font-weight: 800; color: #ff7675;">{i}</div>
                            <div style="margin-top: 5px; font-weight: bold; color: #64748b;">測定開始まで {i} 秒... 画面左端を見つめてください。</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    time.sleep(1.0)
                
                # 測定中の表示に切り替え
                countdown_placeholder.markdown(
                    """
                    <div class="calib-container">
                        <div class="calib-step-indicator">ステップ 6 / 8: よそ見データ収集（データ集め中）</div>
                        <div class="calib-target-wrapper">
                            <div class="calib-target-away"></div>
                        </div>
                        <div style="margin-top: 15px; font-weight: bold; color: #ff7675; animation: blink 1s infinite;">● 測定中 (約2秒間)...</div>
                        <div style="margin-top: 5px; font-weight: bold; color: #64748b;">視線を動かさないでください。</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                # 測定開始
                res = collect_calibration_sample(st.session_state.camera_index, duration=2.0)
                countdown_placeholder.empty()
                
                if res:
                    st.session_state.calib_limit_res = res
                else:
                    st.session_state.calib_limit_res = None
                st.session_state.calib_wizard_step = 7
                st.rerun()
                    
            elif st.session_state.calib_wizard_step == 7:
                st.markdown('<div class="calib-container">', unsafe_allow_html=True)
                st.markdown('<div class="calib-step-indicator">ステップ 7 / 8: よそ見データ解析</div>', unsafe_allow_html=True)
                
                res = st.session_state.calib_limit_res
                if res:
                    st.markdown(
                        f"""
                        <div style="margin-top: 10px; margin-bottom: 20px;">
                            <span style="color: #ff7675; font-size: 1.2rem; font-weight: bold;">✓ よそ見解析完了</span><br>
                            <div style="font-size: 1.1rem; margin-top: 10px;">よそ見限界の視線座標が正常に計算されました。</div>
                            <div style="font-size: 1rem; color: #64748b; margin-top: 5px;">限界座標 (X: {res[0]:.3f}, Y: {res[1]:.3f})</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    col_btn1, col_btn2 = st.columns([2, 1])
                    with col_btn1:
                        if st.button("次へ（結果の確認・適用）", use_container_width=True, key="btn_go_step8", type="primary"):
                            st.session_state.calib_wizard_step = 8
                            st.rerun()
                    with col_btn2:
                        if st.button("もう一度やり直す", use_container_width=True, key="btn_retry_step7"):
                            st.session_state.calib_wizard_step = 5
                            st.session_state.calib_limit_res = None
                            st.rerun()
                else:
                    st.markdown(
                        """
                        <div style="margin-top: 10px; margin-bottom: 20px;">
                            <span style="color: #ff7675; font-size: 1.2rem; font-weight: bold;">⚠ 解析失敗</span><br>
                            <div style="font-size: 1.1rem; margin-top: 10px; color: #ff7675;">顔または視線が検出できませんでした。</div>
                            <div style="font-size: 0.9rem; color: #64748b; margin-top: 5px;">部屋の照明を明るくするか、カメラの角度を調整してください。</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    col_btn1, col_btn2 = st.columns([2, 1])
                    with col_btn1:
                        if st.button("もう一度サンプリングする", use_container_width=True, key="btn_retry_step7_err", type="primary"):
                            st.session_state.calib_wizard_step = 5
                            st.session_state.calib_limit_res = None
                            st.rerun()
                    with col_btn2:
                        if st.button("キャンセル", use_container_width=True, key="btn_cancel_step7"):
                            st.session_state.calib_wizard_step = 1
                            st.session_state.calib_limit_res = None
                            st.rerun()
                            
            elif st.session_state.calib_wizard_step == 8:
                st.markdown('<div class="calib-container">', unsafe_allow_html=True)
                st.markdown('<div class="calib-step-indicator">ステップ 8 / 8: 結果出力・許容値更新</div>', unsafe_allow_html=True)
                
                if not st.session_state.calib_center_res or not st.session_state.calib_limit_res:
                    st.warning("キャリブレーションデータが不足しています。最初からやり直してください。")
                    if st.button("最初に戻る", use_container_width=True):
                        st.session_state.calib_wizard_step = 1
                        st.session_state.calib_center_res = None
                        st.session_state.calib_limit_res = None
                        st.rerun()
                else:
                    cx, cy = st.session_state.calib_center_res
                    lx, ly = st.session_state.calib_limit_res
                    
                    h_diff = abs(lx - cx)
                    v_diff = abs(ly - cy)
                    
                    # 安全制限つきマージン（極端な値を防止）
                    h_margin = max(0.04, min(0.22, h_diff))
                    v_margin = max(0.04, min(0.22, v_diff))
                    
                    new_h_range = (round(cx - h_margin, 2), round(cx + h_margin, 2))
                    new_v_range = (round(cy - v_margin, 2), round(cy + v_margin, 2))
                    
                    st.markdown(
                        f"""
                        <div style="text-align: left; width: 100%; padding: 10px 20px;">
                            <div style="font-weight: bold; font-size: 1.1rem; color: #0d9488; margin-bottom: 10px;">📐 計算されたキャリブレーション結果</div>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 6px 0; color: #475569;">正面中心点 (X, Y)</td>
                                    <td style="padding: 6px 0; text-align: right; font-weight: bold;">({cx:.2f}, {cy:.2f})</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; color: #475569;">よそ見限界点 (X, Y)</td>
                                    <td style="padding: 6px 0; text-align: right; font-weight: bold;">({lx:.2f}, {ly:.2f})</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; color: #475569;">計算された左右許容幅</td>
                                    <td style="padding: 6px 0; text-align: right; font-weight: bold; color: #0d9488;">±{h_margin:.2f}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; color: #475569;">計算された上下許容幅</td>
                                    <td style="padding: 6px 0; text-align: right; font-weight: bold; color: #0d9488;">±{v_margin:.2f}</td>
                                </tr>
                            </table>
                            <div style="margin-top: 15px; padding: 10px; background: rgba(13, 148, 136, 0.05); border: 1px solid rgba(13, 148, 136, 0.2); border-radius: 8px;">
                                <div style="font-weight: bold; color: #0d9488; font-size: 0.95rem;">🎯 新しい許容範囲設定:</div>
                                <div style="font-size: 0.9rem; margin-top: 4px;">左右: <b>{new_h_range[0]} - {new_h_range[1]}</b> / 上下: <b>{new_v_range[0]} - {new_v_range[1]}</b></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    col_btn1, col_btn2 = st.columns([2, 1])
                    with col_btn1:
                        if st.button("💾 この設定を適用して終了する", use_container_width=True, key="btn_apply_calib_finish", type="primary"):
                            st.session_state.h_range = new_h_range
                            st.session_state.v_range = new_v_range
                            
                            st.session_state.calib_wizard_step = 1
                            st.session_state.calib_center_res = None
                            st.session_state.calib_limit_res = None
                            
                            st.session_state.show_options = False
                            st.toast("🎯 新しい視線許容範囲を適用しました！")
                            st.rerun()
                    with col_btn2:
                        if st.button("破棄してやり直す", use_container_width=True, key="btn_reset_wizard"):
                            st.session_state.calib_wizard_step = 1
                            st.session_state.calib_center_res = None
                            st.session_state.calib_limit_res = None
                            st.rerun()
                    
            st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08); margin: 15px 0;'>", unsafe_allow_html=True)
            
            st.subheader("⚙️ 視線判定しきい値の調整")
            st.markdown("数値範囲を狭くすると判定が厳しくなり、広くすると甘くなります。")
            
            h_range = st.slider(
                "水平方向の許容範囲 (左右の目線そらしの感度)",
                min_value=0.20,
                max_value=0.80,
                value=st.session_state.h_range,
                step=0.01,
                key="dialog_h_range_slider"
            )
            st.session_state.h_range = h_range
            
            v_range = st.slider(
                "垂直方向の許容範囲 (上下の目線そらしの感度)",
                min_value=0.20,
                max_value=0.80,
                value=st.session_state.v_range,
                step=0.01,
                key="dialog_v_range_slider"
            )
            st.session_state.v_range = v_range
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # リアルタイム診断モードのトグル
            live_cam_active = st.checkbox("📹 リアルタイム診断モードを開始する (診断プレビュー)", value=False, key="dialog_live_cam_checkbox")
            
            if live_cam_active:
                import cv2
                import mediapipe as mp
                import platform
                if platform.system() == "Windows":
                    cap = cv2.VideoCapture(st.session_state.camera_index, cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(st.session_state.camera_index)
                if not cap.isOpened():
                    st.error("カメラデバイスを開くことができませんでした。")
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
                        st.warning(f"目線解析モデルの初期化に失敗しました: {e}")
                    
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
                                            gaze_x_compensated = gaze_x + 0.25 * yaw
                                            gaze_y_compensated = gaze_y + 0.25 * (pitch - 0.5)
                                            
                                            if not (st.session_state.h_range[0] <= gaze_x_compensated <= st.session_state.h_range[1]) or not (st.session_state.v_range[0] <= gaze_y_compensated <= st.session_state.v_range[1]):
                                                looking_away = True
                                                
                                            pt_left = landmarks[468]
                                            pt_right = landmarks[473]
                                            mx = int((pt_left.x + pt_right.x) / 2.0 * w)
                                            my = int((pt_left.y + pt_right.y) / 2.0 * h)
                                            trail_points.append((mx, my))
                                                
                                        if is_blink:
                                            color = (255, 165, 0)
                                        else:
                                            color = (0, 0, 255) if looking_away else (0, 255, 0)
                                            
                                        draw_face_landmarks(frame, landmarks, color, is_blink)
                                    else:
                                        trail_points.append(None)
                                except Exception:
                                    trail_points.append(None)
                            else:
                                trail_points.append(None)
                                
                            if len(trail_points) > 40:
                                trail_points.pop(0)
                                
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
                            
                            dot_color = draw_radar_overlay(
                                frame=frame,
                                gaze_x_compensated=gaze_x_compensated,
                                gaze_y_compensated=gaze_y_compensated,
                                is_blink=is_blink,
                                is_calibrating=False,
                                looking_away=looking_away
                            )
                            
                            if is_blink:
                                status_txt = "BLINKING"
                            else:
                                status_txt = "LOOKING AWAY (OUT OF RANGE)" if looking_away else "LOOKING AT SCREEN (OK)"
                            cv2.putText(frame, status_txt, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, dot_color, 2)
                            cv2.putText(frame, f"Gaze X: {gaze_x_compensated:.3f} (Limit: {st.session_state.h_range[0]:.2f} - {st.session_state.h_range[1]:.2f})", (15, h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                            cv2.putText(frame, f"Gaze Y: {gaze_y_compensated:.3f} (Limit: {st.session_state.v_range[0]:.2f} - {st.session_state.v_range[1]:.2f})", (15, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                            cv2.rectangle(frame, (0, 0), (w, h), dot_color, 6)
                            
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            frame_placeholder.image(frame_rgb, caption="リアルタイム目線追跡プレビュー", use_container_width=True)
                            time.sleep(0.04)
                    finally:
                        if face_mesh is not None:
                            face_mesh.close()
                        cap.release()
                        frame_placeholder.empty()

    # 将来的な拡張機能（音声認識など）のプレースホルダー
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🎙️ 音声・対話設定 (将来の拡張用)")
    with st.container(border=True):
        st.toggle("音声認識を利用する (リアルタイム文字起こしと回答分析)", value=False, disabled=True, help="今後のアップデートで追加予定の機能です。")
        st.caption("※ 現在はご利用いただけません。")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("設定を閉じる", use_container_width=True, key="dialog_close_btn"):
        st.session_state.show_options = False
        st.rerun()

def render_setup_view(avatar_path: str):
    # 2カラムレイアウトで表示
    col_setup_left, col_setup_right = st.columns([1, 1], gap="large")
    
    with col_setup_left:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("📝 エントリーシート（ES）の入力")
        
        name_input = st.text_input("お名前", placeholder="例: 面接 太郎", value=st.session_state.name if st.session_state.name else "プロト 太郎")
        final_academic_background = st.text_input("最終学歴", placeholder="例: 〇〇大学 〇〇学部 〇〇学科", value=st.session_state.final_academic_background)
        
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

        tech_skills = st.text_area("技術スキル (カンマ区切り)", placeholder="例: Java, SQL, Python, Git", value=st.session_state.tech_skills, height=80)
        qualifications = st.text_area("資格名 (改行またはカンマ区切り)", placeholder="例: 基本情報技術者, 応用情報技術者", value=st.session_state.qualifications, height=80)
        
        st.write("**経験工程 (複数選択可)**")
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            p_req = st.checkbox("要件定義", value="要件定義" in st.session_state.experienced_processes)
            p_basic = st.checkbox("基本設計", value="基本設計" in st.session_state.experienced_processes)
        with col_p2:
            p_detail = st.checkbox("詳細設計", value="詳細設計" in st.session_state.experienced_processes)
            p_code = st.checkbox("実装・プログラミング", value="実装・プログラミング" in st.session_state.experienced_processes)
        with col_p3:
            p_test = st.checkbox("テスト・単体検証", value="テスト・単体検証" in st.session_state.experienced_processes)
            p_maint = st.checkbox("運用保守", value="運用保守" in st.session_state.experienced_processes)
        
        selected_processes = []
        if p_req: selected_processes.append("要件定義")
        if p_basic: selected_processes.append("基本設計")
        if p_detail: selected_processes.append("詳細設計")
        if p_code: selected_processes.append("実装・プログラミング")
        if p_test: selected_processes.append("テスト・単体検証")
        if p_maint: selected_processes.append("運用保守")
        
        experienced_processes_content = st.text_area(
            "経験した工程の具体的な内容",
            placeholder="例: Javaを用いたWebAPIの実装工程を担当し、単体テスト仕様書の作成および単体テストの実行を行いました。",
            value=st.session_state.experienced_processes_content,
            height=120
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with col_setup_right:
        st.markdown('<div class="glass-card" style="height: 100%;">', unsafe_allow_html=True)
        st.subheader("⚙️ 動作・API設定")
        
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
                # インタビュアークラスのインスタンス化または更新
                if st.session_state.api_key or os.environ.get("GEMINI_API_KEY"):
                    st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key)
            with col_btn:
                st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True) # 余白合わせ
                if st.button("🔑 接続テスト"):
                    with st.spinner("API接続確認中..."):
                        if not st.session_state.get("interviewer"):
                            st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key)
                        success, msg = st.session_state.interviewer.verify_connection()
                        st.session_state.api_test_result = {"success": success, "msg": msg}
            
            # API接続テスト結果の表示
            if st.session_state.api_test_result:
                res = st.session_state.api_test_result
                if res["success"]:
                    st.success(res["msg"])
                else:
                    st.error(res["msg"])
        else:
            st.info("オフラインデモ用のモックモードで動作します。APIキーは不要です。")
            
        st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08); margin: 15px 0;'>", unsafe_allow_html=True)
        if "show_options" not in st.session_state:
            st.session_state.show_options = False
        if st.button("📹 カメラ・視線判定オプションを開く", use_container_width=True, key="setup_open_options_btn"):
            st.session_state.show_options = True
            st.rerun()
            
        st.markdown('</div>', unsafe_allow_html=True)

    # 過去の面接履歴の表示
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("📊 過去の面接履歴")
    if name_input.strip():
        history = get_interview_history(name_input.strip())
        if history:
            st.markdown(f"**{name_input.strip()}** さんの過去の面接結果 ({len(history)}件) です。クリックして詳細を展開できます。")
            for item in history:
                created_at = item.get("created_at", "")
                job_type = item.get("job_type", "")
                overall_score = item.get("overall_score", 0)
                rank = item.get("rank", "D")
                
                expander_label = f"📅 {created_at} | 職種: {job_type} | 判定: 【{rank}】 {overall_score}点"
                with st.expander(expander_label):
                    had_camera = item.get("use_camera", 1) == 1
                    
                    if had_camera:
                        h_col1, h_col2, h_col3 = st.columns(3)
                        with h_col1:
                            st.metric("一貫性", f"{item.get('consistency_score', 0)}点")
                        with h_col2:
                            st.metric("回答品質", f"{item.get('content_quality_score', 0)}点")
                        with h_col3:
                            st.metric("視線安定度", f"{item.get('eye_contact_score', 0)}点")
                    else:
                        h_col1, h_col2 = st.columns(2)
                        with h_col1:
                            st.metric("一貫性", f"{item.get('consistency_score', 0)}点")
                        with h_col2:
                            st.metric("回答品質", f"{item.get('content_quality_score', 0)}点")
                    
                    st.markdown("**🤖 面接官ナナミからの評価フィードバック:**")
                    st.info(item.get("eval_text", ""))
                    
                    ans_col1, ans_col2 = st.columns(2)
                    with ans_col1:
                        st.markdown("**💬 第1問回答:**")
                        st.write(item.get("user_answer_1", "") if item.get("user_answer_1") else "（記録なし）")
                    with ans_col2:
                        st.markdown("**💬 第2問回答 (深掘り):**")
                        st.write(item.get("user_answer_2", "") if item.get("user_answer_2") else "（記録なし）")
        else:
            st.info(f"**{name_input.strip()}** さんの過去の面接履歴は見つかりませんでした。最初の面接練習を開始して履歴を記録しましょう！")
    else:
        st.warning("お名前を入力すると、過去の履歴が表示されます。")

    # 開始ボタンを全幅で配置（設定オプションは動作・API設定カード内へ移動）
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 面接練習を開始する", use_container_width=True):
        if not name_input.strip() or not st.session_state.job_type.strip():
            st.warning("お名前、希望する職種を入力してください。")
        elif st.session_state.mode == "AI" and not st.session_state.api_key.strip():
            st.error("AIモードで実行するには、APIキーを設定してください。")
        else:
            cleanup_temp_files()
            
            # ES情報をセッションステートに保存
            st.session_state.name = name_input.strip()
            st.session_state.final_academic_background = final_academic_background.strip()
            st.session_state.tech_skills = tech_skills.strip()
            st.session_state.qualifications = qualifications.strip()
            st.session_state.experienced_processes = selected_processes
            st.session_state.experienced_processes_content = experienced_processes_content.strip()
            
            # 汎用の自己PR要約テキストを作成
            processes_str = ", ".join(selected_processes) if selected_processes else "なし"
            st.session_state.es_pr = (
                f"学歴: {st.session_state.final_academic_background}\n"
                f"スキル: {st.session_state.tech_skills}\n"
                f"資格: {st.session_state.qualifications}\n"
                f"経験工程: {processes_str}\n"
                f"工程詳細: {st.session_state.experienced_processes_content}"
            )
            
            st.session_state.es_data = {
                "name": st.session_state.name,
                "final_academic_background": st.session_state.final_academic_background,
                "tech_skills": st.session_state.tech_skills,
                "qualifications": st.session_state.qualifications,
                "experienced_processes": st.session_state.experienced_processes,
                "experienced_processes_content": st.session_state.experienced_processes_content,
                "job_type": st.session_state.job_type
            }
            
            # 視線トラッキングスレッドの開始 (Webカメラ起動、カメラが有効な場合のみ)
            if st.session_state.get("use_camera", True):
                st.session_state.recorder = GazeRecorder(
                    camera_index=st.session_state.camera_index,
                    h_range=st.session_state.h_range,
                    v_range=st.session_state.v_range
                )
                st.session_state.recorder.start()
            else:
                st.session_state.recorder = None
            
            q1_text = ""
            
            # --- 第一問生成 ---
            if not st.session_state.get("interviewer"):
                st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
            else:
                st.session_state.interviewer.mode = st.session_state.mode
                st.session_state.interviewer.api_key = st.session_state.api_key
                
            with st.spinner("AI面接官がエントリーシートを読み込み、質問の流れを構成しています..."):
                q1_text = st.session_state.interviewer.generate_first_question(st.session_state.es_data)
            
            st.session_state.question_1 = q1_text
            
            # 音声ファイルを生成
            timestamp = int(time.time())
            filename = os.path.join(TEMP_DIR, f"temp_audio_q1_{timestamp}.mp3")
            
            with st.spinner("面接官の音声（TTS）を生成中..."):
                success = generate_tts(q1_text, filename)
                if success:
                    st.session_state.audio_path = filename
                st.session_state.step = "QUESTION"
                st.rerun()

    if st.session_state.get("show_options", False):
        show_options_modal()
