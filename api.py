#!/usr/bin/env python3
"""mov2txt の文字起こしAPI

アップロード時にキーを返し、そのキーで状態を問い合わせる。
完了していれば文字起こし結果のCSVを返す。過去の結果を一覧する機能は持たない。

起動: python api.py
"""

import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import queue
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

BASE_DIR = Path(__file__).resolve().parent
TXT_DIR = BASE_DIR / "txt"
TMP_DIR = BASE_DIR / "tmp"
JOBS_DIR = TMP_DIR / "api"
MOV2TXT = BASE_DIR / "mov2txt.py"

HOST = "0.0.0.0"
PORT = 8000
RETENTION_HOURS = 24
MAX_UPLOAD_BYTES = 10 * 1024**3  # 10GB
CHUNK_SIZE = 1024 * 1024
CLEANUP_INTERVAL_SEC = 60
ALLOWED_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
}
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}$")
STEP_PATTERN = re.compile(r"\[(\d+)/(\d+)\]")

load_dotenv(BASE_DIR / ".env")
API_TOKEN = os.getenv("API_TOKEN")


@dataclass
class Job:
    key: str
    original_name: str
    input_path: Path
    language: str
    status: str = "queued"  # queued / running / done / failed
    finished_at: float | None = None
    error: str = ""

    @property
    def dir(self) -> Path:
        return JOBS_DIR / self.key

    @property
    def log_path(self) -> Path:
        return self.dir / "run.log"

    @property
    def result_path(self) -> Path:
        return self.dir / "result.csv"


@dataclass
class JobStore:
    jobs: dict[str, Job] = field(default_factory=dict)
    waiting: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    queue: "queue.Queue[str]" = field(default_factory=queue.Queue)


store = JobStore()


def current_step(job: Job) -> str | None:
    try:
        text = job.log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    matches = STEP_PATTERN.findall(text)
    if not matches:
        return None
    n, total = matches[-1]
    return f"{n}/{total}"


def log_tail(job: Job, lines: int = 20) -> str:
    try:
        text = job.log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    # 進捗表示の \r を改行として扱い、最後の数行だけ返す
    rows = [r for r in text.replace("\r", "\n").splitlines() if r.strip()]
    return "\n".join(rows[-lines:])


def remove_intermediate_files(job: Job) -> None:
    """mov2txt.py が作る一時ファイルと、アップロードされた元ファイルを削除する"""
    (TMP_DIR / f"{job.key}.wav").unlink(missing_ok=True)
    job.input_path.unlink(missing_ok=True)


def run_job(job: Job) -> None:
    with store.lock:
        job.status = "running"
        store.waiting.remove(job.key)

    cmd = [sys.executable, str(MOV2TXT), str(job.input_path), "--language", job.language]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        with open(job.log_path, "w", encoding="utf-8") as log:
            returncode = subprocess.run(
                cmd, cwd=BASE_DIR, stdout=log, stderr=subprocess.STDOUT, env=env
            ).returncode
        output_csv = TXT_DIR / f"{job.key}.csv"
        if returncode == 0 and output_csv.is_file():
            shutil.move(output_csv, job.result_path)
            status, error = "done", ""
        else:
            output_csv.unlink(missing_ok=True)
            status, error = "failed", log_tail(job)
    except Exception as e:  # noqa: BLE001 - ワーカーを止めないため
        status, error = "failed", f"{type(e).__name__}: {e}"
    finally:
        remove_intermediate_files(job)

    with store.lock:
        job.status = status
        job.error = error
        job.finished_at = time.time()


def cleanup_expired() -> None:
    limit = time.time() - RETENTION_HOURS * 3600
    with store.lock:
        expired = [
            key for key, job in store.jobs.items()
            if job.finished_at is not None and job.finished_at < limit
        ]
        for key in expired:
            del store.jobs[key]
    for key in expired:
        shutil.rmtree(JOBS_DIR / key, ignore_errors=True)


def worker() -> None:
    while True:
        try:
            key = store.queue.get(timeout=CLEANUP_INTERVAL_SEC)
        except queue.Empty:
            cleanup_expired()
            continue
        with store.lock:
            job = store.jobs.get(key)
        if job is not None:
            run_job(job)
        cleanup_expired()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # ジョブ情報はメモリ上にしかないため、前回起動時の残りは削除する
    shutil.rmtree(JOBS_DIR, ignore_errors=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    yield


app = FastAPI(
    title="mov2txt API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def require_token(authorization: str | None) -> None:
    expected = f"Bearer {API_TOKEN}"
    if authorization is None or not secrets.compare_digest(
        authorization.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="認証に失敗しました")


@app.post("/jobs", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    language: str = Form("ja"),
    authorization: str | None = Header(default=None),
):
    require_token(authorization)

    original_name = Path(file.filename or "upload").name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"対応していないファイル形式です: {ext or '(拡張子なし)'}")
    language = language.strip().lower()
    if language and not LANGUAGE_PATTERN.match(language):
        raise HTTPException(status_code=400, detail=f"言語コードが不正です: {language}")

    key = secrets.token_urlsafe(32)
    job_dir = JOBS_DIR / key
    job_dir.mkdir(parents=True)
    # stem をキーにして、mov2txt.py の tmp/<stem>.wav・txt/<stem>.csv が既存ファイルと衝突しないようにする
    input_path = job_dir / f"{key}{ext}"

    size = 0
    try:
        with open(input_path, "wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="ファイルが大きすぎます")
                out.write(chunk)
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    if size == 0:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="ファイルが空です")

    job = Job(key=key, original_name=original_name, input_path=input_path, language=language)
    with store.lock:
        store.jobs[key] = job
        store.waiting.append(key)
        position = len(store.waiting) - 1
    store.queue.put(key)

    return {"key": key, "status": "queued", "queue_position": position}


@app.get("/jobs/{key}")
def get_job(key: str):
    cleanup_expired()
    with store.lock:
        job = store.jobs.get(key)
        if job is None:
            raise HTTPException(status_code=404, detail="キーが見つかりません（期限切れの可能性があります）")
        status = job.status
        position = store.waiting.index(key) if status == "queued" else None
        error = job.error

    if status == "done":
        return FileResponse(
            job.result_path,
            media_type="text/csv; charset=utf-8",
            filename=f"{Path(job.original_name).stem}.csv",
        )
    if status == "failed":
        return JSONResponse(status_code=500, content={"status": "failed", "error": error})

    body = {"status": status}
    if status == "queued":
        body["queue_position"] = position
    else:
        body["step"] = current_step(job)
    return JSONResponse(status_code=202, content=body)


if __name__ == "__main__":
    if not API_TOKEN:
        print("[エラー] .env に API_TOKEN が設定されていません", file=sys.stderr)
        sys.exit(1)
    uvicorn.run(app, host=HOST, port=PORT, workers=1)
