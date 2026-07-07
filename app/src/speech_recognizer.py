import tempfile
import streamlit as st
from google import genai
from google.genai import types


def transcribe_audio_with_gemini(audio_file, api_key: str, mode: str = "AI") -> str:
    """
    Streamlitの st.audio_input で取得した音声をGeminiで文字起こしする。
    mode が MOCK の場合は空文字を返す。
    """

    if mode != "AI":
        return ""

    if not api_key:
        st.warning("音声認識にはGemini APIキーが必要です。")
        return ""

    if audio_file is None:
        return ""

    try:
        audio_bytes = audio_file.getvalue()

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/wav"
                ),
                "この音声を日本語の面接回答として自然な文章に文字起こししてください。余計な説明は不要です。"
            ],
        )

        return response.text.strip() if response.text else ""

    except Exception as e:
        st.error(f"音声認識に失敗しました: {e}")
        return ""


def render_speech_input(input_key: str) -> str:
    audio_file = st.audio_input(
        "マイクで回答を録音してください",
        key=f"audio_input_{input_key}"
    )

    transcript_key = f"transcript_{input_key}"

    if transcript_key not in st.session_state:
        st.session_state[transcript_key] = ""

    if audio_file is not None:
        if st.button("🎙️ 録音内容を文字起こしする", key=f"transcribe_btn_{input_key}"):
            with st.spinner("音声を文字起こししています..."):
                transcript = transcribe_audio_with_gemini(
                    audio_file=audio_file,
                    api_key=st.session_state.get("api_key", ""),
                    mode=st.session_state.get("mode", "MOCK")
                )

                if transcript:
                    st.session_state[transcript_key] = transcript

    return st.session_state[transcript_key]
