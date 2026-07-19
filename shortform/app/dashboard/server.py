"""승인 큐 + 상태 보드 (FastAPI, 로컬 전용).

Level 0~1 기간의 운영자 승인/반려가 M10의 학습 데이터가 되므로,
반려 시 사유 입력을 강제한다 (PLAYBOOK §6-5).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .. import db, policy
from ..config import OUT_DIR

app = FastAPI(title="shortform dashboard")
INDEX = Path(__file__).parent / "index.html"


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
