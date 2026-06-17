import os
import streamlit as st
from session_manager import init_session, stop_recorder
from views.setup import render_setup_view
from views.question import render_question_view
from views.deep_dive import render_deep_dive_view
from views.evaluation import render_evaluation_view

# 環境変数のAPIキーに改行などが含まれる場合のクレンジング
if "GEMINI_API_KEY" in os.environ:
    os.environ["GEMINI_API_KEY"] = os.environ["GEMINI_API_KEY"].strip()

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

# セッション状態の初期化と初回ローディング画面
init_session()

# 以前の残存している視線トラッキングスレッドがあれば停止
if st.session_state.step == "SETUP":
    stop_recorder()

# ヘッダー
st.markdown("""
<div class="header-container">
    <div class="main-title">🤖 AI面接練習システム</div>
    <div class="sub-title">視線トラッキング搭載 評価プロトタイプ</div>
</div>
""", unsafe_allow_html=True)

avatar_path = "interviewer_avatar.png"

# ルーティング処理 (現在のステップに応じてビューを描画)
if st.session_state.step == "SETUP":
    render_setup_view(avatar_path)
elif st.session_state.step == "QUESTION":
    render_question_view(avatar_path)
elif st.session_state.step == "DEEP_DIVE":
    render_deep_dive_view(avatar_path)
elif st.session_state.step == "EVALUATION":
    render_evaluation_view(avatar_path)

# フッター
st.markdown("""
<br><hr style='border: 0.5px solid rgba(255,255,255,0.05)'>
<div style="text-align: center; color: #718096; font-size: 0.85rem; padding-bottom: 20px;">
    🤖 AI面接練習システム (視線トラッキング搭載プロトタイプ) | Designed with Streamlit & Gemini Pro
</div>
""", unsafe_allow_html=True)