"""주간 롱폼 컴필레이션 — 쇼츠는 유입, 수익은 롱폼 (RPM 10~20배).

최근 7일 발행분 중 성과 상위 쇼츠를 모아 16:9 롱폼(블러 배경 패딩)으로
재구성한다. 개별 클립은 이미 리스크 심사·운영자 승인을 통과한 것들이므로
롱폼은 승인 큐에서 최종 확인만 받는다.
"""
from __future__ import annotations

import json
import subprocess
import time

from .. import db, llm, schemas
from ..config import OUT_DIR, affiliates

MAX_ITEMS = 6
MIN_ITEMS = 3


def _top_jobs_of_week() -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            """SELECT j.id, COALESCE(p.avg_view_pct, j.priority/100.0) AS r
               FROM jobs j
               LEFT JOIN performance p ON p.job_id=j.id AND p.window='72h'
               WHERE j.state='DONE' AND j.category != 'longform'
                 AND j.updated_at >= ?
               ORDER BY r DESC LIMIT ?""",
            (time.time() - 7 * 86400, MAX_ITEMS)).fetchall()
    jobs = [db.get_job(r["id"]) for r in rows]
    return [j for j in jobs if (OUT_DIR / f"{j['id']}.mp4").exists()]


def _concat_16x9(items: list[dict], out_path) -> None:
    """세로 쇼츠들 → 블러 배경 패딩 16:9 → concat (단일 ffmpeg 명령)."""
    inputs, f = [], []
    for i, job in enumerate(items):
        inputs += ["-i", str(OUT_DIR / f"{job['id']}.mp4")]
        f.append(
            f"[{i}:v]split[a{i}][b{i}];"
            f"[a{i}]scale=1920:1080,boxblur=24[bg{i}];"
            f"[b{i}]scale=-1:1080[fg{i}];"
            f"[bg{i}][fg{i}]overlay=(W-w)/2:0,fps=30[v{i}];"
            f"[{i}:a]aresample=44100[a_{i}]")
    f.append("".join(f"[v{i}][a_{i}]" for i in range(len(items)))
             + f"concat=n={len(items)}:v=1:a=1[v][a]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(f),
           "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"longform ffmpeg failed: {proc.stderr[-1500:]}")


def build_weekly(track_id: str = "kr") -> int | None:
    items = _top_jobs_of_week()
    if len(items) < MIN_ITEMS:
        return None

    titles = [j["payload"].get("title", j["source_title"]) for j in items]
    meta_llm = llm.complete_json(
        "아래 쇼츠들을 묶은 주간 롱폼 컴필레이션의 제목(60자 이내, 낚시 금지)과 "
        "설명 2문장을 만들어라. 형식: '이번 주 해외 이슈 TOP" + str(len(items))
        + "' 계열.\n\n꼭지들:\n" + "\n".join(f"- {t}" for t in titles),
        schemas.LONGFORM, tier="light", max_tokens=1000)

    job_id = db.create_job(
        track_id, category="longform", license_type="commentary",
        source_url="compilation", source_title=meta_llm["title"], priority=100,
        payload={"title": meta_llm["title"], "member_jobs": [j["id"] for j in items]})
    # 컴필레이션은 M2~M4를 건너뛴다 — 상태 머신 순서만 유지
    for st in ["RIGHTS_OK", "ACQUIRED", "ANALYZED", "EDITED"]:
        db.transition(job_id, st)

    tmp = OUT_DIR / f"{job_id}.tmp.mp4"
    _concat_16x9(items, tmp)
    tmp.rename(OUT_DIR / f"{job_id}.mp4")

    credits = [f"- {j['payload'].get('title')}: 원본 {j['source_url']}"
               for j in items if j["license_type"] in ("commentary", "cc_by")]
    aff = sorted({line for j in items
                  for line in affiliates().get(j["category"], [])})
    desc = "\n".join([meta_llm["description"], "", "이번 주 꼭지 원본 출처:",
                      *credits, *([""] + aff if aff else [])])
    (OUT_DIR / f"{job_id}.json").write_text(json.dumps({
        "job_id": job_id, "title": meta_llm["title"],   # 롱폼 — #Shorts 태그 없음
        "description": desc,
        "tags": list({k for j in items
                      for k in j["payload"].get("script", {}).get("keywords", [])})[:15],
        "duration": 0, "file": f"{job_id}.mp4",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    db.transition(job_id, "RENDERED")
    return job_id
