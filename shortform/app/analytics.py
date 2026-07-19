"""YouTube Analytics API 연동 — 완주율·구독 전환 실측 (M8 보상의 1차 소스).

업로드용 OAuth 토큰을 그대로 쓴다 (m6의 SCOPES에 analytics readonly 포함).
토큰이 없거나 실패하면 None을 반환하고 M8이 좋아요율 근사치로 폴백한다.
"""
from __future__ import annotations

import time


def video_metrics(video_id: str, published_at: float,
                  track=None) -> dict | None:
    """{avg_view_pct: 0~1, subs_gained: int} 또는 None(연동 불가)."""
    try:
        from googleapiclient.discovery import build
        from .stages.m6_publish import _credentials
        creds = _credentials(track, interactive=False)
        if creds is None:
            return None
        yta = build("youtubeAnalytics", "v2", credentials=creds)
        start = time.strftime("%Y-%m-%d", time.gmtime(published_at - 86400))
        end = time.strftime("%Y-%m-%d", time.gmtime())
        resp = yta.reports().query(
            ids="channel==MINE", startDate=start, endDate=end,
            metrics="averageViewPercentage,subscribersGained",
            filters=f"video=={video_id}").execute()
        rows = resp.get("rows") or []
        if not rows:
            return None
        avg_pct, subs = rows[0][0], rows[0][1]
        return {"avg_view_pct": float(avg_pct) / 100.0, "subs_gained": int(subs)}
    except Exception:  # noqa: BLE001 — 어떤 실패든 근사치 폴백
        return None
