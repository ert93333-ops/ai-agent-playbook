"""M5 — 렌더링: 타임라인 → ffmpeg 실행 → out/ mp4 + 메타데이터 JSON."""
from __future__ import annotations

import json
import subprocess

from .. import db
from ..config import ASSETS_DIR, OUT_DIR, job_dir
from ..editing import ffmpeg_graph, subtitles


def render(job: dict) -> None:
    d = job_dir(job["id"])
    timeline = json.loads((d / "timeline.json").read_text(encoding="utf-8"))
    params = job["payload"]["resolved_params"]

    ass = subtitles.write_ass(
        timeline["subtitles"], d / "subs.ass",
        size=params.get("sub_font_size", 84),
        align=params.get("sub_align", "bottom"),
        margin_v=params.get("sub_margin_v", 560))

    OUT_DIR.mkdir(exist_ok=True)
    out_mp4 = OUT_DIR / f"{job['id']}.mp4"
    tmp_mp4 = OUT_DIR / f"{job['id']}.tmp.mp4"
    cmd = ffmpeg_graph.build_command(
        timeline, source=d / "source.mp4", ass_path=ass, tts_dir=d / "tts",
        out_path=tmp_mp4, logo=ASSETS_DIR / "logo-badge-v1.png")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-1500:]}")
    tmp_mp4.rename(out_mp4)   # 원자적 완성 (PLAYBOOK §6-1 멱등성)

    meta = {
        "job_id": job["id"],
        "title": job["payload"]["title"] + " #Shorts",
        "description": _description(job),
        "tags": job["payload"]["script"].get("keywords", []),
        "duration": timeline["duration"],
        "file": out_mp4.name,
    }
    (OUT_DIR / f"{job['id']}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    db.transition(job["id"], "RENDERED")


def _description(job: dict) -> str:
    lines = [job["payload"]["title"], ""]
    # 출처 표기 — commentary/cc_by는 원본 크레딧 필수 (SPEC 0-1-1)
    if job["license_type"] in ("commentary", "cc_by"):
        lines += [f"원본: {job['payload'].get('source_channel', '')} "
                  f"({job['source_url']})",
                  "해설·편집: 본 채널 제작"]
    return "\n".join(lines)


def run() -> None:
    for job in db.jobs_in_state("EDITED"):
        try:
            render(job)
        except Exception as e:  # noqa: BLE001
            db.record_failure(job["id"], f"render: {e}")
