"""상품 수요 리서치 — 조회수·댓글이 검증한 수요를 찾아 리포트로 만든다.

중요: 여기서 찾은 영상은 '무엇을 팔지'의 신호로만 쓴다. 타인의 상품 영상을
다운로드·재편집하는 것은 상업적 이용이라 저작권 방어가 불가능하다 (SPEC 0-1).
소싱 결정 → 쿠팡 등록 → 본인 촬영 or 공급사 제공(licensed) 영상으로 제작.
"""
from __future__ import annotations

import time

import httpx

from .. import llm, schemas
from ..config import OUT_DIR, settings
from .. import policy

QUERIES = ["신박한 제품", "살까말까", "쿠팡 추천템", "가성비 템", "언박싱"]


def _trending_product_shorts() -> list[dict]:
    out = []
    for q in QUERIES:
        try:
            r = httpx.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"part": "snippet", "type": "video",
                        "videoDuration": "short", "order": "viewCount",
                        "publishedAfter": time.strftime(
                            "%Y-%m-%dT00:00:00Z",
                            time.gmtime(time.time() - 14 * 86400)),
                        "regionCode": "KR", "maxResults": 10, "q": q,
                        "key": settings().youtube_api_key},
                timeout=30)
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        ids = [i["id"]["videoId"] for i in r.json().get("items", [])
               if i["id"].get("videoId")]
        if not ids:
            continue
        stats = httpx.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": ",".join(ids),
                    "key": settings().youtube_api_key}, timeout=30).json()
        for v in stats.get("items", []):
            st = v.get("statistics", {})
            out.append({
                "title": v["snippet"]["title"],
                "views": int(st.get("viewCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            })
    out.sort(key=lambda x: x["views"], reverse=True)
    return out[:30]


def weekly_report() -> str | None:
    if not settings().youtube_api_key:
        return None
    items = _trending_product_shorts()
    if len(items) < 5:
        return None
    listing = "\n".join(
        f"- [{i['views']:,}회 / 댓글 {i['comments']:,}] {i['title']}"
        for i in items)
    result = llm.complete_json(
        llm.load_prompt("product_research", items=listing),
        schemas.PRODUCT_RESEARCH, tier="light", max_tokens=3000)

    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"product_opportunities_{time.strftime('%Y%m%d')}.md"
    lines = ["# 주간 상품 기회 리포트 (수요 검증 기반)\n",
             "다음 단계: 상품 선정 → 쿠팡 소싱·등록 → 본인 촬영 또는 공급사",
             "제공 영상 확보 → products.yaml 등록 (타인 영상 재편집 금지)\n"]
    for o in result["opportunities"]:
        lines += [f"\n## {o['product']}",
                  f"- 수요 근거: {o['demand_signal']}",
                  f"- 먹히는 소구점: {o['angle']}",
                  f"- 소싱 힌트: {o['sourcing_hint']}",
                  f"- 주의: {o['caution']}"]
    path.write_text("\n".join(lines), encoding="utf-8")
    policy.alert(f"상품 기회 리포트 생성: {path.name}")
    return str(path)
