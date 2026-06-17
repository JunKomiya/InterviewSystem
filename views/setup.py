import os
import time
import cv2
import mediapipe as mp
import streamlit as st
from gemini_interviewer import GeminiInterviewer
from database import get_interview_history
from tts import generate_tts
from utils import TEMP_DIR, cleanup_temp_files
from gaze_tracker import (
    GazeRecorder,
    scan_available_cameras,
    analyze_face_features,
    draw_face_landmarks,
    draw_radar_overlay
)

def render_setup_view(avatar_path: str):
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
            "水平方向の許容範囲 (左右 of 目線そらしの感度)",
            min_value=0.20,
            max_value=0.80,
            value=st.session_state.h_range,
            step=0.01
        )
        st.session_state.h_range = h_range
        
        v_range = st.slider(
            "垂直方向の許容範囲 (上下 of 目線そらしの感度)",
            min_value=0.20,
            max_value=0.80,
            value=st.session_state.v_range,
            step=0.01
        )
        st.session_state.v_range = v_range
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # リアルタイム診断モードのトグル
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
                                        # 診断プレビュー用の簡易頭向き補正
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
                            
                        # 直近40フレームまでに制限
                        if len(trail_points) > 40:
                            trail_points.pop(0)
                            
                        # 視線のペイント軌跡（線）を描画
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
                        
                        # 判定に応じたテキストおよび太枠
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
