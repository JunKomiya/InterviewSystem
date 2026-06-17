import os
import sys
import mediapipe as mp

# 環境変数のAPIキーに改行などが含まれる場合のクレンジング
if "GEMINI_API_KEY" in os.environ:
    os.environ["GEMINI_API_KEY"] = os.environ["GEMINI_API_KEY"].strip()

import streamlit as st
import asyncio
import glob
import time
import json
import cv2
import threading
from gemini_interviewer import GeminiInterviewer
from tts import generate_tts
from database import save_interview_result, get_interview_history
from gaze_tracker import (
    GazeRecorder,
    scan_available_cameras,
    test_camera_capture,
    analyze_face_features,
    draw_face_landmarks,
    draw_radar_overlay
)

# 一時ファイルフォルダの設定
TEMP_DIR = "temp_assets"
os.makedirs(TEMP_DIR, exist_ok=True)

# CSSの読み込み
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ページ基本設定
st.set_page_config(
    page_title="AI面接練習システム | プロトタイプ",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 起動直後にCSSをロード
load_css()

# ログを確実にファイル出力するためのヘルパー関数
def log_gaze(msg: str):
    try:
        with open("gaze_recorder.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass



# 一時ファイルのクリーンアップ処理
def cleanup_temp_files():
    # 音声ファイル
    for f in glob.glob(os.path.join(TEMP_DIR, "temp_audio_*.mp3")):
        try: os.remove(f)
        except Exception: pass
    # ビデオファイル（webmとmp4）
    for ext in ["*.webm", "*.mp4"]:
        for f in glob.glob(os.path.join(TEMP_DIR, f"temp_gaze_timelapse_{ext}")):
            try: os.remove(f)
            except Exception: pass
    # マップ画像ファイル
    for f in glob.glob(os.path.join(TEMP_DIR, "temp_gaze_map_*.png")):
        try: os.remove(f)
        except Exception: pass

# セッション状態の初期化と初回ローディング画面
if "initialized" not in st.session_state:
    st.markdown("""
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
    st.session_state.interviewer = None
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
                                        
                                    draw_face_landmarks(frame, landmarks, color, is_blink)
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
                        
                        # 右上レーダー描画
                        dot_color = draw_radar_overlay(
                            frame=frame,
                            gaze_x_compensated=gaze_x_compensated,
                            gaze_y_compensated=gaze_y_compensated,
                            is_blink=is_blink,
                            is_calibrating=False,
                            looking_away=looking_away
                        )
                        
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
                    h_col1, h_col2, h_col3 = st.columns(3)
                    with h_col1:
                        st.metric("一貫性", f"{item.get('consistency_score', 0)}点")
                    with h_col2:
                        st.metric("回答品質", f"{item.get('content_quality_score', 0)}点")
                    with h_col3:
                        st.metric("視線安定度", f"{item.get('eye_contact_score', 0)}点")
                    
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
            
            # --- 第一問生成 ---
            if not st.session_state.get("interviewer"):
                st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
            else:
                st.session_state.interviewer.mode = st.session_state.mode
                st.session_state.interviewer.api_key = st.session_state.api_key
                
            with st.spinner("AI面接官がエントリーシートを読み込み、質問の流れを構成しています..."):
                q1_text = st.session_state.interviewer.generate_first_question(
                    name=st.session_state.name,
                    job_type=st.session_state.job_type,
                    es_pr=st.session_state.es_pr
                )
            
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
                
                # --- 深掘り質問生成 ---
                if not st.session_state.get("interviewer"):
                    st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
                else:
                    st.session_state.interviewer.mode = st.session_state.mode
                    st.session_state.interviewer.api_key = st.session_state.api_key

                with st.spinner("AI面接官があなたの回答を評価し、深掘り質問を構成しています..."):
                    feedback_intro, deep_dive_txt = st.session_state.interviewer.generate_deep_dive_question(
                        es_pr=st.session_state.es_pr,
                        job_type=st.session_state.job_type,
                        question_1=st.session_state.question_1,
                        answer_1=st.session_state.user_answer_1
                    )
                
                st.session_state.deep_dive_text = f"{feedback_intro}\n\n{deep_dive_txt}"
                deep_dive_tts = f"{feedback_intro} {deep_dive_txt}"
                
                # 音声ファイル生成
                timestamp = int(time.time())
                filename = os.path.join(TEMP_DIR, f"temp_audio_q2_{timestamp}.mp3")
                
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
                        # 動画・静止画を一時フォルダへ出力
                        video_fn = os.path.join(TEMP_DIR, f"temp_gaze_timelapse_{ts}.webm")
                        map_fn = os.path.join(TEMP_DIR, f"temp_gaze_map_{ts}.png")
                        
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
                
                # --- 総合評価生成 ---
                if not st.session_state.get("interviewer"):
                    st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
                else:
                    st.session_state.interviewer.mode = st.session_state.mode
                    st.session_state.interviewer.api_key = st.session_state.api_key

                with st.spinner("AI面接官が全体の回答を分析し、評価レポートをまとめています..."):
                    eval_json = st.session_state.interviewer.generate_evaluation_report(
                        es_pr=st.session_state.es_pr,
                        job_type=st.session_state.job_type,
                        question_1=st.session_state.question_1,
                        answer_1=st.session_state.user_answer_1,
                        question_2=st.session_state.deep_dive_text,
                        answer_2=st.session_state.user_answer_2
                    )
                
                st.session_state.overall_score = eval_json.get("overall_score", 88)
                st.session_state.rank = eval_json.get("rank", "A")
                st.session_state.consistency_score = eval_json.get("consistency_score", 90)
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
                
                eval_tts = f"面接練習お疲れ様でした。あなたのアピールポイントと改善点を含めた詳細な診断評価レポートを作成しましたので、画面をご確認ください。本日はお疲れ様でした！"
                
                # 音声ファイル生成
                timestamp = int(time.time())
                filename = os.path.join(TEMP_DIR, f"temp_audio_eval_{timestamp}.mp3")
                
                with st.spinner("面接官がフィードバックをまとめています..."):
                    success = generate_tts(eval_tts, filename)
                    if success:
                        st.session_state.eval_audio_path = filename
                    
                    # データベースに詳細な結果を保存
                    save_interview_result(
                        user_name=st.session_state.name,
                        job_type=st.session_state.job_type,
                        overall_score=st.session_state.overall_score,
                        rank=st.session_state.rank,
                        consistency_score=st.session_state.consistency_score,
                        content_quality_score=st.session_state.content_quality_score,
                        eye_contact_score=st.session_state.eye_contact_score,
                        eval_text=st.session_state.eval_text,
                        user_answer_1=st.session_state.user_answer_1,
                        user_answer_2=st.session_state.user_answer_2
                    )
                    
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