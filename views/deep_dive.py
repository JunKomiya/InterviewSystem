import os
import time
import threading
import streamlit as st
from gemini_interviewer import GeminiInterviewer
from database import save_interview_result
from tts import generate_tts
from utils import TEMP_DIR

def render_deep_dive_view(avatar_path: str):
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
                
                # --- 総合評価生成 ---
                if not st.session_state.get("interviewer"):
                    st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
                else:
                    st.session_state.interviewer.mode = st.session_state.mode
                    st.session_state.interviewer.api_key = st.session_state.api_key

                with st.spinner("AI面接官が全体の回答を分析し、評価レポートをまとめています..."):
                    conversation_log = [
                        {"speaker": "interviewer", "text": st.session_state.question_1},
                        {"speaker": "student", "text": st.session_state.user_answer_1},
                        {"speaker": "interviewer", "text": st.session_state.deep_dive_text},
                        {"speaker": "student", "text": st.session_state.user_answer_2}
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
                        experienced_processes_content=st.session_state.experienced_processes_content
                    )
                    
                    st.session_state.step = "EVALUATION"
                    st.rerun()
                    
        st.markdown('</div>', unsafe_allow_html=True)
