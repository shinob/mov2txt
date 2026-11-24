# mov2txt API 利用ガイド（クライアント向け）

別のPCから音声・動画ファイルを送り、話者分離付きの文字起こし結果（CSV）を受け取るための手順です。
サーバー側のセットアップは [README.md](README.md) の「API」を参照してください。

## 全体の流れ

1. ファイルをアップロードする → **キー**が返る
2. キーで状態を問い合わせる → 待機中・実行中なら状態が返る
3. 完了していれば、同じ問い合わせで **CSV** が返る

- 取得できるのは、自分がアップロードしたジョブ（キーを知っているジョブ）の結果だけです
- 結果は完了から **24時間** で削除されます。それまでに受け取ってください
- サーバーでは同時に1件ずつ処理するため、混んでいるときは順番待ちになります

## 事前に用意するもの

サーバーの管理者から次の2つを受け取ってください。

| 項目 | 例 |
|---|---|
| サーバーのURL | `http://<サーバーのIP>:8000` |
| APIトークン | 長いランダムな文字列 |

以下の例では、環境変数に入れておく前提で書いています。

```bash
# Linux / macOS
export MOV2TXT_URL="http://<サーバーのIP>:8000"
export MOV2TXT_TOKEN="<APIトークン>"
```

```powershell
# Windows (PowerShell)
$env:MOV2TXT_URL = "http://<サーバーのIP>:8000"
$env:MOV2TXT_TOKEN = "<APIトークン>"
```

## 1. アップロード

```bash
curl -H "Authorization: Bearer $MOV2TXT_TOKEN" \
     -F "file=@会議.mp4" \
     -F "language=ja" \
     "$MOV2TXT_URL/jobs"
```

応答（202）:

```json
{"key": "Xr3...長い文字列...9fQ", "status": "queued", "queue_position": 0}
```

- `key` を控えておきます。**キーを知っている人は誰でも結果を取得できる**ので、他人に渡さないでください
- `queue_position` は自分より前に待っている件数です（0 なら次に実行されます）
- `language` は文字起こしの言語です。省略すると `ja`（日本語）。英語なら `en`、空文字 `language=` にすると自動判定します
- 対応形式: mp4, mkv, avi, mov, webm, flv, wmv, m4v, ts, wav, mp3, m4a, aac, flac, ogg, opus, wma（最大10GB）

## 2. 状態の問い合わせ / 3. 結果の受け取り

```bash
curl -i "$MOV2TXT_URL/jobs/<key>"
```

問い合わせにトークンは不要です。応答はHTTPステータスで見分けます。

| ステータス | 意味 | 本文 |
|---|---|---|
| 202 | 順番待ち | `{"status": "queued", "queue_position": 1}` |
| 202 | 実行中 | `{"status": "running", "step": "3/6"}`（6段階中の何段階目か） |
| **200** | **完了** | **CSVファイル** |
| 500 | 失敗 | `{"status": "failed", "error": "<処理ログの末尾>"}` |
| 404 | キーが存在しない・期限切れ | `{"detail": "..."}` |

完了していれば、そのままファイルに保存します。

```bash
curl -o 会議.csv "$MOV2TXT_URL/jobs/<key>"
```

処理には音声の長さに応じた時間がかかります（長時間の録音では数十分以上かかることもあります）。問い合わせは **30〜60秒おき** 程度にしてください。

## 出力CSVの形式

- 文字コード: UTF-8（BOM付き。Excelでそのまま開けます）
- 列: `時間,発話者,発言`

```csv
時間,発話者,発言
00:00:01,SPEAKER_01,それでは始めさせていただきます
00:00:30,SPEAKER_02,よろしくお願いします
```

- 時間は発言開始時刻（`HH:MM:SS`）
- 発話者は `SPEAKER_00`, `SPEAKER_01` … のラベルです（実名にはなりません）。判定できなかった発言は `不明`

## まとめて実行するスクリプト例

アップロードから結果の保存までを自動で行う例です。

### Bash（Linux / macOS）

