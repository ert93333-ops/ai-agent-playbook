"""상품 페이지에서 공급사 홍보 영상 자동 추출 (1688 등).

소싱 우선순위 (products.enqueue):
1. footage 파일이 이미 있으면 그대로 사용
2. supplier_url 페이지에서 공급사 영상 자동 추출 ← 이 모듈
3. 실패 시 아웃리치(왕왕/메일)로 소스 요청

근거: 공급사가 해당 상품 판매 촉진용으로 게시한 홍보 소재를, 그 상품을
사입해 판매하는 셀러가 판매 목적으로 쓰는 것 — 업계 표준 관행이며 출처를
license_note에 자동 기록한다. (타 크리에이터 영상과는 성격이 다름)
1688은 지역 차단·로그인 요구가 있어 실패할 수 있다 — 실패는 정상 경로.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import httpx

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1")

# 페이지 소스에 등장하는 mp4 URL 패턴 (JSON 이스케이프 변형 포함)
_PATTERNS = [
    re.compile(r'https?:\\?/\\?/[^"\'\s]+?\.mp4[^"\'\s]*'),
    re.compile(r'"videoUrl"\s*:\s*"([^"]+)"'),
    re.compile(r'"videoId"[^}]*?"url"\s*:\s*"([^"]+)"'),
]


def _unescape(url: str) -> str:
    return html.unescape(url).replace("\\/", "/").replace("\\u002F", "/")


def find_video_url(page_url: str) -> str | None:
    try:
        r = httpx.get(page_url, headers={"User-Agent": UA},
                      follow_redirects=True, timeout=30)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    text = r.text
    candidates: list[str] = []
    for pat in _PATTERNS:
        for m in pat.findall(text):
            url = _unescape(m if isinstance(m, str) else m[0])
            if url.startswith("//"):
                url = "https:" + url
            if ".mp4" in url and url.startswith("http"):
                candidates.append(url)
    return candidates[0] if candidates else None


def download(video_url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    try:
        with httpx.stream("GET", video_url, headers={"User-Agent": UA},
                          follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(65536):
                    f.write(chunk)
    except httpx.HTTPError:
        tmp.unlink(missing_ok=True)
        return False
    if tmp.stat().st_size < 100_000:   # 100KB 미만이면 영상이 아님 (오탐)
        tmp.unlink()
        return False
    tmp.rename(dest)
    return True


def try_fetch(product: dict, dest: Path) -> str | None:
    """성공 시 자동 생성된 license_note 반환, 실패 시 None."""
    page = product.get("supplier_url") or product.get("coupang_url")
    if not page:
        return None
    video_url = find_video_url(page)
    if not video_url or not download(video_url, dest):
        return None
    import time
    return (f"{time.strftime('%Y-%m-%d')} 공급사 상품페이지({page})의 공식 홍보 "
            "영상 자동 추출 — 판매 상품 홍보 목적 사용. 왕왕으로 사용 확인 한 줄 권장")
