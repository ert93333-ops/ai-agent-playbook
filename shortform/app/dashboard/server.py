"""승인 큐 + 상태 보드 + 조작 GUI (FastAPI, 로컬 전용).

Level 0~1 기간의 운영자 승인/반려가 M10의 학습 데이터가 되므로,
반려 시 사유 입력을 강제한다 (PLAYBOOK §6-5).
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .. import db, policy
from ..config import OUT_DIR, WORK_DIR, settings

app = FastAPI(title="shortform dashboard")
INDEX = Path(__file__).parent / "index.html"

_run = {"running": False, "log": []}


def _log(msg: str) -> None:
    _run["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _pipeline_thread() -> None:
    from .. import policy as pol
    from ..stages import m2_acquire, m3_analyze, m4_edit, m5_render
    steps = [("소스 확보(M2)", m2_acquire.run),
             ("전사·대본 생성(M3)", m3_analyze.run),
             ("편집(M4)", m4_edit.run),
             ("렌더링(M5)", m5_render.run),
             ("리스크 심사(M10)", pol.run)]
    try:
        for name, fn in steps:
            _log(f"{name} 시작...")
            fn()
        _log("파이프라인 완료 — 아래 목록에서 RENDERED 영상을 확인하세요.")
    except Exception as e:  # noqa: BLE001
        _log(f"오류: {e}")
    finally:
        _run["running"] = False


@app.get("/api/setup")
def setup_check() -> dict:
    s = settings()
    checks = {
        "anthropic_key": bool(s.anthropic_api_key),
        "youtube_key": bool(s.youtube_api_key),
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }
    try:
        import faster_whisper  # noqa: F401
        checks["whisper"] = True
    except ImportError:
        checks["whisper"] = False
    return checks


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...), title: str = Form(...)) -> dict:
    dest_dir = WORK_DIR / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{int(time.time())}_{Path(file.filename or 'video.mp4').name}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    job_id = db.create_job(
        "kr", category="global_meme", license_type="own",
        source_url=f"file://{dest}", source_title=title, priority=100,
        payload={"local_path": str(dest), "angle_hint": "", "video_id": ""})
    _log(f"영상 등록됨 (job {job_id}): {title}")
    return {"job_id": job_id}


@app.post("/api/run")
def run_pipeline() -> dict:
    if _run["running"]:
        raise HTTPException(409, "이미 실행 중입니다")
    _run.update(running=True, log=[])
    threading.Thread(target=_pipeline_thread, daemon=True).start()
    return {"ok": True}


@app.get("/api/run/log")
def run_log() -> dict:
    return {"running": _run["running"], "log": _run["log"][-100:]}


@app.post("/api/discover")
def run_discover() -> dict:
    """해외 트렌드 스캔 (YouTube API 키 필요)."""
    if not settings().youtube_api_key:
        raise HTTPException(400, ".env에 YOUTUBE_API_KEY가 필요합니다")
    from ..stages import m1_discover
    created = m1_discover.run()
    _log(f"트렌드 스캔 완료 — 신규 소재 {len(created)}건")
    return {"created": len(created)}


class Decision(BaseModel):
    approve: bool
    reason: str = ""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


@app.get("/api/jobs")
def jobs() -> list[dict]:
    states = ["DISCOVERED", "RIGHTS_OK", "ACQUIRED", "ANALYZED", "EDITED",
              "RENDERED", "APPROVED", "PUBLISHED_YT", "DONE",
              "FAILED", "REJECTED", "BLOCKED_RIGHTS"]
    out = []
    for st in states:
        for j in db.jobs_in_state(st):
            out.append({k: j[k] for k in
                        ("id", "track_id", "state", "category", "source_title",
                         "priority", "error")}
                       | {"title": j["payload"].get("title"),
                          "policy": j["payload"].get("policy")})
    return out


@app.get("/api/preview/{job_id}")
def preview(job_id: int) -> FileResponse:
    path = OUT_DIR / f"{job_id}.mp4"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/decide/{job_id}")
def decide(job_id: int, d: Decision) -> dict:
    if not d.approve and not d.reason.strip():
        raise HTTPException(400, "반려 사유는 필수입니다 (학습 데이터)")
    policy.operator_decide(job_id, d.approve, d.reason)
    return {"ok": True}


@app.get("/api/autonomy")
def autonomy() -> list[dict]:
    from ..config import enabled_tracks
    out = []
    for t in enabled_tracks():
        rate, n = policy.engine_operator_agreement(t.id)
        out.append({"track": t.id, "level": db.autonomy_level(t.id),
                    "agreement": round(rate, 3), "samples": n})
    return out


@app.post("/api/autonomy/{track_id}/{level}")
def set_level(track_id: str, level: int) -> dict:
    """승급은 운영자 수동 확정 (SPEC 0-2). 강등은 서킷브레이커가 자동."""
    if not 0 <= level <= 3:
        raise HTTPException(400)
    db.set_autonomy_level(track_id, level)
    return {"ok": True}
