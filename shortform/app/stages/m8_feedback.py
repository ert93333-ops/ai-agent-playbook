"""M8 — 성과 수집·피드백 루프 (자동 개선의 입력).

발행 48시간 후 실측 지표를 수집해:
1. performance 테이블에 적재 (M10 지연 라벨 회고의 원료)
2. optimize.record_result()로 밴딧에 보상 전달 (톤앤매너 학습)
3. 성과 급락 감지 시 서킷브레이커 (SPEC 0-2)

보상 지표: YouTube Analytics API(OAuth)가 있으면 평균시청지속률(완주율),
없으면 Data API 통계 기반 근사치(좋아요율)로 폴백.
"""
from __future__ import annotations

import time

import httpx

from .. import db, llm, optimize, policy, schemas
from ..config import settings

MEASURE_AFTER_SEC = 48 * 3600
DROP_SIGMA = 2.0   # 트랙 이동평균 대비 -2σ면 서킷브레이커


def _stats(video_id: str) -> dict | None:
    r = httpx.get("https://www.googleapis.com/youtube/v3/videos",
                  params={"part": "statistics", "id": video_id,
                          "key": settings().youtube_api_key}, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    return items[0]["statistics"] if items else None


def _reward(stats: dict) -> float:
    """완주율 대용 근사치: 좋아요율 기반 (Analytics OAuth 연동 전 폴백).

    쇼츠 평균 좋아요율 ~4%를 0.5로 정규화 → reward = min(1, like_rate * 12.5)
    Analytics API 연동 시 averageViewPercentage/100으로 교체할 것.
    """
    views = int(stats.get("viewCount", 0))
    likes = int(stats.get("likeCount", 0))
    if views < 100:      # 표본 미달 — 중립 보상
        return 0.5
    return min(1.0, (likes / views) * 12.5)


def _measured(job_id: int) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM performance WHERE job_id=?",
                         (job_id,)).fetchone() is not None


def collect() -> int:
    """DONE job 중 발행 48h 경과 + 미측정 건을 수집."""
    if not settings().youtube_api_key:
        return 0
    n = 0
    with db.conn() as c:
        rows = c.execute(
            "SELECT j.id FROM jobs j JOIN uploads u ON u.job_id=j.id"
            " WHERE j.state='DONE' AND u.platform='youtube'"
            " AND u.uploaded_at < ?", (time.time() - MEASURE_AFTER_SEC,)).fetchall()
    for row in rows:
        job = db.get_job(row["id"])
        if _measured(job["id"]):
            continue
        video_id = job["payload"].get("youtube_id")
        if not video_id:
            continue
        stats = _stats(video_id)
        if stats is None:      # 영상 삭제/차단됨 — 클레임 신호로 간주
            policy.circuit_breaker(job["track_id"],
                                   reason=f"video {video_id} unavailable",
                                   copyright_strike=True)
            db.blacklist_channel(job["payload"].get("channel_url", ""),
                                 "video removed after publish")
            continue
        reward = _reward(stats)
        with db.conn() as c:
            c.execute(
                "INSERT INTO performance (job_id, platform, measured_at, views,"
                " avg_view_pct, likes, comments) VALUES (?,?,?,?,?,?,?)",
                (job["id"], "youtube", time.time(),
                 int(stats.get("viewCount", 0)), reward,
                 int(stats.get("likeCount", 0)),
                 int(stats.get("commentCount", 0))))
        if job["template_params"]:
            optimize.record_result(job["template_params"], job["category"], reward)
        _check_drop(job["track_id"], reward)
        n += 1
    return n


def _check_drop(track_id: str, reward: float) -> None:
    with db.conn() as c:
        rows = c.execute(
            "SELECT p.avg_view_pct AS r FROM performance p JOIN jobs j"
            " ON j.id=p.job_id WHERE j.track_id=? ORDER BY p.measured_at DESC"
            " LIMIT 20", (track_id,)).fetchall()
    vals = [r["r"] for r in rows]
    if len(vals) < 10:
        return
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    if reward < mean - DROP_SIGMA * (var ** 0.5):
        policy.circuit_breaker(track_id,
                               reason=f"reward drop {reward:.2f} vs mean {mean:.2f}")


def weekly_tone_review() -> str | None:
    """주 1회: 상·하위 성과 대본 비교 → 페르소나/제목 프롬프트 개선안 생성.

    자동 적용하지 않는다 (PLAYBOOK §7) — out/에 리포트로 남기고 알림만.
    """
    with db.conn() as c:
        rows = c.execute(
            """SELECT j.id, j.payload, p.avg_view_pct AS r FROM performance p
               JOIN jobs j ON j.id=p.job_id
               ORDER BY p.measured_at DESC LIMIT 30""").fetchall()
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
        print(f"m8: {n}건 성과 수집")