```bash
#!/usr/bin/env bash
# 使い方: ./transcribe.sh 会議.mp4 [言語コード]
set -euo pipefail

file="$1"
lang="${2:-ja}"
out="${file%.*}.csv"

key=$(curl -sf -H "Authorization: Bearer $MOV2TXT_TOKEN" \
           -F "file=@$file" -F "language=$lang" \
           "$MOV2TXT_URL/jobs" | python3 -c 'import sys, json; print(json.load(sys.stdin)["key"])')
echo "キー: $key"

while true; do
    code=$(curl -s -o "$out.part" -w '%{http_code}' "$MOV2TXT_URL/jobs/$key")
    case "$code" in
        200) mv "$out.part" "$out"; echo "完了: $out"; break ;;
        202) echo "$(date +%T) $(cat "$out.part")"; sleep 30 ;;
        *)   echo "エラー ($code): $(cat "$out.part")" >&2; rm -f "$out.part"; exit 1 ;;
    esac
done
```

### Python（Windows / macOS / Linux 共通）

`pip install requests` が必要です。

```python
#!/usr/bin/env python3
"""使い方: python transcribe.py 会議.mp4 [言語コード]"""
import os
import sys
import time
from pathlib import Path

import requests

URL = os.environ["MOV2TXT_URL"]
TOKEN = os.environ["MOV2TXT_TOKEN"]

src = Path(sys.argv[1])
lang = sys.argv[2] if len(sys.argv) > 2 else "ja"

with open(src, "rb") as f:
    r = requests.post(
        f"{URL}/jobs",
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={"file": (src.name, f)},
        data={"language": lang},
    )
r.raise_for_status()
key = r.json()["key"]
print(f"キー: {key}")

while True:
    r = requests.get(f"{URL}/jobs/{key}")
    if r.status_code == 200:
        out = src.with_suffix(".csv")
        out.write_bytes(r.content)
        print(f"完了: {out}")
        break
    if r.status_code == 202:
        print(time.strftime("%H:%M:%S"), r.json())
        time.sleep(30)
        continue
    sys.exit(f"エラー ({r.status_code}): {r.text}")
```

### Windows（PowerShell）で手動実行する場合

PowerShell では `curl` が別のコマンドを指すことがあるため、**`curl.exe`** と書いてください。

```powershell
# アップロード
curl.exe -H "Authorization: Bearer $env:MOV2TXT_TOKEN" -F "file=@会議.mp4" -F "language=ja" "$env:MOV2TXT_URL/jobs"

# 状態の確認（ステータスコードも表示）
curl.exe -s -w " %{http_code}`n" "$env:MOV2TXT_URL/jobs/<key>"

# 完了していれば保存
curl.exe -o 会議.csv "$env:MOV2TXT_URL/jobs/<key>"
```

## エラーと対処

| 症状 | 原因と対処 |
|---|---|
| 401 `認証に失敗しました` | トークンが違うか、`Authorization: Bearer ` の書き方が間違っている |
| 400 `対応していないファイル形式です` | 拡張子が対応形式にない。FFmpeg などで mp3 / wav に変換して送る |
| 400 `ファイルが空です` / `言語コードが不正です` | ファイルの指定（`@` の付け忘れなど）や言語コード（`ja`, `en` など）を確認 |
| 413 `ファイルが大きすぎます` | 10GBを超えている。音声だけを抽出（mp3 / m4a など）して送る |
| 404 `キーが見つかりません` | キーの写し間違い、24時間の保持期限切れ、またはサーバーの再起動。再度アップロードする |
| 500 `failed` | サーバー側の処理が失敗した。`error` の内容を添えて管理者に連絡する（GPUのメモリ不足などの場合は、時間をおいて再実行すると成功することがあります） |
| 接続できない | URL・ポート番号の確認、同じネットワーク（またはVPN）に接続しているか、サーバーでAPIが起動しているかを確認 |

## 注意事項

- 通信はHTTP（暗号化なし）です。社外ネットワークから直接使わず、LAN内またはVPN経由で利用してください
- 会議の録音など機密性のある内容を扱う場合、受け取ったCSVの保管にも注意してください
- サーバーが再起動されると、処理中・完了済みのジョブはすべて消えます。その場合は再度アップロードしてください
