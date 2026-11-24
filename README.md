# mov2txt

長時間の動画・音声ファイルを、話者分離付きで文字起こしするCLIツール。

## 特徴

- 2時間以上の動画でも文字起こし可能
- WhisperXによる話者分離（誰がいつ話したかを識別）
- FFmpegが対応する動画・音声形式を入力可能（MP4, MKV, AVI, MOV, WAV, MP3等）
- 処理をステップごとに分けて進捗を表示

## 必要なソフト・環境

- Python 3.10以上
- FFmpeg
- CUDA対応のNVIDIA GPU + CUDAツールキット
- Hugging Faceアカウント（無料）とアクセストークン

## セットアップ

```bash
./setup.sh
```

これにより以下が行われます。

- Python / FFmpeg / GPUの確認
- venv作成・依存ライブラリのインストール
- `mov/`, `txt/`, `tmp/` フォルダの作成
- `.env` ファイルの雛形作成

### Hugging Faceトークンの設定

1. https://huggingface.co/settings/tokens でアクセストークンを発行
2. `.env` に設定

   ```
   HF_TOKEN=your_token_here
   ```

3. 話者分離モデルの利用条件に同意（初回のみ）

   以下のページにログイン状態でアクセスし、利用条件（gated）に同意してください。

   - https://huggingface.co/pyannote/speaker-diarization-community-1

   同意していない場合、実行時に話者分離のステップで403エラーになります。

## 使用方法

```bash
source venv/bin/activate
python mov2txt.py <filename> [--language <言語コード>]
```

- `filename` は `mov/` 内のファイル名、または任意のパスを指定可能
- `--language` は文字起こしの言語（既定: `ja`）。空文字 `""` を指定すると自動判定
- 出力は `txt/<ファイル名>.csv` に保存される

```bash
python mov2txt.py 会議.mp4                 # 日本語（既定）
python mov2txt.py talk.mp4 --language en   # 英語
python mov2txt.py clip.mp4 --language ""   # 自動判定
```

## API

外部のPCから音声・動画を送って文字起こしできます（`api.py`）。
アップロード時に返る**キー**で状態を問い合わせ、完了していればCSVを受け取ります。
キーを知っているジョブの結果しか取得できず、過去の結果や `txt/` の一覧を見る機能はありません。
クライアント側の詳しい使い方は [API_USAGE.md](API_USAGE.md) を参照してください。

### APIトークンの設定

アップロード時の認証に使うトークンを `.env` に設定します。推測されにくいランダムな文字列を、次のコマンドで生成してください。

```bash
# トークンを生成して表示する（43文字の英数字と - _）
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

生成と `.env` への追記は、プロジェクトのフォルダで次の1行を実行するだけでできます。

```bash
echo "API_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
```

このコマンドは次の3つの部分でできています。

| 部分 | 働き |
|---|---|
| `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` | Python の `secrets` モジュール（暗号用の乱数）で、32バイトのランダムな値を作り、URLでも使える43文字の文字列にして表示する |
| `"API_TOKEN=$( … )"` | `$( … )` の中のコマンドを実行し、その出力（生成した文字列）を `API_TOKEN=` の後ろに埋め込む |
| `echo … >> .env` | できあがった `API_TOKEN=…` の1行を `.env` の**末尾に追記**する（`>>` は追記。`>` にすると `.env` が上書きされて `HF_TOKEN` が消えるので注意） |

実行後、設定された値を確認します（この値をクライアントの利用者に渡します）。

```bash
grep '^API_TOKEN=' .env
```

- 実行するたびに1行追加されるため、**実行は1回だけ**にする。すでに `API_TOKEN` がある場合は、上の `grep` で確認してから実行する

`.env` には次の形で入ります。

```
API_TOKEN=your_api_token_here
```

- トークンを変更する場合は `.env` の `API_TOKEN=` の行を書き換え、APIを再起動する（古いトークンは使えなくなるので、クライアント側にも新しい値を伝える）
- トークンはメールやチャットに貼らず、できるだけ安全な方法でクライアントの利用者に渡す

### 起動

```bash
./run.sh             # http://0.0.0.0:8000 で待ち受け（停止は Ctrl+C）
```

`run.sh` は venv・`API_TOKEN`・API用ライブラリの有無を確認してから `api.py` を起動します（どのディレクトリから実行しても動作します）。

### 常時起動（systemd）

`./run.sh` はターミナルを閉じると停止します。PC起動時に自動で立ち上げ、常に動かしておく場合は systemd のサービスとして登録します。

#### 1. サービスファイルを作成する

`<ユーザー名>` と `/path/to/mov2txt` は自分の環境に合わせて置き換えてください（プロジェクトのフォルダで `whoami` と `pwd` を実行すると確認できます）。

```bash
sudo tee /etc/systemd/system/mov2txt-api.service > /dev/null <<'EOF'
[Unit]
Description=mov2txt API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<ユーザー名>
WorkingDirectory=/path/to/mov2txt
ExecStart=/path/to/mov2txt/run.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

