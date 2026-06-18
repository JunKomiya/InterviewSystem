import streamlit as st
from src.gaze_tracker import scan_available_cameras
from src.utils import cleanup_temp_files

def stop_recorder():
    """現在稼働中の GazeRecorder があれば安全に停止させます。"""
    if "recorder" in st.session_state and st.session_state.recorder:
        try:
            if st.session_state.recorder.is_recording:
                st.session_state.recorder.stop()
        except Exception:
            pass

def init_session():
    """アプリ起動時のセッション状態初期化ライフサイクルを行います。"""
    if "initialized" not in st.session_state:
        st.markdown("""
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <div class="loading-text">Loading...</div>
            </div>
        """, unsafe_allow_html=True)
        
        # セッション状態変数の初期設定
        st.session_state.step = "START"  # START -> SETUP -> QUESTION -> DEEP_DIVE -> EVALUATION
        st.session_state.name = ""
        st.session_state.final_academic_background = ""
        st.session_state.tech_skills = ""
        st.session_state.qualifications = ""
        st.session_state.experienced_processes = []
        st.session_state.experienced_processes_content = ""
        st.session_state.es_data = {}
        st.session_state.es_pr = ""
        st.session_state.job_type = ""
        st.session_state.mode = "MOCK"  # MOCK or AI
        st.session_state.api_key = ""
        st.session_state.interviewer = None
        st.session_state.audio_path = ""
        st.session_state.question_1 = ""
        st.session_state.user_answer_1 = ""
        st.session_state.deep_dive_text = ""
        st.session_state.deep_dive_audio_path = ""
        st.session_state.user_answer_2 = ""
        st.session_state.eval_text = ""
        st.session_state.eval_audio_path = ""
        st.session_state.consistency_score = 90
        st.session_state.content_quality_score = 90
        st.session_state.eye_contact_score = 78
        st.session_state.overall_score = 90
        st.session_state.rank = "A"
        st.session_state.gaze_video_path = ""
        st.session_state.gaze_map_path = ""
        st.session_state.camera_index = 0
        st.session_state.api_test_result = None
        st.session_state.camera_test_result = None
        st.session_state.h_range = (0.40, 0.60)
        st.session_state.v_range = (0.38, 0.62)
        
        # 利用可能なカメラデバイスのスキャン（初回の重い処理）
        st.session_state.available_cameras = scan_available_cameras()
        st.session_state.initialized = True
        st.rerun()

def reset_session():
    """セッションの評価結果や進行情報を初期化し、SETUP画面へ安全に戻る処理を行います。"""
    # 進行中のカメラ録画スレッドを安全に停止
    stop_recorder()
    
    # テンポラリアセットの削除
    cleanup_temp_files()
    
    # 状態変数の初期化
    st.session_state.step = "SETUP"
    st.session_state.name = ""
    st.session_state.final_academic_background = ""
    st.session_state.tech_skills = ""
    st.session_state.qualifications = ""
    st.session_state.experienced_processes = []
    st.session_state.experienced_processes_content = ""
    st.session_state.es_data = {}
    st.session_state.es_pr = ""
    st.session_state.audio_path = ""
    st.session_state.question_1 = ""
    st.session_state.user_answer_1 = ""
    st.session_state.deep_dive_text = ""
    st.session_state.deep_dive_audio_path = ""
    st.session_state.user_answer_2 = ""
    st.session_state.eval_text = ""
    st.session_state.eval_audio_path = ""
    st.session_state.gaze_video_path = ""
    st.session_state.gaze_map_path = ""
    st.session_state.eye_contact_score = 78
    st.session_state.api_test_result = None
    st.session_state.camera_test_result = None
