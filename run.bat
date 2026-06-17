@echo off
echo ==================================================
echo   AI面接練習システム を起動しています...
echo ==================================================
set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
python3.12 -m streamlit run main.py
pause
