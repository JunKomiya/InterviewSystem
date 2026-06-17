import os
import time
import streamlit as st
from gemini_interviewer import GeminiInterviewer
from tts import generate_tts
from utils import TEMP_DIR

def render_question_view(avatar_path: str):
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
