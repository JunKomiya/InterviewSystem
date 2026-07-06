Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  AI面接練習システム を起動しています..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$ENV_DIR = Join-Path $PSScriptRoot ".python_env"
$PYTHON_EXE = Join-Path $ENV_DIR "python.exe"
$RUN_PYTHON = ""

# 1. システムに既に Python 3.12 がインストールされているかチェック
if (Get-Command "python3.12" -ErrorAction SilentlyContinue) {
    Write-Host "システム上の Python 3.12 を使用して起動します..." -ForegroundColor Green
    $RUN_PYTHON = "python3.12"
}
# 2. システムに Python 3.12 はないが、過去に作成したポータブル環境があるかチェック
elseif (Test-Path $PYTHON_EXE) {
    Write-Host "同梱のポータブル Python 環境を使用して起動します..." -ForegroundColor Green
    $RUN_PYTHON = $PYTHON_EXE
}
# 3. ポータブル環境の自動構築
else {
    Write-Host "Python 3.12 が見つかりません。" -ForegroundColor Yellow
    Write-Host "ポータブル環境の自動構築を開始します（初回のみ数分かかります）..." -ForegroundColor Yellow
    Write-Host ""

    if (-not (Test-Path $ENV_DIR)) {
        New-Item -ItemType Directory -Path $ENV_DIR | Out-Null
    }

    $TEMP_ZIP = Join-Path $env:TEMP "python_embed.zip"
    $TEMP_GET_PIP = Join-Path $env:TEMP "get-pip.py"

    # 3.1. ダウンロード
    Write-Host "[1/4] Python 3.12 ポータブルパッケージをダウンロード中..." -ForegroundColor Yellow
    try {
        curl.exe -L -o $TEMP_ZIP "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
    } catch {
        Write-Host "[エラー] Python のダウンロードに失敗しました。インターネット接続を確認してください。" -ForegroundColor Red
        Read-Host "続行するには Enter キーを押してください..."
        exit
    }

    # 3.2. 展開
    Write-Host "[2/4] パッケージを展開中..." -ForegroundColor Yellow
    tar.exe -xf $TEMP_ZIP -C $ENV_DIR
    Remove-Item $TEMP_ZIP

    # 3.3. pipのセットアップ
    Write-Host "[3/4] パッケージ管理ツール (pip) をセットアップ中..." -ForegroundColor Yellow
    $PTH_FILE = Join-Path $ENV_DIR "python312._pth"
    Add-Content -Path $PTH_FILE -Value "import site"

    try {
        curl.exe -L -o $TEMP_GET_PIP "https://bootstrap.pypa.io/get-pip.py"
        & $PYTHON_EXE $TEMP_GET_PIP --no-warn-script-location
        Remove-Item $TEMP_GET_PIP
    } catch {
        Write-Host "[エラー] pip のセットアップに失敗しました。" -ForegroundColor Red
        Read-Host "続行するには Enter キーを押してください..."
        exit
    }

    # 3.4. ライブラリのインストール
    Write-Host "[4/4] 必要なライブラリをインストール中 (これには少し時間がかかります)..." -ForegroundColor Yellow
    $PIP_EXE = Join-Path $ENV_DIR "Scripts\pip.exe"
    & $PIP_EXE install --no-warn-script-location --prefer-binary --no-compile -i https://mirrors.aliyun.com/pypi/simple/ streamlit mediapipe==0.10.14 opencv-python edge-tts google-genai numpy pandas openpyxl

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[エラー] ライブラリのインストールに失敗しました。" -ForegroundColor Red
        Read-Host "続行するには Enter キーを押してください..."
        exit
    }

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "  セットアップが完了しました！システムを起動します。" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host ""
    $RUN_PYTHON = $PYTHON_EXE
}

# 4. 起動処理
$env:PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="python"
if ($RUN_PYTHON -eq "python3.12") {
    python3.12 -m pip install --quiet --prefer-binary --no-compile -i https://mirrors.aliyun.com/pypi/simple/ streamlit mediapipe==0.10.14 opencv-python edge-tts google-genai numpy pandas openpyxl
    python3.12 -m streamlit run main.py
} else {
    & $RUN_PYTHON -m streamlit run main.py
}

