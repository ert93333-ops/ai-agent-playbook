"""M2 — 소스 확보. 권리 게이트(하드)를 통과한 job만 다운로드한다."""
from __future__ import annotations

import shutil
import subprocess

from .. import db
from ..config import ALLOWED_LICENSES, job_dir


def rights_gate(job: dict) -> bool:
    """SPEC 0-1: license_type 미기록/미허용이면 BLOCKED_RIGHTS."""
    lic = job.get("license_type")
    if lic not in ALLOWED_LICENSES:
        db.transition(job["id"], "BLOCKED_RIGHTS",
                      error=f"license_type={lic!r} not allowed")
        return False
    db.transition(job["id"], "RIGHTS_OK")
    return True


def _download(url: str, dest) -> None:
    import yt_dlp
    opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "outtmpl": str(dest / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


def acquire(job: dict) -> None:
    d = job_dir(job["id"])
    src = d / "source.mp4"
    if not src.exists():
        local = job["payload"].get("local_path")
        if local:
            shutil.copy(local, src)
        else:
            _download(job["source_url"], d)
    if not src.exists():
        raise FileNotFoundError("source.mp4 missing after acquire")
    # 오디오 분리 (전사·분석용)
    wav = d / "source.wav"
    if not wav.exists():
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-ac", "1",
                        "-ar", "16000", str(wav)],
                       check=True, capture_output=True)
    db.transition(job["id"], "ACQUIRED")


def run() -> None:
    for job in db.jobs_in_state("DISCOVERED"):
        if rights_gate(job):
            job = db.get_job(job["id"])
            try:
                acquire(job)
            except Exception as e:  # noqa: BLE001
                db.record_failure(job["id"], f"acquire: {e}")
