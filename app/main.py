import os
import streamlit as st
from src.session_manager import init_session, stop_recorder, reset_session
from views.start import render_start_view
from views.setup import render_setup_view
from views.interview import render_interview_view
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

# カスタムローディング画面のHTMLを挿入
st.markdown("""
<div class="custom-loader-overlay">
    <div class="custom-loader-card">
        <div class="custom-loader-spinner"></div>
        <div class="custom-loader-text">処理を実行中...</div>
        <div class="custom-loader-subtext">このまましばらくお待ちください</div>
    </div>
</div>
""", unsafe_allow_html=True)

# セッション状態の初期化と初回ローディング画面
init_session()

# クエリパラメータによるリセット（最初のシーンへ戻る）検知
if st.query_params.get("reset") == "true":
    reset_session()
    st.session_state.step = "START"
    st.query_params.clear()
    st.rerun()

# 以前の残存している視線トラッキングスレッドがあれば停止
if st.session_state.step == "SETUP":
    stop_recorder()

# ヘッダーバナー
st.markdown("""
<a href="/?reset=true" target="_self" class="header-banner-link">
    <div class="header-banner">
        <div class="main-title">🤖 AI面接練習システム</div>
    </div>
</a>
""", unsafe_allow_html=True)

# ルーティング処理 (現在のステップに応じてビューを描画)
if st.session_state.step == "START":
    render_start_view()
elif st.session_state.step == "SETUP":
    render_setup_view()
elif st.session_state.step == "INTERVIEW":
    render_interview_view()
elif st.session_state.step == "EVALUATION":
    render_evaluation_view()

# フッター
st.markdown("""
<br><hr style='border: 0.5px solid rgba(0,0,0,0.08)'>
<div style="text-align: center; color: #475569; font-size: 0.85rem; padding-bottom: 20px;">
    🤖 AI面接練習システム (視線トラッキング搭載プロトタイプ) | Designed with Streamlit & Gemini Pro
</div>
""", unsafe_allow_html=True)