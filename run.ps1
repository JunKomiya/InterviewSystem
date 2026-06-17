Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  AI面接練習システム を起動しています..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
$env:PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="python"
python3.12 -m streamlit run main.py
