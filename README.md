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
python mov2txt.py <filename>
```

- `filename` は `mov/` 内のファイル名、または任意のパスを指定可能
- 出力は `txt/<ファイル名>.csv` に保存される

## 処理の流れ

1. 音声抽出（FFmpegで16kHzモノラルWAVに変換 → `tmp/`）
2. Whisperモデルの読み込み（large-v3, float16）
3. 文字起こし
4. タイムスタンプのアライメント
5. 話者分離（pyannote/speaker-diarization-community-1）
6. CSV書き出し

## 出力形式

- CSV（UTF-8 BOM付き）
- 列: `時間,発話者,発言`
- タイムスタンプ形式: `HH:MM:SS`

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
