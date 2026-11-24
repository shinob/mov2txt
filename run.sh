#!/usr/bin/env bash
# mov2txt API（api.py）を起動する
#
# 使い方: ./run.sh
#   停止は Ctrl+C

set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

if [[ ! -x venv/bin/python ]]; then
    echo "[エラー] venv が見つかりません。先に ./setup.sh を実行してください" >&2
    exit 1
fi

if ! grep -qE '^API_TOKEN=.+' .env 2>/dev/null; then
    echo "[エラー] .env に API_TOKEN が設定されていません" >&2
    echo "  例: echo \"API_TOKEN=\$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')\" >> .env" >&2
    exit 1
fi

if ! venv/bin/python -c "import fastapi, uvicorn, multipart" 2>/dev/null; then
    echo "[エラー] API用のライブラリが入っていません。次を実行してください" >&2
    echo "  venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

exec venv/bin/python api.py
