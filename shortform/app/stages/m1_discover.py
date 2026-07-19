"""M1 — 주제·소스 발굴.

토큰 절약 설계: YouTube API로 받은 후보를 휴리스틱(급상승 속도, 길이,
블랙리스트)으로 먼저 걸러 상위 N개만 LLM(light 모델) 심사에 올린다.
"""
from __future__ import annotations

import time

import httpx

from .. import db, llm, schemas
from ..config import Track, enabled_tracks, settings

YT = "https://www.googleapis.com/youtube/v3"
LLM_CANDIDATES_PER_TRACK = 10   # LLM 심사에 올릴 최대 후보 수
MIN_SCORE = 60


def _yt_get(path: str, **params) -> dict:
    params["key"] = settings().youtube_api_key
    r = httpx.get(f"{YT}/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _blacklisted(channel_url: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM blacklist WHERE channel_url=?",
                         (channel_url,)).fetchone() is not None


def _trending_candidates(track: Track) -> list[dict]:
    """지역별 인기 급상승 → 휴리스틱 점수로 정렬한 후보 목록."""
    out = []
    for region in track.trend_regions:
        data = _yt_get("videos", part="snippet,statistics,contentDetails",
                       chart="mostPopular", regionCode=region, maxResults=25)
        for item in data.get("items", []):
            sn, st = item["snippet"], item.get("statistics", {})
            published = time.mktime(time.strptime(
                sn["publishedAt"], "%Y-%m-%dT%H:%M:%SZ"))
            hours = max(1.0, (time.time() - published) / 3600)
            if hours > 48:          # 48시간 지난 소재 제외 (PLAYBOOK §1-2)
                continue
            views = int(st.get("viewCount", 0))
            channel_url = f"https://www.youtube.com/channel/{sn['channelId']}"
            if _blacklisted(channel_url):
                continue
            out.append({
                "video_id": item["id"], "title": sn["title"],
                "channel": sn["channelTitle"], "channel_url": channel_url,
                "description": sn.get("description", "")[:500],
                "published_at": sn["publishedAt"],
                "views": views, "hours_since": round(hours, 1),
                "velocity": views / hours,
                "category_hint": sn.get("categoryId", ""),
            })
    out.sort(key=lambda c: c["velocity"], reverse=True)
    return out


def _already_seen(video_id: str) -> bool:
    with db.conn() as c:
        return c.execute(
            "SELECT 1 FROM jobs WHERE source_url LIKE ?",
            (f"%{video_id}%",)).fetchone() is not None


def _score_with_llm(track: Track, cand: dict) -> dict:
    prompt = llm.load_prompt("audience_fit", **{
        k: cand[k] for k in ("title", "channel", "published_at", "views",
                             "hours_since", "category_hint", "description")})
    return llm.complete_json(prompt, schemas.AUDIENCE_FIT, tier="light",
                             max_tokens=2000)


def collect_benchmarks(track: Track) -> None:
    """니치 상위 쇼츠 수집 → 제목 패턴 저장 (첫 3초 비전 분석은 Phase 4)."""
    data = _yt_get("search", part="snippet", type="video", videoDuration="short",
                   order="viewCount", regionCode="KR", maxResults=15,
                   q=" | ".join(track.categories))
    now = time.time()
    with db.conn() as c:
        for item in data.get("items", []):
            vid = item["id"].get("videoId")
            if not vid:
                continue
            c.execute(
                "INSERT OR IGNORE INTO benchmarks (track_id, video_id, title,"
                " views, hook_patterns, collected_at) VALUES (?,?,?,?,?,?)",
                (track.id, vid, item["snippet"]["title"], 0, "{}", now))


def hook_patterns(track_id: str, limit: int = 10) -> list[str]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT title FROM benchmarks WHERE track_id=?"
            " ORDER BY collected_at DESC LIMIT ?", (track_id, limit)).fetchall()
    return [r["title"] for r in rows]


def run() -> list[int]:
    created = []
    for track in enabled_tracks():
        collect_benchmarks(track)
        candidates = [c for c in _trending_candidates(track)
                      if not _already_seen(c["video_id"])]
        for cand in candidates[:LLM_CANDIDATES_PER_TRACK]:
            verdict = _score_with_llm(track, cand)
            if not verdict["gate_pass"] or verdict["score"] < MIN_SCORE:
                continue
            job_id = db.create_job(
                track.id, category=verdict["category"],
                license_type="commentary",
                source_url=f"https://www.youtube.com/watch?v={cand['video_id']}",
                source_title=cand["title"], priority=verdict["score"],
                payload={"angle_hint": verdict["angle_hint"],
                         "video_id": cand["video_id"],
                         "channel_url": cand["channel_url"],
                         "source_channel": cand["channel"]})
            created.append(job_id)
    return created
