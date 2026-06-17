import streamlit as st

def render_start_view(avatar_path: str):
    # CSS3 脈動アニメーションの挿入
    st.markdown("""
        <style>
        @keyframes pulseGlow {
            0% {
                transform: scale(0.96);
                box-shadow: 0 0 35px rgba(108, 92, 231, 0.4), 0 0 15px rgba(0, 206, 201, 0.2);
            }
            100% {
                transform: scale(1.04);
                box-shadow: 0 0 60px rgba(108, 92, 231, 0.8), 0 0 30px rgba(0, 206, 201, 0.5);
            }
        }
        .pulsing-avatar-container {
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 50px auto 40px auto;
            width: 220px;
            height: 220px;
        }
        .pulsing-avatar-circle {
            width: 180px;
            height: 180px;
            border-radius: 50%;
            background: linear-gradient(135deg, #6c5ce7 0%, #00cec9 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            animation: pulseGlow 2.5s infinite alternate ease-in-out;
            border: 4px solid rgba(255, 255, 255, 0.15);
        }
        .pulsing-avatar-inner {
            font-size: 5rem;
            filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.3));
        }
        .welcome-text-card {
            text-align: center;
            max-width: 700px;
            margin: 0 auto 50px auto;
            padding: 30px;
            background: rgba(255, 255, 255, 0.02);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 16px;
        }
        </style>
        
        <div class="pulsing-avatar-container">
            <div class="pulsing-avatar-circle">
                <span class="pulsing-avatar-inner">🤖</span>
            </div>
        </div>
        
        <div class="welcome-text-card">
            <h3 style="color:#ffffff; margin-bottom: 15px;">AI面接官ナナミとの模擬面接へようこそ</h3>
            <p style="color:#cbd5e1; font-size:1.05rem; line-height:1.6; margin:0;">
                本システムは、最新の視線トラッキング（Gaze Tracking）技術と高性能生成AI（Gemini Pro）を融合させた、自律型面接練習システムです。<br>
                PCのWebカメラを通じて面接中のあなたの目線の動きを分析し、アイコンタクトの安定度を可視化します。<br>
                エントリーシートの登録をもとに、AI面接官があなたの強みを深く掘り下げます。
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # 開始ボタンの配置
    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    if st.button("🚀 面接練習を始める", use_container_width=True):
        st.session_state.step = "SETUP"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
