"""공급사 소스 요청 아웃리치 — 영상 소스(footage)가 없는 상품에 대해
사용 허가 요청 메시지를 자동 생성/발송한다. LLM 미사용(토큰 0).

채널 2종 (products.yaml의 supplier_channel):
- email: 국내 공급사 — SMTP 설정 시 자동 발송 가능 (기본은 초안 모드)
- 1688:  중국 공급사 — 왕왕(阿里旺旺) 채팅에 붙여넣을 중국어 초안 생성
         (왕왕은 공개 API가 없어 발송은 수동 — 초안 복사가 최선)

허가 회신을 받으면: products.yaml에 license: licensed + license_note(회신
날짜·내용 요약) 기록 → 파이프라인 정식 투입.
"""
from __future__ import annotations

import smtplib
import time
from email.mime.text import MIMEText
from pathlib import Path

from . import db, policy
from .config import OUT_DIR, products, settings

FOLLOWUP_DAYS = 5

EMAIL_KO = """제목: [{name}] 판매 셀러입니다 — 공식 홍보 영상/이미지 사용 허가 요청

안녕하세요, {seller_store}의 {seller_name}입니다.

현재 귀사의 "{name}" 제품을 판매하고 있습니다. 판매 촉진을 위해 유튜브
쇼츠 상품 소개 영상을 제작하려고 하는데, 귀사에서 보유하신 공식 홍보
영상·이미지 소스를 제공해 주실 수 있는지, 그리고 해당 소스를 저희 판매
채널(유튜브/쿠팡 상세페이지)에서 사용해도 되는지 허가를 요청드립니다.

영상은 제품 판매 페이지로 연결되어 귀사 제품 판매 증진에 직접 기여합니다.
사용 범위: 유튜브 상품 소개 영상 및 쿠팡 판매 페이지 한정.

회신으로 소스 파일(또는 다운로드 링크)과 사용 동의 여부를 알려주시면
감사하겠습니다.

{seller_name} 드림
"""

MSG_1688 = """您好！我是韩国Coupang平台的卖家（{seller_store}）。

我们正在销售贵司的产品"{name}"，为了扩大销量，计划制作YouTube短视频
进行推广。

请问能否提供贵司的官方产品宣传视频/图片素材？我们希望获得授权，
在YouTube推广视频和Coupang商品页面中使用这些素材。

视频会直接链接到购买页面，有助于提升贵司产品的订单量。

如可以，请发送素材文件或网盘链接，并确认授权。谢谢！

—— 韩国卖家 {seller_name}

[한국어 참고 번역] {name} 판매 셀러입니다. 유튜브 홍보 영상 제작을 위해
공식 홍보 영상/이미지 소스 제공과 사용 허가를 요청드립니다.
"""


def _draft_dir() -> Path:
    d = OUT_DIR / "outreach"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _needs_outreach() -> list[dict]:
    """footage 파일이 없고 공급사 연락처가 있으며 아직 연락 전인 상품."""
    out = []
    for p in products():
        if Path(p.get("footage", "")).exists():
            continue
        if not (p.get("supplier_email") or p.get("supplier_channel") == "1688"):
            continue
        with db.conn() as c:
            row = c.execute("SELECT status FROM outreach WHERE product_id=?",
                            (p["id"],)).fetchone()
        if row is None:
            out.append(p)
    return out


def _render(p: dict) -> tuple[str, str]:
    """(채널, 본문). 1688은 중국어 왕왕 메시지, 그 외는 한국어 이메일."""
    s = settings()
    ctx = {"name": p["name"], "seller_name": s.seller_name or "판매자",
           "seller_store": s.seller_store or "쿠팡 스토어"}
    if p.get("supplier_channel") == "1688":
        return "1688", MSG_1688.format(**ctx)
    return "email", EMAIL_KO.format(**ctx)


def _send_email(to_addr: str, body: str) -> None:
    s = settings()
    subject, _, content = body.partition("\n\n")
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = subject.replace("제목: ", "")
    msg["From"] = s.smtp_user
    msg["To"] = to_addr
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def run_daily() -> None:
    s = settings()
    for p in _needs_outreach():
        channel, body = _render(p)
        path = _draft_dir() / f"{p['id']}.{channel}.txt"
        path.write_text(body, encoding="utf-8")
        status, note = "drafted", f"초안: {path.name}"
        if (channel == "email" and s.outreach_auto_send
                and s.smtp_host and p.get("supplier_email")):
            try:
                _send_email(p["supplier_email"], body)
                status, note = "sent", f"자동 발송 → {p['supplier_email']}"
            except Exception as e:  # noqa: BLE001
                note = f"발송 실패(초안 유지): {e}"
        with db.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO outreach (product_id, supplier_email,"
                " status, sent_at, note) VALUES (?,?,?,?,?)",
                (p["id"], p.get("supplier_email", ""), status,
                 time.time() if status == "sent" else None, note))
        policy.alert(
            f"[아웃리치] {p['name']} ({channel}): {note}"
            + ("" if status == "sent" else " — out/outreach/ 에서 복사해 보내세요"))
    _followups()


def _followups() -> None:
    cutoff = time.time() - FOLLOWUP_DAYS * 86400
    with db.conn() as c:
        rows = c.execute(
            "SELECT product_id FROM outreach WHERE status='sent'"
            " AND sent_at < ? AND (followup_at IS NULL)", (cutoff,)).fetchall()
        for r in rows:
            c.execute("UPDATE outreach SET followup_at=? WHERE product_id=?",
                      (time.time(), r["product_id"]))
    for r in rows:
        policy.alert(f"[아웃리치] {r['product_id']}: {FOLLOWUP_DAYS}일 무응답 — "
                     "팔로업 하거나 다른 공급사를 찾아보세요")


def mark_replied(product_id: str, note: str = "") -> None:
    """회신 수신 처리 (CLI: python -m app outreach-replied <id>)."""
    with db.conn() as c:
        c.execute("UPDATE outreach SET status='replied', note=? WHERE product_id=?",
                  (note or "회신 수신", product_id))
