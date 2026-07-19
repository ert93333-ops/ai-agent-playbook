"""product 트랙 소싱 — products.yaml 카탈로그에서 job 생성 (트렌드 스캔 대신).

같은 상품은 한 번만 자동 생성한다. 다른 앵글로 또 만들고 싶으면
카탈로그에 id를 바꿔(예: earbuds-01-v2) 추가하면 된다.
"""
from __future__ import annotations

from pathlib import Path

from .. import db
from ..config import products, tracks


def _already_queued(product_id: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM jobs WHERE source_url=?",
                         (f"product://{product_id}",)).fetchone() is not None


def enqueue() -> list[int]:
    track = tracks().get("product")
    if track is None or not track.enabled:
        return []
    created = []
    for p in products():
        if _already_queued(p["id"]):
            continue
        footage = Path(p["footage"])
        if not footage.exists():
            print(f"product {p['id']}: footage not found ({footage}) — skip")
            continue
        # own(본인 촬영) 또는 licensed(공급사 제공 — license_note에 근거 기록)
        lic = p.get("license", "own")
        if lic not in ("own", "licensed"):
            print(f"product {p['id']}: license={lic!r} not allowed — skip")
            continue
        if lic == "licensed" and not p.get("license_note"):
            print(f"product {p['id']}: licensed는 license_note(제공 근거) 필수 — skip")
            continue
        job_id = db.create_job(
            "product", category="product", license_type=lic,
            source_url=f"product://{p['id']}", source_title=p["name"],
            priority=90,
            payload={"local_path": str(footage.resolve()), "video_id": "",
                     "angle_hint": "", "product": p})
        created.append(job_id)
    return created