| 項目 | 意味 |
|---|---|
| `User` | APIを動かすユーザー。venv や `.env` を読めるユーザーを指定する（root では動かさない） |
| `WorkingDirectory` / `ExecStart` | プロジェクトのフォルダと `run.sh` の絶対パス |
| `Restart=on-failure` | 異常終了したとき、5秒後（`RestartSec`）に自動で再起動する |
| `WantedBy=multi-user.target` | PC起動時に自動で起動する |

#### 2. 登録して起動する

```bash
sudo systemctl daemon-reload              # サービスファイルを読み込む
sudo systemctl enable --now mov2txt-api   # 自動起動を有効にし、今すぐ起動する
systemctl status mov2txt-api              # active (running) と表示されれば成功
```

#### よく使う操作

| 操作 | コマンド |
|---|---|
| 状態を確認する | `systemctl status mov2txt-api` |
| ログを見る（Ctrl+C で終了） | `journalctl -u mov2txt-api -f` |
| 再起動する | `sudo systemctl restart mov2txt-api` |
| 停止する | `sudo systemctl stop mov2txt-api` |
| 自動起動をやめる | `sudo systemctl disable --now mov2txt-api` |
| サービスを削除する | `disable --now` の後に `sudo rm /etc/systemd/system/mov2txt-api.service` → `sudo systemctl daemon-reload` |

- `.env`（`API_TOKEN` など）や `api.py` を変更したら、`restart` で反映させる
- 再起動するとジョブ情報（実行中・完了済み）は消える。処理中のジョブがないことを確認してから再起動する
- サービスとして動かしている間に `./run.sh` を手動で起動すると、ポート8000が重なって起動に失敗する
- 起動に失敗する場合は `journalctl -u mov2txt-api -n 50` でエラーを確認する（`run.sh` のエラー表示もここに出る）

### 使い方

```bash
# 1. アップロード（トークン必須）→ キーが返る
curl -H "Authorization: Bearer $API_TOKEN" \
     -F file=@会議.mp4 -F language=ja \
     http://<サーバーのIP>:8000/jobs
# => {"key":"...","status":"queued","queue_position":0}

# 2. 状態の問い合わせ（キーのみ）
curl http://<サーバーのIP>:8000/jobs/<key>
# 待機中: 202 {"status":"queued","queue_position":0}
# 実行中: 202 {"status":"running","step":"3/6"}
# 失敗  : 500 {"status":"failed","error":"<ログ末尾>"}

# 3. 完了していればCSVが返る（200）
curl -o 会議.csv http://<サーバーのIP>:8000/jobs/<key>
```

- `language` は省略すると `ja`。空文字にすると自動判定
- 同時に実行するのは1件だけで、残りは順番待ちになる
- 結果は完了から24時間で削除され、キーも無効になる（`api.py` の `RETENTION_HOURS`）
- ジョブ情報はメモリ上にのみ保持するため、APIを再起動すると実行中・完了済みのジョブはすべて破棄される
- 処理中のファイルは `tmp/api/<key>/` に置かれ、`txt/` には何も残らない

### 注意

- GPUを使う他のソフトウェアがVRAMを占有していると、メモリ不足（OOM）で失敗することがある。必要に応じて、実行前にそれらを停止しておく
- LAN内での利用を想定。HTTPのためトークンもキーも暗号化されない。外部から使う場合はVPNなどを経由する

## 処理の流れ

1. 音声抽出（FFmpegで16kHzモノラルWAVに変換 → `tmp/`）
2. Whisperモデルの読み込み（large-v3, float16）
3. 文字起こし（`--language` で指定した言語。未指定時は日本語）
4. タイムスタンプのアライメント
5. 話者分離（pyannote/speaker-diarization-community-1）
6. CSV書き出し

## 出力形式

- CSV（UTF-8 BOM付き）
- 列: `時間,発話者,発言`
- タイムスタンプ形式: `HH:MM:SS`
- 発話者: `SPEAKER_00`, `SPEAKER_01` … の形式（実名には変換されない）。話者を判定できなかった発言は `不明`

## フォルダ構成

| フォルダ | 用途 |
|---|---|
| `mov/` | 入力ファイル置き場 |
| `tmp/` | 一時ファイル（抽出した音声WAV）。再実行時に音声抽出をスキップできるよう処理後も保持 |
| `txt/` | 出力CSVの出力先 |

## 使用ライブラリ

- WhisperX（内部で faster-whisper + pyannote.audio を利用）
- python-dotenv（`.env` からHFトークンを読み込み）

## 注意事項

- `.env` には実際のトークンが入るため、gitや他者との共有時は取り扱いに注意
- 文字起こし結果（`txt/*.csv`）には会話内容がそのまま含まれるため、機密性に応じて取り扱いを検討すること
