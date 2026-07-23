#!/bin/bash
set -e

echo "=== mov2txt セットアップ ==="

# 前提チェック: Python
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[エラー] Python が見つかりません"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    echo "[エラー] Python 3.10以上が必要です（現在: $PYTHON_VERSION）"
    exit 1
fi
echo "[OK] Python $PYTHON_VERSION"

# 前提チェック: FFmpeg
if command -v ffmpeg &>/dev/null; then
    echo "[OK] FFmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
else
    echo "[エラー] FFmpeg が見つかりません。インストールしてください"
    exit 1
fi

# 前提チェック: CUDA
if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    echo "[OK] GPU: $GPU_NAME"
else
    echo "[警告] nvidia-smi が見つかりません。CPU モードで動作します"
fi

# 仮想環境の作成
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ -d "$VENV_DIR" ]; then
    echo "[スキップ] 仮想環境は既に存在します"
else
    echo "仮想環境を作成中..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo "[OK] 仮想環境を作成しました"
fi

# 仮想環境の有効化
source "$VENV_DIR/bin/activate"
echo "[OK] 仮想環境を有効化しました"

# ライブラリのインストール
echo "ライブラリをインストール中..."
pip install -r "$SCRIPT_DIR/requirements.txt"
echo "[OK] ライブラリのインストール完了"

# フォルダの作成
for dir in mov txt tmp; do
    mkdir -p "$SCRIPT_DIR/$dir"
done
echo "[OK] フォルダを作成しました (mov/, txt/, tmp/)"

# .envファイルの確認
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "HF_TOKEN=your_token_here" > "$ENV_FILE"
    echo "[警告] .env ファイルを作成しました。HF_TOKEN を設定してください"
elif grep -q "your_token_here" "$ENV_FILE"; then
    echo "[警告] .env の HF_TOKEN がまだ設定されていません"
else
    echo "[OK] .env ファイル確認済み"
fi

echo ""
echo "=== セットアップ完了 ==="
echo "仮想環境を有効化するには: source venv/bin/activate"
