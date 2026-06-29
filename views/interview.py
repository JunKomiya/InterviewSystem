import os
import time
import threading
import streamlit as st
from src.gemini_interviewer import GeminiInterviewer
from src.database import save_interview_result
from src.tts import generate_tts, play_audio_background
from src.utils import TEMP_DIR

def render_interview_view(avatar_path: str):
    # 音声ファイルの再生（レイアウト影響を防ぐため最上部で実行）
    is_speaking = False
    if st.session_state.get("current_audio_to_play") and os.path.exists(st.session_state.current_audio_to_play):
        is_speaking = True
        play_audio_background(st.session_state.current_audio_to_play)
        # 再生指示を出したら、多重再生を防止するために即時クリア
        st.session_state.current_audio_to_play = None

    # 安全策としてのセッションステート初期化
    if "chat_history" not in st.session_state or not st.session_state.chat_history:
        st.session_state.chat_history = [{
            "role": "interviewer",
            "text": st.session_state.get("question_1", "自己紹介と、今回アピールしたい自身の強みについてお話しください。"),
            "audio_path": st.session_state.get("audio_path", "")
        }]

    col_left, col_center, col_right = st.columns([1, 4, 1], gap="large")
    
    with col_center:
        with st.container(border=True):
            st.markdown('<div class="glass-card-marker" style="display:none;"></div>', unsafe_allow_html=True)
            st.subheader("💬 面接チャットログ")
            
            # 会話履歴の表示
            for msg in st.session_state.chat_history:
                if msg["role"] == "interviewer":
                    st.markdown(f"""
                    <div class="chat-bubble interviewer-bubble">
                        <strong>ナナミ:</strong><br>
                        {msg["text"].replace('\n', '<br>')}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="chat-bubble student-bubble">
                        <strong>{st.session_state.name}:</strong><br>
                        {msg["text"].replace('\n', '<br>')}
                    </div>
                    """, unsafe_allow_html=True)
                
            st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08)'>", unsafe_allow_html=True)
            
            # 会話履歴の長さから現在のターン数と言葉・挙動を決定
            # 履歴の長さ: 1(ナナミの1問目) -> 1回目の回答待ち
            # 履歴の長さ: 3(ナナミの2問目) -> 2回目の回答待ち
            is_first_turn = (len(st.session_state.chat_history) == 1)
            
            if is_first_turn:
                input_label = "✍️ あなたの回答（自己紹介と強み）"
                placeholder_text = "例: はじめまして、プロト太郎と申します。大学では情報工学を専攻しており、強みである行動力を活かして個人でPythonのアプリ開発を行っています。特にReactとStreamlitの連携に力を入れています。"
                button_label = "回答を送信する"
            else:
                input_label = "✍️ あなたの回答（深掘り質問に対する回答）"
                placeholder_text = "例: 最大の困難は、個人開発で外部APIの連携エラーの解決に何日も詰まってしまったことです。しかし、公式ドキュメントやGitHubのIssueを読み漁り、解決しました。"
                button_label = "回答を送信して評価へ進む"
                
            st.subheader(input_label)
            
            # 入力ごとにユニークなキーを設定して、送信後の入力自動クリアを実現
            input_key = f"user_reply_input_{len(st.session_state.chat_history)}"
            
            user_ans = st.text_area(
                "ここに回答を入力してください（タイピング）",
                placeholder=placeholder_text,
                height=150,
                key=input_key
            )
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(button_label):
                if not user_ans.strip():
                    st.warning("回答を入力してください。")
                else:
                    # 回答を会話履歴に追加
                    st.session_state.chat_history.append({
                        "role": "student",
                        "text": user_ans.strip()
                    })
                    
                    if is_first_turn:
                        # 後方互換性のために変数に保存
                        st.session_state.user_answer_1 = user_ans.strip()
                        
                        # --- 深掘り質問生成 ---
                        if not st.session_state.get("interviewer"):
                            st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
                        else:
                            st.session_state.interviewer.mode = st.session_state.mode
                            st.session_state.interviewer.api_key = st.session_state.api_key
        
                        with st.spinner("AI面接官があなたの回答を評価し、深掘り質問を構成しています..."):
                            conversation_log = [
                                {"speaker": "interviewer", "text": st.session_state.question_1},
                                {"speaker": "student", "text": st.session_state.user_answer_1}
                            ]
                            feedback_intro, deep_dive_txt = st.session_state.interviewer.generate_deep_dive_question(
                                es_data=st.session_state.es_data,
                                conversation_log=conversation_log
                            )
                        
                        deep_dive_full = f"{feedback_intro}\n\n{deep_dive_txt}"
                        st.session_state.deep_dive_text = deep_dive_full
                        deep_dive_tts = f"{feedback_intro} {deep_dive_txt}"
                        
                        # 音声ファイル生成
                        timestamp = int(time.time())
                        filename = os.path.join(TEMP_DIR, f"temp_audio_q2_{timestamp}.mp3")
                        
                        with st.spinner("面接官が質問を考えています..."):
                            success = generate_tts(deep_dive_tts, filename)
                            if success:
                                st.session_state.deep_dive_audio_path = filename
                                st.session_state.current_audio_to_play = filename
                            else:
                                st.session_state.current_audio_to_play = None
                            
                            # 会話履歴に質問を追加
                            st.session_state.chat_history.append({
                                "role": "interviewer",
                                "text": deep_dive_full,
                                "audio_path": filename if success else ""
                            })
                            st.rerun()
                    else:
                        # 2回目の回答（深掘り回答）
                        st.session_state.user_answer_2 = user_ans.strip()
                        
                        # 視線トラッキングの停止とタイムラプス動画の出力
                        if "recorder" in st.session_state and st.session_state.recorder is not None:
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
                                    
                                    # 有効フレーム
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
                        else:
                            st.session_state.eye_contact_score = 100
                            st.session_state.gaze_measurement_warning = False
                            st.session_state.gaze_video_path = ""
                            st.session_state.gaze_map_path = ""
                        
                        # --- 総合評価生成 ---
                        if not st.session_state.get("interviewer"):
                            st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
                        else:
                            st.session_state.interviewer.mode = st.session_state.mode
                            st.session_state.interviewer.api_key = st.session_state.api_key
        
                        with st.spinner("AI面接官が全体の回答を分析し、評価レポートをまとめています..."):
                            # chat_historyからGeminiInterviewer用にspeaker形式のログを生成
                            conversation_log = [
                                {"speaker": msg["role"], "text": msg["text"]}
                                for msg in st.session_state.chat_history
                            ]
                            eval_json = st.session_state.interviewer.generate_evaluation_report(
                                es_data=st.session_state.es_data,
                                conversation_log=conversation_log
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
                            
                            use_camera_val = st.session_state.get("use_camera", True)
                            use_camera_int = 1 if use_camera_val else 0
        
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
                                user_answer_2=st.session_state.user_answer_2,
                                final_academic_background=st.session_state.final_academic_background,
                                tech_skills=st.session_state.tech_skills,
                                qualifications=st.session_state.qualifications,
                                experienced_processes=", ".join(st.session_state.experienced_processes),
                                experienced_processes_content=st.session_state.experienced_processes_content,
                                use_camera=use_camera_int
                            )
                            
                            st.session_state.step = "EVALUATION"
                            st.rerun()
