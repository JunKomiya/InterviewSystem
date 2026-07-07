import os
import time
import threading
import streamlit as st
from src.gemini_interviewer import GeminiInterviewer
from src.database import save_interview_result
from src.tts import generate_tts, play_audio_background
from src.utils import TEMP_DIR

def render_interview_view():
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
            "text": st.session_state.get("question_1", "はじめまして。面談担当者のナナミです。本日はよろしくお願いいたします。"),
            "audio_path": st.session_state.get("audio_path", "")
        }]

    col_left, col_center, col_right = st.columns([1, 4, 1], gap="large")
    
    with col_center:
        with st.container(border=True):
            st.markdown('<div class="glass-card-marker" style="display:none;"></div>', unsafe_allow_html=True)
            st.subheader("💬 面談チャットログ")
            
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
            
            # 現在のフェーズに基づき、入力欄のラベルやプレースホルダー、ボタンテキストなどを動的に設定
            phase = st.session_state.get("interview_phase", "CASE_INTRO")
            
            # 完了（締め）のフェーズの場合は入力欄を表示せず、終了案内と評価進捗ボタンを表示
            if phase == "FINAL_QA_DONE":
                st.info("🎉 面談がすべて終了しました。面談官の評価レポートを確認してください。")
                if st.button("📊 評価レポートを表示する", use_container_width=True, type="primary"):
                    st.session_state.step = "EVALUATION"
                    st.rerun()
            else:
                if phase == "CASE_INTRO":
                    input_label = "✍️ 案件に対する質問・確認事項"
                    placeholder_text = "例: 開発チームで現在注力されている技術や、使用されているGitのワークフローなどがあれば教えていただけますでしょうか？（特に質問がなければ『特にありません。』等を入力して送信してください）"
                    button_label = "質問を送信する"
                elif phase == "CASE_QA":
                    input_label = "✍️ あなたの自己紹介と経疑・スキルアピール"
                    placeholder_text = "例: 私はプロト太郎と申します。大学では情報工学を専攻し、強みである課題解決力を活かしてJavaやVue.jsを用いたWeb開発の個人プロジェクトを1年半進めてまいりました。今回の案件の技術要件と一致する点が多く、貢献できると考えております。"
                    button_label = "経歴説明を送信する"
                elif phase == "CAREER_INTRO":
                    input_label = "✍️ 深掘り質問に対する回答"
                    placeholder_text = "例: その課題に対しては、チームのコード規約やレビュー体制を見直すことで対処しました。具体的には、プルリクエスト時のテストケース自動化などを導入し、バグの事前検知力を高めました。"
                    button_label = "回答を送信する"
                elif phase == "SKILL_QA":
                    input_label = "✍️ 最後の質問（逆質問）"
                    placeholder_text = "例: 今回の案件において、参画初期の段階で最も期待される役割やマイルストーンについて詳しく伺うことはできますでしょうか？（特に無ければ『特にありません。』等を入力して送信してください）"
                    button_label = "最後の質問を送信する"
                
                st.subheader(input_label)
                
                # ユニークな入力キーの生成
                input_key = f"user_reply_input_{phase}_{len(st.session_state.chat_history)}"
                
                user_ans = st.text_area(
                    "ここに回答を入力してください（タイピング）",
                    placeholder=placeholder_text,
                    height=150,
                    key=input_key
                )
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(button_label, use_container_width=True):
                    if not user_ans.strip():
                        st.warning("回答を入力してください。")
                    else:
                        # ユーザーの発言を履歴に追加
                        st.session_state.chat_history.append({
                            "role": "student",
                            "text": user_ans.strip()
                        })
                        
                        # インタビュアーの準備
                        if not st.session_state.get("interviewer"):
                            st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
                        else:
                            st.session_state.interviewer.mode = st.session_state.mode
                            st.session_state.interviewer.api_key = st.session_state.api_key
                            
                        # --- 各フェーズごとの応答生成と状態推移ロジック ---
                        if phase == "CASE_INTRO":
                            # 1. 案件説明 ➡️ 2. 案件質問への回答生成
                            with st.spinner("AI面接官が質問への回答を構成しています..."):
                                reply, next_prompt = st.session_state.interviewer.generate_case_qa_reply(
                                    es_data=st.session_state.es_data,
                                    user_question=user_ans.strip()
                                )
                            
                            combined_text = f"{reply}\n\n{next_prompt}"
                            combined_tts = f"{reply} {next_prompt}"
                            
                            # 音声ファイル生成
                            timestamp = int(time.time())
                            filename = os.path.join(TEMP_DIR, f"temp_audio_case_qa_{timestamp}.mp3")
                            
                            with st.spinner("音声（TTS）を生成中..."):
                                success = generate_tts(combined_tts, filename)
                                st.session_state.chat_history.append({
                                    "role": "interviewer",
                                    "text": combined_text,
                                    "audio_path": filename if success else ""
                                })
                                st.session_state.current_audio_to_play = filename if success else None
                            
                            st.session_state.interview_phase = "CASE_QA"
                            st.rerun()
                            
                        elif phase == "CASE_QA":
                            # 2. 案件質問への回答 ➡️ 3. 経歴説明の深掘り質問生成
                            st.session_state.user_answer_1 = user_ans.strip()  # 後方互換性
                            
                            with st.spinner("AI面接官が経歴を読み込み、深掘り質問を構成しています..."):
                                # 質問生成用にこれまでの対話履歴を speaker 形式で構築
                                conversation_log = [
                                    {"speaker": "interviewer", "text": msg["text"]} if msg["role"] == "interviewer" else {"speaker": "student", "text": msg["text"]}
                                    for msg in st.session_state.chat_history[:-1] # 送信した自分の発言を除く前の履歴
                                ]
                                # 現在送信した自己PRを追加
                                conversation_log.append({"speaker": "student", "text": user_ans.strip()})
                                
                                feedback_intro, deep_dive_txt = st.session_state.interviewer.generate_deep_dive_question(
                                    es_data=st.session_state.es_data,
                                    conversation_log=conversation_log
                                )
                                
                            combined_text = f"{feedback_intro}\n\n{deep_dive_txt}"
                            combined_tts = f"{feedback_intro} {deep_dive_txt}"
                            
                            # 音声ファイル生成
                            timestamp = int(time.time())
                            filename = os.path.join(TEMP_DIR, f"temp_audio_deep_dive_{timestamp}.mp3")
                            
                            with st.spinner("音声（TTS）を生成中..."):
                                success = generate_tts(combined_tts, filename)
                                st.session_state.chat_history.append({
                                    "role": "interviewer",
                                    "text": combined_text,
                                    "audio_path": filename if success else ""
                                })
                                st.session_state.current_audio_to_play = filename if success else None
                                
                            st.session_state.interview_phase = "CAREER_INTRO"
                            st.rerun()
                            
                        elif phase == "CAREER_INTRO":
                            # 3. 経歴質問への回答 ➡️ 4. 逆質問への誘導
                            st.session_state.user_answer_2 = user_ans.strip()  # 後方互換性
                            
                            reply = "ご回答いただきありがとうございました。ご自身の強みや課題への取り組みについて非常に良く分かりました。"
                            next_prompt = "それでは面談の最後に、あなたの方から弊社に対して何かご質問（逆質問）や確認したいことはございますか？"
                            combined_text = f"{reply}\n\n{next_prompt}"
                            combined_tts = f"{reply} {next_prompt}"
                            
                            # 音声ファイル生成
                            timestamp = int(time.time())
                            filename = os.path.join(TEMP_DIR, f"temp_audio_prompt_final_{timestamp}.mp3")
                            
                            with st.spinner("音声（TTS）を生成中..."):
                                success = generate_tts(combined_tts, filename)
                                st.session_state.chat_history.append({
                                    "role": "interviewer",
                                    "text": combined_text,
                                    "audio_path": filename if success else ""
                                })
                                st.session_state.current_audio_to_play = filename if success else None
                                
                            st.session_state.interview_phase = "SKILL_QA"
                            st.rerun()
                            
                        elif phase == "SKILL_QA":
                            # 4. 逆質問 ➡️ 5. 逆質問回答と締めの挨拶の生成、および全体の評価レポート生成
                            
                            # A. 視線トラッキングの停止とデータ処理 (ONの場合のみ)
                            if "recorder" in st.session_state and st.session_state.recorder is not None:
                                with st.spinner("カメラをオフにし、結果の解析を行っています..."):
                                    st.session_state.recorder.stop()
                                    ts = int(time.time())
                                    video_fn = os.path.join(TEMP_DIR, f"temp_gaze_timelapse_{ts}.webm")
                                    map_fn = os.path.join(TEMP_DIR, f"temp_gaze_map_{ts}.png")
                                    
                                    st.session_state.recorder.generate_gaze_map(map_fn)
                                    st.session_state.gaze_video_path = video_fn
                                    st.session_state.gaze_map_path = map_fn
                                    
                                    t = threading.Thread(
                                        target=st.session_state.recorder.save_timelapse,
                                        args=(video_fn,)
                                    )
                                    t.daemon = True
                                    t.start()
                                    st.session_state.gaze_video_thread = t
                                    
                                    gps = st.session_state.recorder.gaze_points
                                    if gps:
                                        total_frames = len(gps)
                                        valid_face_count = sum(1 for gp in gps if gp.get("is_valid", True))
                                        valid_gaze_frames = [gp for gp in gps if gp.get("is_valid", True) and not gp.get("is_blink", False)]
                                        
                                        if len(valid_gaze_frames) > 0:
                                            away_count = sum(1 for gp in valid_gaze_frames if gp.get("looking_away", False))
                                            st.session_state.eye_contact_score = int((1 - away_count / len(valid_gaze_frames)) * 100)
                                        else:
                                            st.session_state.eye_contact_score = 0
                                            
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
                                
                            # B. ナナミの最後の逆質問回答と締めの挨拶の生成
                            with st.spinner("AI面接官が質問への回答をまとめています..."):
                                reply_text = st.session_state.interviewer.generate_final_qa_reply(
                                    es_data=st.session_state.es_data,
                                    user_question=user_ans.strip()
                                )
                                
                            # 音声生成
                            timestamp = int(time.time())
                            filename = os.path.join(TEMP_DIR, f"temp_audio_final_reply_{timestamp}.mp3")
                            
                            with st.spinner("音声（TTS）を生成中..."):
                                success = generate_tts(reply_text, filename)
                                st.session_state.chat_history.append({
                                    "role": "interviewer",
                                    "text": reply_text,
                                    "audio_path": filename if success else ""
                                })
                                st.session_state.current_audio_to_play = filename if success else None
                            
                            # C. 全対話の総合評価の生成
                            with st.spinner("AI面接官が全体の対話を分析し、評価レポートを作成しています..."):
                                # 全履歴からGeminiInterviewer用にspeaker形式のログを生成
                                conversation_log = [
                                    {"speaker": "interviewer" if msg["role"] == "interviewer" else "student", "text": msg["text"]}
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
                                f"お疲れ様でした、{st.session_state.name}さん！非常に有意義な面談でした。\n\n"
                                f"【総評】\n"
                                f"{summary}\n\n"
                                f"【今後の改善アドバイス】\n"
                                f"{advice}"
                            )
                            
                            eval_tts = "面談お疲れ様でした。あなたのアピールポイントと改善点を含めた詳細な診断評価レポートを作成しましたので、画面をご確認ください。"
                            
                            # 評価音声生成
                            timestamp = int(time.time())
                            filename_eval = os.path.join(TEMP_DIR, f"temp_audio_eval_{timestamp}.mp3")
                            generate_tts(eval_tts, filename_eval)
                            st.session_state.eval_audio_path = filename_eval
                            
                            # D. データベースに詳細な結果を保存
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
                                created_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                                use_camera=1 if st.session_state.get("use_camera", True) else 0
                            )
                            
                            st.session_state.interview_phase = "FINAL_QA_DONE"
                            st.rerun()
