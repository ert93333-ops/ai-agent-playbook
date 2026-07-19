"""M4 — 편집 결정: 대본+TTS 실측 길이 → 타임라인 JSON 컴파일 + 규칙 검증."""
from __future__ import annotations

import json

from .. import db
from ..config import job_dir, tracks
from ..editing import timeline as tl
from ..editing import tts


def edit(job: dict) -> None:
    d = job_dir(job["id"])
    track = tracks()[job["track_id"]]
    params = job["payload"]["resolved_params"]
    script = job["payload"]["script"]

    narration = tts.synthesize(
        [p["text"] for p in script["script"]],
        voice=params.get("tts_voice", track.tts_voice),
        rate=params.get("tts_rate", track.tts_rate),
        out_dir=d / "tts")

    timeline = tl.compile_timeline(
        job_id=job["id"], clips=script["clips"], script=script["script"],
        narration=narration, params=params, license_type=job["license_type"])

    (d / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    db.transition(job["id"], "EDITED")


def run() -> None:
    for job in db.jobs_in_state("ANALYZED"):
        try:
            edit(job)
        except tl.TransformRuleViolation as e:
            # 변형 규칙 위반은 재시도 무의미 — 즉시 실패 처리 (SPEC 0-1-1)
            db.transition(job["id"], "FAILED", error=f"transform-rule: {e}")
        except Exception as e:  # noqa: BLE001
            db.record_failure(job["id"], f"edit: {e}")
