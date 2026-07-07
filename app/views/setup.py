import os
import time
import streamlit as st
from src.gemini_interviewer import GeminiInterviewer
from src.database import get_interview_history
from src.tts import generate_tts
from src.utils import TEMP_DIR, cleanup_temp_files, parse_excel_skillsheet
from src.gaze_tracker import (
    GazeRecorder,
    scan_available_cameras,
    analyze_face_features,
    draw_face_landmarks,
    draw_radar_overlay,
    collect_calibration_sample
)

def reset_dialog_state():
    st.session_state.show_calib_dialog = False
    st.session_state.calib_wizard_step = 1

@st.dialog("📐 視線キャリブレーション", width="large", on_dismiss=reset_dialog_state)
def run_calibration_dialog():
    if "calib_wizard_step" not in st.session_state:
        st.session_state.calib_wizard_step = 2
    if "calib_center_res" not in st.session_state:
        st.session_state.calib_center_res = None
    if "calib_limit_res" not in st.session_state:
        st.session_state.calib_limit_res = None
        
    if st.session_state.calib_wizard_step == 1:
        st.session_state.calib_wizard_step = 2

    if st.session_state.calib_wizard_step == 2:
        st.markdown(
            """
            <div class="calib-container">
                <div class="calib-step-indicator">ステップ 2 / 8: 正面注視ターゲット提示</div>
                <div class="calib-target-wrapper">
                    <div class="calib-target-center"></div>
                </div>
                <div style="margin-top: 15px; font-weight: bold; color: #0d9488;">アバター（またはWebカメラ）をまっすぐ正面に見つめてください。</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            if st.button("正面サンプリング（データ集め）を開始する", use_container_width=True, key="btn_go_step3", type="primary"):
                st.session_state.calib_wizard_step = 3
                st.rerun()
        with col_btn2:
            if st.button("キャンセル", use_container_width=True, key="btn_cancel_step2"):
                st.session_state.calib_wizard_step = 1
                st.session_state.show_calib_dialog = False
                st.rerun()
                
    elif st.session_state.calib_wizard_step == 3:
        countdown_placeholder = st.empty()
        for i in range(3, 0, -1):
            countdown_placeholder.markdown(
                f"""
                <div class="calib-container">
                    <div class="calib-step-indicator">ステップ 3 / 8: 正面データ収集（データ集め準備）</div>
                    <div class="calib-target-wrapper">
                        <div class="calib-target-center"></div>
                    </div>
                    <div style="margin-top: 15px; font-size: 2.5rem; font-weight: 800; color: #0d9488;">{i}</div>
                    <div style="margin-top: 5px; font-weight: bold; color: #64748b;">測定開始まで {i} 秒... 画面中央を見つめてください。</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            time.sleep(1.0)
        
        countdown_placeholder.markdown(
            """
            <div class="calib-container">
                <div class="calib-step-indicator">ステップ 3 / 8: 正面データ収集（データ集め中）</div>
                <div class="calib-target-wrapper">
                    <div class="calib-target-center"></div>
                </div>
                <div style="margin-top: 15px; font-weight: bold; color: #0d9488; animation: blink 1s infinite;">● 測定中 (約2秒間)...</div>
                <div style="margin-top: 5px; font-weight: bold; color: #64748b;">視線を動かさないでください。</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        res = collect_calibration_sample(st.session_state.camera_index, duration=2.0)
        countdown_placeholder.empty()
        
        if res:
            st.session_state.calib_center_res = res
        else:
            st.session_state.calib_center_res = None
        st.session_state.calib_wizard_step = 4
        st.rerun()
            
    elif st.session_state.calib_wizard_step == 4:
        st.markdown('<div class="calib-container">', unsafe_allow_html=True)
        st.markdown('<div class="calib-step-indicator">ステップ 4 / 8: 正面データ解析</div>', unsafe_allow_html=True)
        
        res = st.session_state.calib_center_res
        if res:
            st.markdown(
                f"""
                <div style="margin-top: 10px; margin-bottom: 20px;">
                    <span style="color: #0d9488; font-size: 1.2rem; font-weight: bold;">✓ 正面解析完了</span><br>
                    <div style="font-size: 1.1rem; margin-top: 10px;">基準の視線座標が正常に計算されました。</div>
                    <div style="font-size: 1rem; color: #64748b; margin-top: 5px;">中心座標 (X: {res[0]:.3f}, Y: {res[1]:.3f})</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                if st.button("次へ（よそ見限界の調整）", use_container_width=True, key="btn_go_step5", type="primary"):
                    st.session_state.calib_wizard_step = 5
                    st.rerun()
            with col_btn2:
                if st.button("もう一度やり直す", use_container_width=True, key="btn_retry_step4"):
                    st.session_state.calib_wizard_step = 2
                    st.session_state.calib_center_res = None
                    st.rerun()
        else:
            st.markdown(
                """
                <div style="margin-top: 10px; margin-bottom: 20px;">
                    <span style="color: #ff7675; font-size: 1.2rem; font-weight: bold;">⚠ 解析失敗</span><br>
                    <div style="font-size: 1.1rem; margin-top: 10px; color: #ff7675;">顔または視線が検出できませんでした。</div>
                    <div style="font-size: 0.9rem; color: #64748b; margin-top: 5px;">部屋の照明を明るくするか、カメラの角度を調整してください。</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                if st.button("もう一度サンプリングする", use_container_width=True, key="btn_retry_step4_err", type="primary"):
                    st.session_state.calib_wizard_step = 2
                    st.session_state.calib_center_res = None
                    st.rerun()
            with col_btn2:
                if st.button("キャンセル", use_container_width=True, key="btn_cancel_step4"):
                    st.session_state.calib_wizard_step = 1
                    st.session_state.calib_center_res = None
                    st.session_state.show_calib_dialog = False
                    st.rerun()
                    
    elif st.session_state.calib_wizard_step == 5:
        st.markdown(
            """
            <div class="calib-container">
                <div class="calib-step-indicator">ステップ 5 / 8: よそ見ターゲット提示</div>
                <div class="calib-target-wrapper">
                    <div class="calib-target-away"></div>
                </div>
                <div style="margin-top: 15px; font-weight: bold; color: #ff7675;">「これ以上目をそらしたら『よそ見』と判定させたい限界位置（画面の端など）」を見つめてください。</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            if st.button("よそ見サンプリング（データ集め）を開始する", use_container_width=True, key="btn_go_step6", type="primary"):
                st.session_state.calib_wizard_step = 6
                st.rerun()
        with col_btn2:
            if st.button("戻る", use_container_width=True, key="btn_back_step5"):
                st.session_state.calib_wizard_step = 4
                st.rerun()
                
    elif st.session_state.calib_wizard_step == 6:
        countdown_placeholder = st.empty()
        for i in range(3, 0, -1):
            countdown_placeholder.markdown(
                f"""
                <div class="calib-container">
                    <div class="calib-step-indicator">ステップ 6 / 8: よそ見データ収集（データ集め準備）</div>
                    <div class="calib-target-wrapper">
                        <div class="calib-target-away"></div>
                    </div>
                    <div style="margin-top: 15px; font-size: 2.5rem; font-weight: 800; color: #ff7675;">{i}</div>
                    <div style="margin-top: 5px; font-weight: bold; color: #64748b;">測定開始まで {i} 秒... 画面左端を見つめてください。</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            time.sleep(1.0)
        
        countdown_placeholder.markdown(
            """
            <div class="calib-container">
                <div class="calib-step-indicator">ステップ 6 / 8: よそ見データ収集（データ集め中）</div>
                <div class="calib-target-wrapper">
                    <div class="calib-target-away"></div>
                </div>
                <div style="margin-top: 15px; font-weight: bold; color: #ff7675; animation: blink 1s infinite;">● 測定中 (約2秒間)...</div>
                <div style="margin-top: 5px; font-weight: bold; color: #64748b;">視線を動かさないでください。</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        res = collect_calibration_sample(st.session_state.camera_index, duration=2.0)
        countdown_placeholder.empty()
        
        if res:
            st.session_state.calib_limit_res = res
        else:
            st.session_state.calib_limit_res = None
        st.session_state.calib_wizard_step = 7
        st.rerun()
            
    elif st.session_state.calib_wizard_step == 7:
        st.markdown('<div class="calib-container">', unsafe_allow_html=True)
        st.markdown('<div class="calib-step-indicator">ステップ 7 / 8: よそ見データ解析</div>', unsafe_allow_html=True)
        
        res = st.session_state.calib_limit_res
        if res:
            st.markdown(
                f"""
                <div style="margin-top: 10px; margin-bottom: 20px;">
                    <span style="color: #ff7675; font-size: 1.2rem; font-weight: bold;">✓ よそ見解析完了</span><br>
                    <div style="font-size: 1.1rem; margin-top: 10px;">よそ見限界の視線座標が正常に計算されました。</div>
                    <div style="font-size: 1rem; color: #64748b; margin-top: 5px;">限界座標 (X: {res[0]:.3f}, Y: {res[1]:.3f})</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                if st.button("次へ（結果の確認・適用）", use_container_width=True, key="btn_go_step8", type="primary"):
                    st.session_state.calib_wizard_step = 8
                    st.rerun()
            with col_btn2:
                if st.button("もう一度やり直す", use_container_width=True, key="btn_retry_step7"):
                    st.session_state.calib_wizard_step = 5
                    st.session_state.calib_limit_res = None
                    st.rerun()
        else:
            st.markdown(
                """
                <div style="margin-top: 10px; margin-bottom: 20px;">
                    <span style="color: #ff7675; font-size: 1.2rem; font-weight: bold;">⚠ 解析失敗</span><br>
                    <div style="font-size: 1.1rem; margin-top: 10px; color: #ff7675;">顔または視線が検出できませんでした。</div>
                    <div style="font-size: 0.9rem; color: #64748b; margin-top: 5px;">部屋の照明を明るくするか、カメラの角度を調整してください。</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                if st.button("もう一度サンプリングする", use_container_width=True, key="btn_retry_step7_err", type="primary"):
                    st.session_state.calib_wizard_step = 5
                    st.session_state.calib_limit_res = None
                    st.rerun()
            with col_btn2:
                if st.button("キャンセル", use_container_width=True, key="btn_cancel_step7"):
                    st.session_state.calib_wizard_step = 1
                    st.session_state.calib_limit_res = None
                    st.session_state.show_calib_dialog = False
                    st.rerun()
                    
    elif st.session_state.calib_wizard_step == 8:
        st.markdown('<div class="calib-container">', unsafe_allow_html=True)
        st.markdown('<div class="calib-step-indicator">ステップ 8 / 8: 結果出力・許容値更新</div>', unsafe_allow_html=True)
        
        if not st.session_state.calib_center_res or not st.session_state.calib_limit_res:
            st.warning("キャリブレーションデータが不足しています。最初からやり直してください。")
            if st.button("最初に戻る", use_container_width=True):
                st.session_state.calib_wizard_step = 2
                st.session_state.calib_center_res = None
                st.session_state.calib_limit_res = None
                st.rerun()
        else:
            cx, cy = st.session_state.calib_center_res
            lx, ly = st.session_state.calib_limit_res
            
            h_diff = abs(lx - cx)
            v_diff = abs(ly - cy)
            
            h_margin = max(0.04, min(0.22, h_diff))
            v_margin = max(0.04, min(0.22, v_diff))
            
            new_h_range = (round(cx - h_margin, 2), round(cx + h_margin, 2))
            new_v_range = (round(cy - v_margin, 2), round(cy + v_margin, 2))
            
            st.markdown(
                f"""
                <div style="text-align: left; width: 100%; padding: 10px 20px;">
                    <div style="font-weight: bold; font-size: 1.1rem; color: #0d9488; margin-bottom: 10px;">📐 計算されたキャリブレーション結果</div>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 6px 0; color: #475569;">正面中心点 (X, Y)</td>
                            <td style="padding: 6px 0; text-align: right; font-weight: bold;">({cx:.2f}, {cy:.2f})</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #475569;">よそ見限界点 (X, Y)</td>
                            <td style="padding: 6px 0; text-align: right; font-weight: bold;">({lx:.2f}, {ly:.2f})</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #475569;">計算された左右許容幅</td>
                            <td style="padding: 6px 0; text-align: right; font-weight: bold; color: #0d9488;">±{h_margin:.2f}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #475569;">計算された上下許容幅</td>
                            <td style="padding: 6px 0; text-align: right; font-weight: bold; color: #0d9488;">±{v_margin:.2f}</td>
                        </tr>
                    </table>
                    <div style="margin-top: 15px; padding: 10px; background: rgba(13, 148, 136, 0.05); border: 1px solid rgba(13, 148, 136, 0.2); border-radius: 8px;">
                        <div style="font-weight: bold; color: #0d9488; font-size: 0.95rem;">🎯 新しい許容範囲設定:</div>
                        <div style="font-size: 0.9rem; margin-top: 4px;">左右: <b>{new_h_range[0]} - {new_h_range[1]}</b> / 上下: <b>{new_v_range[0]} - {new_v_range[1]}</b></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                if st.button("💾 この設定を適用して終了する", use_container_width=True, key="btn_apply_calib_finish", type="primary"):
                    st.session_state.h_range = new_h_range
                    st.session_state.v_range = new_v_range
                    
                    st.session_state.calib_wizard_step = 1
                    st.session_state.calib_center_res = None
                    st.session_state.calib_limit_res = None
                    st.session_state.show_calib_dialog = False
                    
                    st.toast("🎯 新しい視線許容範囲を適用しました！")
                    st.rerun()
            with col_btn2:
                if st.button("破棄して閉じる", use_container_width=True, key="btn_reset_wizard"):
                    st.session_state.calib_wizard_step = 1
                    st.session_state.calib_center_res = None
                    st.session_state.calib_limit_res = None
                    st.session_state.show_calib_dialog = False
                    st.rerun()

def render_options_section():
    st.markdown("システムの動作環境（デバイス、各種機能のオン/オフおよびパラメータ）を調整します。")
    
    st.markdown("### 🔊 サウンド設定 (スピーカーの選択)")
    with st.container(border=True):
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            speaker_options = []
            for d in devices:
                if d.get('max_output_channels', 0) > 0:
                    name = d.get('name', 'Unknown Device')
                    if isinstance(name, bytes):
                        name = name.decode('utf-8', errors='ignore')
                    speaker_options.append(name)
            speaker_options = list(dict.fromkeys(speaker_options))
        except Exception:
            speaker_options = ["既定のスピーカー (システム設定に従う)"]
            
        if not speaker_options:
            speaker_options = ["既定のスピーカー (システム設定に従う)"]
            
        if "selected_speaker" not in st.session_state:
            st.session_state.selected_speaker = speaker_options[0]
        elif st.session_state.selected_speaker not in speaker_options:
            st.session_state.selected_speaker = speaker_options[0]
            
        selected_speaker = st.selectbox(
            "音声の再生に使用するスピーカーを選択してください",
            options=speaker_options,
            index=speaker_options.index(st.session_state.selected_speaker),
            key="speaker_selectbox"
        )
        st.session_state.selected_speaker = selected_speaker
        
        # Inject JavaScript to set the sink ID of all audio elements in the browser
        safe_speaker = selected_speaker.replace("'", "\\'")
        st.components.v1.html(
            f"""
            <script>
            const selectedLabel = '{safe_speaker}';
            
            function updateSinkId() {{
                if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
                navigator.mediaDevices.enumerateDevices().then(devices => {{
                    const audiooutput = devices.filter(d => d.kind === 'audiooutput');
                    let targetDevice = audiooutput.find(d => d.label === selectedLabel);
                    if (!targetDevice) {{
                        targetDevice = audiooutput.find(d => d.label.includes(selectedLabel) || selectedLabel.includes(d.label));
                    }}
                    
                    if (targetDevice) {{
                        const parentDoc = window.parent.document;
                        const audios = parentDoc.querySelectorAll('audio');
                        audios.forEach(audio => {{
                            if (audio.setSinkId && audio.sinkId !== targetDevice.deviceId) {{
                                audio.setSinkId(targetDevice.deviceId)
                                    .then(() => console.log('Audio output successfully routed to:', targetDevice.label))
                                    .catch(err => console.error('setSinkId error:', err));
                            }}
                        }});
                    }}
                }});
            }}
            
            updateSinkId();
            setInterval(updateSinkId, 1000);
            </script>
            """,
            height=0,
            width=0
        )
        
        st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08); margin: 10px 0;'>", unsafe_allow_html=True)
        st.toggle("音声認識を利用する (リアルタイム文字起こしと回答分析)", value=False, disabled=True, help="今後のアップデートで追加予定の機能です。")
        st.caption("※ 現在はご利用いただけません。 (将来の拡張用)")
        
    st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08); margin: 15px 0;'>", unsafe_allow_html=True)
    
    st.markdown("### 👁️ 視線・表情検知の設定")
    
    # 「カメラを利用する」トグル
    if "use_camera" not in st.session_state:
        st.session_state.use_camera = True
        
    use_camera = st.toggle("カメラを利用する (視線トラッキング)", value=st.session_state.use_camera, key="toggle_use_camera")
    st.session_state.use_camera = use_camera
    
    if use_camera:
        with st.container(border=True):
            st.subheader("📹 カメラ設定")
            col_cam_sel, col_cam_scan = st.columns([2, 1])
            with col_cam_sel:
                cam_options = st.session_state.available_cameras
                cam_labels = [f"カメラ {i}" for i in cam_options]
                
                default_sel_idx = 0
                if st.session_state.camera_index in cam_options:
                    default_sel_idx = cam_options.index(st.session_state.camera_index)
                
                selected_cam_idx = st.selectbox(
                    "使用するカメラを選択",
                    options=range(len(cam_options)),
                    format_func=lambda x: cam_labels[x],
                    index=default_sel_idx,
                    key="dialog_camera_selectbox"
                )
                st.session_state.camera_index = cam_options[selected_cam_idx]
                
            with col_cam_scan:
                          st.subheader("📐 視線許容範囲の自動調整 (キャリブレーション)")
            st.markdown("カメラを実際に見つめて、あなたの目線の動きに合わせた最適な許容範囲を自動計測します。")
            
            # ダイアログ表示用の初期化
            if "show_calib_dialog" not in st.session_state:
                st.session_state.show_calib_dialog = False
            if "calib_wizard_step" not in st.session_state:
                st.session_state.calib_wizard_step = 1
            if "calib_center_res" not in st.session_state:
                st.session_state.calib_center_res = None
            if "calib_limit_res" not in st.session_state:
                st.session_state.calib_limit_res = None

            if st.button("📐 自動調整（キャリブレーション）を開始する", use_container_width=True, type="primary", key="btn_start_calib"):
                # リアルタイム診断が有効なら強制的にOFFにしてカメラをリリースさせる
                st.session_state.dialog_live_cam_checkbox = False
                st.session_state.show_calib_dialog = True
                st.session_state.calib_wizard_step = 2
                st.rerun()

            if st.session_state.get("show_calib_dialog", False):
                run_calibration_dialog()
                    
            st.markdown("<hr style='border: 0.5px solid rgba(0,0,0,0.08); margin: 15px 0;'>", unsafe_allow_html=True)
            
            st.subheader("⚙️ 視線判定しきい値の調整")
            st.markdown("数値範囲を狭くすると判定が厳しくなり、広くすると甘くなります。")
            
            h_range = st.slider(
                "水平方向の許容範囲 (左右の目線そらしの感度)",
                min_value=0.20,
                max_value=0.80,
                value=st.session_state.h_range,
                step=0.01,
                key="dialog_h_range_slider"
            )
            st.session_state.h_range = h_range
            
            v_range = st.slider(
                "垂直方向の許容範囲 (上下の目線そらしの感度)",
                min_value=0.20,
                max_value=0.80,
                value=st.session_state.v_range,
                step=0.01,
                key="dialog_v_range_slider"
            )
            st.session_state.v_range = v_range
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # リアルタイム診断モードのトグル
            is_calib_active = st.session_state.get("show_calib_dialog", False)
            live_cam_active = st.checkbox(
                "📹 リアルタイム診断モードを開始する (診断プレビュー)",
                value=False,
                key="dialog_live_cam_checkbox",
                disabled=is_calib_active
            )
            
            if live_cam_active and not is_calib_active:
                import cv2
                import mediapipe as mp
                import platform
                if platform.system() == "Windows":
                    cap = cv2.VideoCapture(st.session_state.camera_index, cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(st.session_state.camera_index)
                if not cap.isOpened():
                    st.error("カメラデバイスを開くことができませんでした。")
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
                        st.warning(f"目線解析モデルの初期化に失敗しました: {e}")
                    
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
                                            gaze_x_compensated = gaze_x + 0.25 * yaw
                                            gaze_y_compensated = gaze_y + 0.25 * (pitch - 0.5)
                                            
                                            if not (st.session_state.h_range[0] <= gaze_x_compensated <= st.session_state.h_range[1]) or not (st.session_state.v_range[0] <= gaze_y_compensated <= st.session_state.v_range[1]):
                                                looking_away = True
                                                
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
                                
                            if len(trail_points) > 40:
                                trail_points.pop(0)
                                
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
                            
                            dot_color = draw_radar_overlay(
                                frame=frame,
                                gaze_x_compensated=gaze_x_compensated,
                                gaze_y_compensated=gaze_y_compensated,
                                is_blink=is_blink,
                                is_calibrating=False,
                                looking_away=looking_away
                            )
                            
                            if is_blink:
                                status_txt = "BLINKING"
                            else:
                                status_txt = "LOOKING AWAY (OUT OF RANGE)" if looking_away else "LOOKING AT SCREEN (OK)"
                            cv2.putText(frame, status_txt, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, dot_color, 2)
                            cv2.putText(frame, f"Gaze X: {gaze_x_compensated:.3f} (Limit: {st.session_state.h_range[0]:.2f} - {st.session_state.h_range[1]:.2f})", (15, h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                            cv2.putText(frame, f"Gaze Y: {gaze_y_compensated:.3f} (Limit: {st.session_state.v_range[0]:.2f} - {st.session_state.v_range[1]:.2f})", (15, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                            cv2.rectangle(frame, (0, 0), (w, h), dot_color, 6)
                            
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            frame_placeholder.image(frame_rgb, caption="リアルタイム目線追跡プレビュー", use_container_width=True)
                            time.sleep(0.04)
                    finally:
                        if face_mesh is not None:
                            face_mesh.close()
                        cap.release()
                        frame_placeholder.empty()




def render_setup_view():
    # 2カラムレイアウトで表示
    col_setup_left, col_setup_right = st.columns([1, 1], gap="large")
    
    with col_setup_left:
        with st.container(border=True):
            st.markdown('<div class="glass-card-marker" style="display:none;"></div>', unsafe_allow_html=True)
            st.subheader("📝 経歴書のアップロードと案件情報の入力")
            
            # 手入力は削除し、Excelアップロード固定とする
            st.session_state.es_input_method = "EXCEL"
            
            # 案件情報の記入 (st.session_state.job_type に格納)
            project_info = st.text_area(
                "💼 案件情報（募集要項・仕事内容など）",
                value=st.session_state.job_type if st.session_state.job_type else "",
                placeholder="例:\n【業務内容】PythonおよびStreamlitを使用したWebアプリケーションの開発。\n【必須スキル】Pythonでの開発経験2年以上、SQLを用いたデータベース操作の実務経験。",
                height=150
            )
            st.session_state.job_type = project_info.strip()
            
            st.markdown("---")
            
            # Excelアップロードモード
            uploaded_file = st.file_uploader(
                "技術経歴書 (skillsheet.xlsx) をアップロードしてください", 
                type=["xlsx", "xls"],
                help="アップロードされたファイルからプロフィールやスキル、職務経歴が自動抽出されます。"
            )
                
            if uploaded_file is not None:
                try:
                    parsed_data = parse_excel_skillsheet(uploaded_file)
                    st.session_state.excel_parsed_data = parsed_data
                    
                    st.success("✓ Excelファイルの解析に成功しました！")
                    
                    # 解析データのプレビューをリッチに表示
                    st.markdown(f"""
                    <div style="background-color: rgba(13, 148, 136, 0.05); padding: 15px; border-radius: 8px; border: 1px solid rgba(13, 148, 136, 0.2); margin-top: 10px; margin-bottom: 15px;">
                        <div style="font-weight: bold; color: #0d9488; font-size: 1.1rem; margin-bottom: 10px;">📋 解析された経歴書プレビュー</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 0.95rem;">
                            <tr>
                                <td style="font-weight: bold; width: 30%; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">お名前:</td>
                                <td style="padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">{parsed_data.get('name', '未記入')}</td>
                            </tr>
                            <tr>
                                <td style="font-weight: bold; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">最終学歴:</td>
                                <td style="padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">{parsed_data.get('final_academic_background', '未記入')}</td>
                            </tr>
                            <tr>
                                <td style="font-weight: bold; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">技術スキル:</td>
                                <td style="white-space: pre-line; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">{parsed_data.get('tech_skills', '未記入')}</td>
                            </tr>
                            <tr>
                                <td style="font-weight: bold; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">保有資格:</td>
                                <td style="white-space: pre-line; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.05);">{parsed_data.get('qualifications', '未記入')}</td>
                            </tr>
                            <tr>
                                <td style="font-weight: bold; padding: 6px 0;">経験工程:</td>
                                <td style="padding: 6px 0;">{', '.join(parsed_data.get('experienced_processes', [])) if parsed_data.get('experienced_processes') else '未記入'}</td>
                            </tr>
                        </table>
                        <details style="margin-top: 12px; border-top: 1px dashed rgba(13, 148, 136, 0.2); padding-top: 10px;">
                            <summary style="cursor: pointer; color: #0d9488; font-weight: bold; font-size: 0.9rem;">職務経歴・詳細を表示</summary>
                            <div style="margin-top: 8px; font-size: 0.85rem; background-color: rgba(0,0,0,0.02); padding: 10px; border-radius: 4px; max-height: 250px; overflow-y: auto; white-space: pre-wrap; color: #334155; border: 1px solid rgba(0,0,0,0.05);">
                                {parsed_data.get('experienced_processes_content', '記載なし')}
                            </div>
                        </details>
                    </div>
                    """, unsafe_allow_html=True)
                except ValueError as ve:
                    st.error(f"❌ フォーマットエラー: {ve}")
                    st.session_state.excel_parsed_data = None
                except Exception as e:
                    st.error(f"❌ Excel解析中にエラーが発生しました: {e}")
                    st.session_state.excel_parsed_data = None
            else:
                st.info("経歴書データが含まれたExcelファイルをドラッグ＆ドロップまたは選択してください。")
                st.session_state.excel_parsed_data = None

    with col_setup_right:
        with st.container(border=True):
            st.markdown('<div class="glass-card-marker height-100-marker" style="display:none;"></div>', unsafe_allow_html=True)
            st.subheader("⚙️ 動作・API設定")
            
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
            else:
                st.info("オフラインデモ用のモックモードで動作します。APIキーは不要です。")
                
            with st.expander("⚙️ 環境設定・オプション", expanded=True):
                render_options_section()

    # 過去の面接履歴の表示
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("📊 過去の面接履歴")
    
    # Excelから読み取られた名前を取得
    current_name = ""
    if st.session_state.get("excel_parsed_data"):
        current_name = st.session_state.excel_parsed_data.get("name", "").strip()

    if current_name:
        history = get_interview_history(current_name)
        if history:
            st.markdown(f"**{current_name}** さんの過去の面接結果 ({len(history)}件) です。クリックして詳細を展開できます。")
            for item in history:
                created_at = item.get("created_at", "")
                job_type = item.get("job_type", "")
                overall_score = item.get("overall_score", 0)
                rank = item.get("rank", "D")
                
                # 案件情報の長さに応じて切り詰めて表示
                job_title_short = job_type[:15] + "..." if len(job_type) > 15 else job_type
                expander_label = f"📅 {created_at} | 案件: {job_title_short} | 判定: 【{rank}】 {overall_score}点"
                with st.expander(expander_label):
                    had_camera = item.get("use_camera", 1) == 1
                    
                    if had_camera:
                        h_col1, h_col2, h_col3 = st.columns(3)
                        with h_col1:
                            st.metric("一貫性", f"{item.get('consistency_score', 0)}点")
                        with h_col2:
                            st.metric("回答品質", f"{item.get('content_quality_score', 0)}点")
                        with h_col3:
                            st.metric("視線安定度", f"{item.get('eye_contact_score', 0)}点")
                    else:
                        h_col1, h_col2 = st.columns(2)
                        with h_col1:
                            st.metric("一貫性", f"{item.get('consistency_score', 0)}点")
                        with h_col2:
                            st.metric("回答品質", f"{item.get('content_quality_score', 0)}点")
                    
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
            st.info(f"**{current_name}** さんの過去の面接履歴は見つかりませんでした。最初の面接練習を開始して履歴を記録しましょう！")
    else:
        st.warning("経歴書Excelをアップロードすると、過去の履歴が表示されます。")

    # 開始ボタンを全幅で配置（設定オプションは動作・API設定カード内へ移動）
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 面接練習を開始する", use_container_width=True):
        excel_data = st.session_state.get("excel_parsed_data")
        
        if not excel_data:
            st.error("Excelファイルをアップロードして解析を完了させてください。")
        else:
            name = excel_data.get("name", "").strip()
            final_academic_background = excel_data.get("final_academic_background", "").strip()
            tech_skills = excel_data.get("tech_skills", "").strip()
            qualifications = excel_data.get("qualifications", "").strip()
            selected_processes = excel_data.get("experienced_processes", [])
            experienced_processes_content = excel_data.get("experienced_processes_content", "").strip()

            if not name:
                st.error("アップロードされた技術経歴書からお名前を抽出できませんでした。Excelファイルを確認してください。")
            elif not st.session_state.job_type.strip():
                st.warning("案件情報（募集要項・仕事内容など）を入力してください。")
            elif st.session_state.mode == "AI" and not st.session_state.api_key.strip():
                st.error("AIモードで実行するには、APIキーを設定してください。")
            else:
                cleanup_temp_files()
                
                # ES情報をセッションステートに保存
                st.session_state.name = name
                st.session_state.final_academic_background = final_academic_background
                st.session_state.tech_skills = tech_skills
                st.session_state.qualifications = qualifications
                st.session_state.experienced_processes = selected_processes
                st.session_state.experienced_processes_content = experienced_processes_content
                
                # 汎用の自己PR要約テキストを作成
                processes_str = ", ".join(selected_processes) if selected_processes else "なし"
                st.session_state.es_pr = (
                    f"学歴: {st.session_state.final_academic_background}\n"
                    f"スキル: {st.session_state.tech_skills}\n"
                    f"資格: {st.session_state.qualifications}\n"
                    f"経験工程: {processes_str}\n"
                    f"工程詳細: {st.session_state.experienced_processes_content}"
                )
                
                st.session_state.es_data = {
                    "name": st.session_state.name,
                    "final_academic_background": st.session_state.final_academic_background,
                    "tech_skills": st.session_state.tech_skills,
                    "qualifications": st.session_state.qualifications,
                    "experienced_processes": st.session_state.experienced_processes,
                    "experienced_processes_content": st.session_state.experienced_processes_content,
                    "job_type": st.session_state.job_type
                }
                
                # 視線トラッキングスレッドの開始 (Webカメラ起動、カメラが有効な場合のみ)
                if st.session_state.get("use_camera", True):
                    st.session_state.recorder = GazeRecorder(
                        camera_index=st.session_state.camera_index,
                        h_range=st.session_state.h_range,
                        v_range=st.session_state.v_range
                    )
                    st.session_state.recorder.start()
                else:
                    st.session_state.recorder = None
                
                q1_text = ""
                
                # --- 第一問生成 ---
                if not st.session_state.get("interviewer"):
                    st.session_state.interviewer = GeminiInterviewer(st.session_state.api_key, mode=st.session_state.mode)
                else:
                    st.session_state.interviewer.mode = st.session_state.mode
                    st.session_state.interviewer.api_key = st.session_state.api_key
                    
                with st.spinner("AI面接官がエントリーシートを読み込み、質問の流れを構成しています..."):
                    q1_text = st.session_state.interviewer.generate_case_intro(st.session_state.es_data)
                
                st.session_state.question_1 = q1_text
                st.session_state.interview_phase = "CASE_INTRO"
                
                # 音声ファイルを生成
                timestamp = int(time.time())
                filename = os.path.join(TEMP_DIR, f"temp_audio_q1_{timestamp}.mp3")
                
                with st.spinner("面接官の音声（TTS）を生成中..."):
                    success = generate_tts(q1_text, filename)
                    if success:
                        st.session_state.audio_path = filename
                    
                    # チャット履歴の初期化
                    st.session_state.chat_history = [{
                        "role": "interviewer",
                        "text": q1_text,
                        "audio_path": filename if success else ""
                    }]
                    st.session_state.current_audio_to_play = filename if success else None
                    st.session_state.step = "INTERVIEW"
                    st.rerun()

