"""M10 — 승인 정책 엔진 + 발행 게이트 (단계적 자율화, SPEC 0-2).

리스크 축(LLM 심사, 보수적)과 성과 축(템플릿 통계)을 분리한다.
성과가 아무리 좋아도 리스크 임계 초과면 자동 발행 불가.

Level 0: 전건 수동 / 1: 섀도(예측만) / 2: 부분 자동 / 3: 전자동.
승급은 대시보드에서 운영자가 수동으로, 강등(서킷브레이커)은 자동으로.
"""
from __future__ import annotations

import json
import time

import httpx

from . import db, llm, schemas
from .config import settings, tracks, persona

RISK_BLOCK = 60          # risk_score >= 이 값이면 차단
AUTO_APPROVE_RISK = 25   # Level 2+ 자동 승인에 필요한 리스크 상한
AGREEMENT_WINDOW = 200   # 승급 판단에 보는 최근 판정 수
AGREEMENT_MIN = 0.95


def risk_review(job: dict) -> dict:
    """편집과 독립된 리스크 심사 패스. 전사문 캐시 프리픽스 공유."""
    from .stages.m3_analyze import transcribe, _transcript_system
    track = tracks()[job["track_id"]]
    script = job["payload"]["script"]
    clip_summary = ", ".join(
        f"{c['start']:.0f}-{c['end']:.0f}s({c['role']})" for c in script["clips"])
    prompt = llm.load_prompt(
        "risk_review", source_title=job["source_title"],
        source_url=job["source_url"], license_type=job["license_type"],
        category=job["category"], clip_summary=clip_summary,
        title=job["payload"]["title"],
        script="\n".join(p["text"] for p in script["script"]),
        forbidden=", ".join(persona(track)["forbidden"]))
    return llm.complete_json(prompt, schemas.RISK,
                             system=_transcript_system(transcribe(job)),
                             max_tokens=3000)


def perf_score(job: dict) -> float:
    """예상 성과(0~1): 선택된 프리셋들의 카테고리 조건부 평균 보상."""
    from .optimize import _stats
    params = job.get("template_params") or {}
    scores = []
    for dim, preset in params.items():
        trials, reward = _stats(dim, preset, job["category"])
        if trials:
            scores.append(reward / trials)
    return sum(scores) / len(scores) if scores else 0.5


def record_decision(job_id: int, decided_by: str, decision: str, *,
                    risk: float, perf: float, features: dict, reason: str) -> None:
    with db.conn() as c:
        c.execute(
            "INSERT INTO policy_decisions (job_id, decided_by, decision,"
            " risk_score, perf_score, features, reason, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (job_id, decided_by, decision, risk, perf,
             json.dumps(features, ensure_ascii=False), reason, time.time()))


def evaluate(job: dict) -> dict:
    """RENDERED job 판정. 반환: {decision, auto_applied, ...}

    - block: 리스크 임계 초과 → REJECTED (레벨 무관)
    - approve: Level 2+이고 저위험·비민감이면 자동 APPROVED
    - hold: 사람 판단 대기 (Level 0~1, 또는 애매/민감 건)
    """
    risk = risk_review(job)
    perf = perf_score(job)
    level = db.autonomy_level(job["track_id"])
    features = {"risk": risk, "perf": perf, "level": level,
                "category": job["category"]}

    if not risk["pass"] or risk["risk_score"] >= RISK_BLOCK:
        db.transition(job["id"], "REJECTED",
                      error=json.dumps(risk["violations"], ensure_ascii=False))
        record_decision(job["id"], "engine", "reject", risk=risk["risk_score"],
                        perf=perf, features=features,
                        reason="risk threshold exceeded")
        return {"decision": "block", "auto_applied": True, **features}

    sensitive = job["category"] == "incident" or risk.get("escalate")
    can_auto = (level >= 2 and settings().auto_publish
                and risk["risk_score"] < AUTO_APPROVE_RISK and not sensitive)
    if can_auto:
        db.transition(job["id"], "APPROVED")
        record_decision(job["id"], "engine", "approve", risk=risk["risk_score"],
                        perf=perf, features=features, reason="auto (level>=2)")
        return {"decision": "approve", "auto_applied": True, **features}

    # Level 0~1 또는 민감 건: 예측만 기록하고 사람 대기 (섀도 학습 데이터)
    record_decision(job["id"], "engine",
                    "approve" if risk["risk_score"] < AUTO_APPROVE_RISK else "reject",
                    risk=risk["risk_score"], perf=perf, features=features,
                    reason="shadow prediction")
    db.update_payload(job["id"], {"policy": features})
    return {"decision": "hold", "auto_applied": False, **features}


def operator_decide(job_id: int, approve: bool, reason: str = "") -> None:
    job = db.get_job(job_id)
    pol = job["payload"].get("policy", {})
    record_decision(job_id, "operator", "approve" if approve else "reject",
                    risk=pol.get("risk", {}).get("risk_score", -1),
                    perf=pol.get("perf", -1), features=pol, reason=reason)
    db.transition(job_id, "APPROVED" if approve else "REJECTED", error=reason or None)


def engine_operator_agreement(track_id: str) -> tuple[float, int]:
    """최근 판정에서 엔진 섀도 예측과 운영자 결정의 일치율 (승급 근거)."""
    with db.conn() as c:
        rows = c.execute(
            """SELECT e.decision AS eng, o.decision AS op FROM policy_decisions e
               JOIN policy_decisions o ON e.job_id=o.job_id
               JOIN jobs j ON j.id=e.job_id
               WHERE e.decided_by='engine' AND o.decided_by='operator' AND j.track_id=?
               ORDER BY o.created_at DESC LIMIT ?""",
            (track_id, AGREEMENT_WINDOW)).fetchall()
    if not rows:
        return 0.0, 0
    agree = sum(1 for r in rows if r["eng"] == r["op"])
    return agree / len(rows), len(rows)


def circuit_breaker(track_id: str, *, reason: str, copyright_strike: bool = False) -> None:
    """사고 신호 → 자동 발행 즉시 중단 + 레벨 강등 + 알림 (SPEC 0-2)."""
    level = db.autonomy_level(track_id)
    new_level = 0 if copyright_strike else max(0, level - 1)
    db.set_autonomy_level(track_id, new_level)
    alert(f"[서킷브레이커] track={track_id} level {level}->{new_level}: {reason}")


def alert(message: str) -> None:
    url = settings().alert_webhook_url
    if url:
        try:
            httpx.post(url, json={"text": message}, timeout=10)
        except httpx.HTTPError:
            pass
    print(f"ALERT: {message}")


def run() -> None:
    for job in db.jobs_in_state("RENDERED"):
        try:
            evaluate(job)
        except Exception as e:  # noqa: BLE001
            db.record_failure(job["id"], f"policy: {e}")
