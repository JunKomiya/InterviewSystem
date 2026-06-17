import os
import streamlit as st
from session_manager import reset_session

def render_evaluation_view(avatar_path: str):
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
            reset_session()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
