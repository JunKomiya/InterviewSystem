@echo off
setlocal enabledelayedexpansion
echo ==================================================
echo   Starting AI Interview System...
echo ==================================================

set "ENV_DIR=%~dp0app\.python_env"
set "PYTHON_EXE=%ENV_DIR%\python.exe"

where python3.12 >nul 2>nul
if %errorlevel% equ 0 (
    echo Using system Python 3.12...
    set "RUN_PYTHON=python3.12"
    goto START_APP
)

if exist "%PYTHON_EXE%" (
    echo Using portable Python environment...
    set "RUN_PYTHON=%PYTHON_EXE%"
    goto START_APP
)

echo Python 3.12 not found.
echo Starting automatic setup (takes a few minutes)...
echo.

if not exist "%ENV_DIR%" mkdir "%ENV_DIR%"

echo [1/4] Downloading Python 3.12...
curl -L -o "%TEMP%\python_embed.zip" https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip
if %errorlevel% neq 0 (
    echo [Error] Failed to download Python.
    goto ERROR_EXIT
)

echo [2/4] Extracting package...
tar -xf "%TEMP%\python_embed.zip" -C "%ENV_DIR%"
del "%TEMP%\python_embed.zip"

echo [3/4] Setting up pip...
echo import site>> "%ENV_DIR%\python312._pth"

curl -L -o "%TEMP%\get-pip.py" https://bootstrap.pypa.io/get-pip.py
if %errorlevel% neq 0 (
    echo [Error] Failed to download pip.
    goto ERROR_EXIT
)
"%PYTHON_EXE%" "%TEMP%\get-pip.py" --no-warn-script-location
del "%TEMP%\get-pip.py"

echo [4/4] Installing required libraries (Streamlit, MediaPipe, OpenCV, etc.)...
"%ENV_DIR%\Scripts\pip.exe" install --no-warn-script-location --prefer-binary --no-compile -i https://mirrors.aliyun.com/pypi/simple/ streamlit mediapipe==0.10.14 opencv-python edge-tts google-genai numpy pandas openpyxl
if %errorlevel% neq 0 (
    echo [Error] Failed to install libraries.
    goto ERROR_EXIT
)


echo.
echo ==================================================
echo   Setup completed! Launching system...
echo ==================================================
echo.
set "RUN_PYTHON=%PYTHON_EXE%"

:START_APP
cd /d "%~dp0app"
set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
if "%RUN_PYTHON%"=="python3.12" (
    python3.12 -m pip install --quiet --prefer-binary --no-compile -i https://mirrors.aliyun.com/pypi/simple/ streamlit mediapipe==0.10.14 opencv-python edge-tts google-genai numpy pandas openpyxl
    python3.12 -m streamlit run main.py
) else (
    "%RUN_PYTHON%" -m streamlit run main.py
)
pause
exit /b

:ERROR_EXIT
echo.
echo [Error] Setup failed.
echo Please check your internet connection and run run.bat again.
pause
exit /b
