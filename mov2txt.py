#!/usr/bin/env python3
"""動画・音声ファイルの音声を文字起こしし、話者分離付きCSVを出力する"""

import argparse
import csv
import gc
import os
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
MOV_DIR = BASE_DIR / "mov"
TXT_DIR = BASE_DIR / "txt"
TMP_DIR = BASE_DIR / "tmp"

WHISPER_MODEL = "large-v3"
COMPUTE_TYPE = "float16"
BATCH_SIZE = 16
DEVICE = "cuda"
TOTAL_STEPS = 6


def log_step(step: int, message: str) -> None:
    print(f"\n[{step}/{TOTAL_STEPS}] {message}")


def resolve_input_path(filename: str) -> Path:
    direct = Path(filename)
    if direct.is_file():
        return direct
    candidate = MOV_DIR / filename
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"入力ファイルが見つかりません: {filename}（mov/ ディレクトリも確認しました）"
    )


def extract_audio(input_path: Path) -> Path:
    TMP_DIR.mkdir(exist_ok=True)
    wav_path = TMP_DIR / f"{input_path.stem}.wav"
    if wav_path.is_file():
        print(f"  既存の音声ファイルを再利用します: {wav_path}")
        return wav_path

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ac", "1", "-ar", "16000", "-vn",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        wav_path.unlink(missing_ok=True)
        raise RuntimeError(f"音声抽出に失敗しました:\n{result.stderr}")
    print(f"  音声を抽出しました: {wav_path}")
    return wav_path


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def make_progress_printer(label: str):
    last = {"pct": -1}

    def callback(pct: float) -> None:
        pct_int = int(pct)
        if pct_int != last["pct"]:
            last["pct"] = pct_int
            end = "\n" if pct_int >= 100 else ""
            print(f"\r  {label}: {pct_int:3d}%", end=end, flush=True)

    return callback


def write_csv(result: dict, output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["時間", "発話者", "発言"])
        for seg in result.get("segments", []):
            timestamp = format_timestamp(seg.get("start", 0.0))
            speaker = seg.get("speaker", "不明")
            text = seg.get("text", "").strip()
            writer.writerow([timestamp, speaker, text])


def check_prerequisites(hf_token: str | None) -> None:
    if shutil.which("ffmpeg") is None:
        print("[エラー] FFmpeg が見つかりません", file=sys.stderr)
        sys.exit(1)
    if not torch.cuda.is_available():
        print("[エラー] CUDA対応GPUが見つかりません", file=sys.stderr)
        sys.exit(1)
    if not hf_token:
        print("[エラー] .env に HF_TOKEN が設定されていません", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="動画・音声ファイルを文字起こしします")
    parser.add_argument("filename", help="mov/ 内のファイル名、または動画・音声ファイルへのパス")
    args = parser.parse_args()

    load_dotenv(BASE_DIR / ".env")
    hf_token = os.getenv("HF_TOKEN")
    check_prerequisites(hf_token)

    try:
        input_path = resolve_input_path(args.filename)
    except FileNotFoundError as e:
        print(f"[エラー] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"入力ファイル: {input_path}")

    import whisperx
    from whisperx.diarize import DiarizationPipeline, assign_word_speakers

    log_step(1, "音声を抽出しています...")
    wav_path = extract_audio(input_path)
    audio = whisperx.load_audio(str(wav_path))

    log_step(2, "Whisperモデルを読み込んでいます...")
    model = whisperx.load_model(WHISPER_MODEL, device=DEVICE, compute_type=COMPUTE_TYPE)

    log_step(3, "文字起こしを実行しています...")
    result = model.transcribe(audio, batch_size=BATCH_SIZE, print_progress=True)
    language = result.get("language", "ja")
    print(f"  検出言語: {language}")

    del model
    gc.collect()
    torch.cuda.empty_cache()

    log_step(4, "タイムスタンプを調整しています...")
    align_model, align_metadata = whisperx.load_align_model(language_code=language, device=DEVICE)
    result = whisperx.align(
        result["segments"], align_model, align_metadata, audio, DEVICE, print_progress=True
    )

    del align_model
    gc.collect()
    torch.cuda.empty_cache()

    log_step(5, "話者分離を実行しています...")
    diarize_model = DiarizationPipeline(token=hf_token, device=DEVICE)
    diarize_segments = diarize_model(audio, progress_callback=make_progress_printer("話者分離"))
    result = assign_word_speakers(diarize_segments, result)

    del diarize_model
    gc.collect()
    torch.cuda.empty_cache()

    log_step(6, "CSVファイルを書き出しています...")
    TXT_DIR.mkdir(exist_ok=True)
    output_path = TXT_DIR / f"{input_path.stem}.csv"
    write_csv(result, output_path)
    print(f"  出力しました: {output_path}")

    print("\n完了しました。")


if __name__ == "__main__":
    main()
