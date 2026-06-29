import os
import streamlit as st
from src.session_manager import reset_session
from src.database import get_interview_history


def render_evaluation_view(avatar_path: str):
    st.success("🎉 面接のすべてのステップが終了しました！評価レポートを表示します。")
    if st.session_state.get("gaze_measurement_warning", False):
        st.warning("⚠️ 適切に計測できませんでした（カメラ位置や照明を確認してください）")
        
    # 過去5回の平均スコアを取得・算出
    user_name = st.session_state.get("name", "学生")
    history = get_interview_history(user_name)
    past_5 = history[:5] if history else []
    
    if past_5:
        avg_consistency = sum(r.get("consistency_score", 0) for r in past_5) / len(past_5)
        avg_content_quality = sum(r.get("content_quality_score", 0) for r in past_5) / len(past_5)
    else:
        avg_consistency = st.session_state.consistency_score
        avg_content_quality = st.session_state.content_quality_score
    
    col_l, col_r = st.columns([1, 2], gap="large")
    
    with col_l:
        with st.container(border=True):
            st.markdown('<div class="glass-card-marker text-center-marker" style="display:none;"></div>', unsafe_allow_html=True)
            st.subheader("📊 診断結果")
            
            st.markdown(f"""
            <div class="rank-container">
                <div class="rank-badge">{st.session_state.rank}</div>
                <div class="rank-label">総合判定 ({st.session_state.overall_score}点)</div>
            </div>
            """, unsafe_allow_html=True)
            
            # 1. メイン評価の表示 (常に表示)
            st.markdown("<div style='margin-top: 15px; margin-bottom: 5px; font-weight: bold; color: #4f46e5;'>🔑 メイン評価 (対話・内容)</div>", unsafe_allow_html=True)
            main_metrics = [
                {"name": "回答の一貫性 (AI分析)", "val": st.session_state.consistency_score, "color": "linear-gradient(90deg, #ff9f43, #feca57)", "avg": avg_consistency},
                {"name": "回答の適切さ (AI分析)", "val": st.session_state.content_quality_score, "color": "linear-gradient(90deg, #ff6b6b, #ff8787)", "avg": avg_content_quality}
            ]
            for m in main_metrics:
                st.markdown(f"""
                <div class="metric-row" style="margin-bottom: 25px;">
                    <span class="metric-name">{m['name']}</span>
                    <span class="metric-val">{m['val']}%</span>
                    <div class="metric-bar-bg" style="margin-bottom: 4px;">
                        <div class="metric-bar-fill" style="width: {m['val']}%; background: {m['color']};"></div>
                    </div>
                    <!-- 過去5回平均を示す細いゲージ -->
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.78rem; color: #475569; margin-top: 2px;">
                        <span>過去5回の平均</span>
                        <span style="font-weight: 600;">{m['avg']:.1f}%</span>
                    </div>
                    <div style="background: rgba(0, 0, 0, 0.05); height: 4px; border-radius: 2px; margin-top: 4px; overflow: hidden;">
                        <div style="height: 100%; width: {m['avg']}%; background: #94a3b8; border-radius: 2px;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    
            # 2. サブ評価の表示（オプション機能のON/OFFに連動）
            use_camera = st.session_state.get("use_camera", True)
            
            # 将来的に音声認識などの別のオプションが追加された際にも拡張しやすいよう、論理和で判定
            show_sub_section = use_camera  # 将来的には use_camera or use_audio などの拡張が可能
            
            if show_sub_section:
                st.markdown("<div style='margin-top: 20px; margin-bottom: 5px; font-weight: bold; color: #0d9488;'>📹 サブ評価 (オプション機能)</div>", unsafe_allow_html=True)
                sub_metrics = []
                
                if use_camera:
                    sub_metrics.append({"name": "視線の安定度 (実測データ)", "val": st.session_state.eye_contact_score, "color": "linear-gradient(90deg, #2e86de, #54a0ff)"})
                    
                for m in sub_metrics:
                    st.markdown(f"""
                    <div class="metric-row">
                        <span class="metric-name">{m['name']}</span>
                        <span class="metric-val">{m['val']}%</span>
                        <div class="metric-bar-bg">
                            <div class="metric-bar-fill" style="width: {m['val']}%; background: {m['color']};"></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        
        # 評価音声の再生 (非表示コンポーネント)
        if st.session_state.eval_audio_path and os.path.exists(st.session_state.eval_audio_path):
            from src.tts import play_audio_background
            play_audio_background(st.session_state.eval_audio_path)
        
    with col_r:
        # タブ機能を使って「総合評価」と「視線分析」を切り替え表示
        tab1, tab2 = st.tabs(["💡 総合指導 & ログ", "👁️ 視線トラッキング分析 (タイムラプス)"])
        
        with tab1:
            with st.container(border=True):
                st.markdown('<div class="glass-card-marker evaluation-tab-marker" style="display:none;"></div>', unsafe_allow_html=True)
                st.markdown('<h3 style="color: #0f172a; font-size: 1.35rem; font-weight: 700; margin-bottom: 15px;">💡 面接官ナナミからの総評 ＆ 改善指導</h3>', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="chat-bubble interviewer-bubble" style="white-space: pre-line; font-size: 1.05rem; border-left-color: #ff007f; color: #0f172a; background: rgba(255, 255, 255, 0.6);">
                    {st.session_state.eval_text}
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08); margin: 20px 0;'>", unsafe_allow_html=True)
                
                st.markdown('<h3 style="color: #0f172a; font-size: 1.35rem; font-weight: 700; margin-bottom: 15px;">📝 本日の面接ログ</h3>', unsafe_allow_html=True)
                st.markdown('<div style="background: rgba(255, 255, 255, 0.5); padding: 20px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.08); display: flex; flex-direction: column; gap: 15px;">', unsafe_allow_html=True)
                if st.session_state.get("chat_history"):
                    for msg in st.session_state.chat_history:
                        role_label = "🤖 【面接官からの質問】" if msg["role"] == "interviewer" else "👤 【あなたの回答】"
                        border_color = "#818cf8" if msg["role"] == "interviewer" else "#0d9488"
                        text_escaped = msg["text"].replace('\n', '<br>')
                        st.markdown(f"""
                        <div>
                            <p style="color: #1e293b; margin-bottom: 4px; font-weight: 600;"><strong>{role_label}</strong></p>
                            <p style="color: #0f172a; font-size: 1rem; border-left: 3px solid {border_color}; padding-left: 10px; margin-bottom: 0;">
                                {text_escaped}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div>
                        <p style="color: #1e293b; margin-bottom: 4px;"><strong>【自己紹介と強みの質問への回答】</strong></p>
                        <p style="color: #0f172a; font-size: 1rem; border-left: 3px solid #818cf8; padding-left: 10px; margin-bottom: 20px;">
                            {st.session_state.user_answer_1}
                        </p>
                        <p style="color: #1e293b; margin-bottom: 4px;"><strong>【深掘り質問への回答】</strong></p>
                        <p style="color: #0f172a; font-size: 1rem; border-left: 3px solid #4fd1c5; padding-left: 10px;">
                            {st.session_state.user_answer_2}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            
        with tab2:
            with st.container(border=True):
                st.markdown('<div class="glass-card-marker evaluation-tab-marker" style="display:none;"></div>', unsafe_allow_html=True)
                st.markdown('<h3 class="tracking-title" style="color: #0d9488; font-size: 1.35rem; font-weight: 700; border-left: 4px solid #0d9488; padding-left: 10px; margin-bottom: 15px;">👁️ 視線トラッキング分析タイムラプス</h3>', unsafe_allow_html=True)
                st.markdown('<p style="color: #1e293b; font-size: 1rem; margin-bottom: 20px;">面接中にカメラから取得した目線の動きを分析した結果です。</p>', unsafe_allow_html=True)
                
                col_v, col_m = st.columns([1, 1], gap="medium")
                
                with col_v:
                    st.markdown('<h5 style="color: #0f172a; font-weight: 700; margin-top: 10px; margin-bottom: 8px;">🎥 視線タイムラプス動画</h5>', unsafe_allow_html=True)
                    thread = st.session_state.get("gaze_video_thread")
                    if thread and thread.is_alive():
                        with st.spinner("タイムラプス動画を生成中..."):
                            thread.join(timeout=1.0)
                    
                    if thread and thread.is_alive():
                        st.info("🎥 動画ファイルをエンコード中です。しばらくしてからタブを切り替えるか、ブラウザをリロードしてください。")
                    elif st.session_state.gaze_video_path and os.path.exists(st.session_state.gaze_video_path):
                        st.video(st.session_state.gaze_video_path, autoplay=True, loop=True)
                        st.markdown('<p style="color: #475569; font-size: 0.85rem; margin-top: 6px; line-height: 1.4;">録画された顔の映像に「緑の虹彩マーク」と右上「視線プロットレーダー」が描画されたタイムラプスです。</p>', unsafe_allow_html=True)
                    else:
                        st.info("カメラが有効でなかったか、動画の書き込みに失敗したため、動画はありません。")
                        
                with col_m:
                    st.markdown('<h5 style="color: #0f172a; font-weight: 700; margin-top: 10px; margin-bottom: 8px;">📍 視線移動トレイルマップ</h5>', unsafe_allow_html=True)
                    if st.session_state.gaze_map_path and os.path.exists(st.session_state.gaze_map_path):
                        st.image(st.session_state.gaze_map_path, use_container_width=True)
                        st.markdown('<p style="color: #475569; font-size: 0.85rem; margin-top: 6px; line-height: 1.4;">面接開始から終了までの、目線座標の推移を描いたプロットです。線は時間の経過とともに色が変化（パープル側が最新）します。</p>', unsafe_allow_html=True)
                    else:
                        st.info("トラッキングデータがないため、マップ画像はありません。")
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # リセットボタン
        st.markdown('<div class="reset-btn">', unsafe_allow_html=True)
        if st.button("面接練習を最初からやり直す"):
            reset_session()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
