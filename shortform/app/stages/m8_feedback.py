"""M8 — 성과 수집·피드백 루프 (자동 개선의 입력).

발행 후 3h / 24h / 72h 3회 측정:
- 3h/24h: 초기 신호 적재 (추세 감시·서킷브레이커)
- 72h(최종): 밴딧 보상 확정 → optimize.record_result()

보상 = 시기별 목표 가중 합성 (settings.optimize_goal):
- subs(YPP 진입 전):  0.4*완주율 + 0.6*구독전환(정규화)
- retention(이후):    0.8*완주율 + 0.2*구독전환
완주율·구독전환은 Analytics API 실측이 1순위, 없으면 좋아요율 근사치 폴백.
"""
from __future__ import annotations

import time

import httpx

from .. import analytics, db, llm, optimize, policy, schemas
from ..config import settings, tracks

WINDOWS = [("3h", 3 * 3600), ("24h", 24 * 3600), ("72h", 72 * 3600)]
FINAL_WINDOW = "72h"
DROP_SIGMA = 2.0
SUBS_PER_1K_VIEWS_NORM = 2.0   # 1천 회당 구독 2명 = 1.0 (쇼츠 상위권 수준)


def _stats(video_id: str) -> dict | None:
    r = httpx.get("https://www.googleapis.com/youtube/v3/videos",
                  params={"part": "statistics", "id": video_id,
                          "key": settings().youtube_api_key}, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    return items[0]["statistics"] if items else None


def _proxy_retention(stats: dict) -> float:
    """Analytics 미연동 폴백: 좋아요율 근사 (평균 4% → 0.5 정규화)."""
    views = int(stats.get("viewCount", 0))
    if views < 100:
        return 0.5
    return min(1.0, (int(stats.get("likeCount", 0)) / views) * 12.5)


def _reward(retention: float, subs_gained: int, views: int) -> float:
    subs_norm = 0.5 if views < 100 else min(
        1.0, (subs_gained / max(views, 1) * 1000) / SUBS_PER_1K_VIEWS_NORM)
    if settings().optimize_goal == "subs":
        return 0.4 * retention + 0.6 * subs_norm
    return 0.8 * retention + 0.2 * subs_norm


def _measured(job_id: int, window: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM performance WHERE job_id=? AND window=?",
                         (job_id, window)).fetchone() is not None


def collect() -> int:
    if not settings().youtube_api_key:
        return 0
    n = 0
    with db.conn() as c:
        rows = c.execute(
            "SELECT j.id, u.uploaded_at FROM jobs j JOIN uploads u"
            " ON u.job_id=j.id WHERE j.state='DONE' AND u.platform='youtube'"
        ).fetchall()
    for row in rows:
        age = time.time() - row["uploaded_at"]
        for window, sec in WINDOWS:
            if age < sec or _measured(row["id"], window):
                continue
            n += _measure_one(db.get_job(row["id"]), window, row["uploaded_at"])
    return n


def _measure_one(job: dict, window: str, uploaded_at: float) -> int:
    video_id = job["payload"].get("youtube_id")
    if not video_id:
        return 0
    stats = _stats(video_id)
    if stats is None:   # 영상 삭제/차단 — 저작권 사고로 간주
        policy.circuit_breaker(job["track_id"],
                               reason=f"video {video_id} unavailable",
                               copyright_strike=True)
        db.blacklist_channel(job["payload"].get("channel_url", ""),
                             "video removed after publish")
        return 0
    track = tracks().get(job["track_id"])
    views = int(stats.get("viewCount", 0))
    metrics = analytics.video_metrics(video_id, uploaded_at, track)
    retention = metrics["avg_view_pct"] if metrics else _proxy_retention(stats)
    subs = metrics["subs_gained"] if metrics else 0
    reward = _reward(retention, subs, views)
    with db.conn() as c:
        c.execute(
            "INSERT INTO performance (job_id, platform, window, measured_at,"
            " views, avg_view_pct, likes, comments, subs_gained)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (job["id"], "youtube", window, time.time(), views, reward,
             int(stats.get("likeCount", 0)), int(stats.get("commentCount", 0)),
             subs))
    if window == FINAL_WINDOW:
        if job["template_params"]:
            optimize.record_result(job["template_params"], job["category"], reward)
        _check_drop(job["track_id"], reward)
    return 1


def _check_drop(track_id: str, reward: float) -> None:
    with db.conn() as c:
        rows = c.execute(
            "SELECT p.avg_view_pct AS r FROM performance p JOIN jobs j"
            " ON j.id=p.job_id WHERE j.track_id=? AND p.window=?"
            " ORDER BY p.measured_at DESC LIMIT 20",
            (track_id, FINAL_WINDOW)).fetchall()
    vals = [r["r"] for r in rows]
    if len(vals) < 10:
        return
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    if reward < mean - DROP_SIGMA * (var ** 0.5):
        policy.circuit_breaker(track_id,
                               reason=f"reward drop {reward:.2f} vs mean {mean:.2f}")


def weekly_tone_review() -> str | None:
    """주 1회: 상·하위 성과 대본 비교 → 프롬프트 개선안 리포트 (수동 반영)."""
    with db.conn() as c:
        rows = c.execute(
            """SELECT j.id, j.payload, p.avg_view_pct AS r FROM performance p
               JOIN jobs j ON j.id=p.job_id WHERE p.window=?
               ORDER BY p.measured_at DESC LIMIT 30""", (FINAL_WINDOW,)).fetchall()
        rejections = c.execute(
            "SELECT reason FROM policy_decisions WHERE decided_by='operator'"
            " AND decision='reject' ORDER BY created_at DESC LIMIT 20").fetchall()
    if len(rows) < 10:
        return None
    import json as _json
    items = sorted(({"r": r["r"], **_json.loads(r["payload"])} for r in rows),
                   key=lambda x: x["r"])

    def fmt(subset):
        return "\n".join(
            f"- [{i['r']:.2f}] {i.get('title')}: "
            + " / ".join(p["text"] for p in i.get("script", {}).get("script", [])[:3])
            for i in subset)

    prompt = llm.load_prompt(
        "tone_review", top_items=fmt(items[-5:]), bottom_items=fmt(items[:5]),
        rejection_reasons="\n".join(f"- {r['reason']}" for r in rejections) or "없음")
    result = llm.complete_json(prompt, schemas.TONE_REVIEW, max_tokens=4000)

    from ..config import OUT_DIR
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"tone_review_{time.strftime('%Y%m%d')}.md"
    lines = ["# 주간 톤앤매너 회고 (자동 생성 — 운영자 검토 후 수동 반영)\n"]
    for section, key in (("페르소나", "persona_diffs"), ("제목 프롬프트", "title_prompt_diffs")):
        lines.append(f"\n## {section}")
        for d in result[key]:
            lines.append(f"- **{d['target']}** → {d['change']}\n  근거: {d['evidence']}")
    path.write_text("\n".join(lines), encoding="utf-8")
    policy.alert(f"주간 톤앤매너 회고 생성: {path.name} (검토 후 반영하세요)")
    return str(path)


def run() -> None:
    n = collect()
    if n:
        print(f"m8: {n}건 성과 측정")
