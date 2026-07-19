"""M6 — 업로드. APPROVED 상태를 함수 안에서 재확인한다 — 어떤 코드 경로도
발행 게이트를 우회할 수 없다 (PLAYBOOK §6-4).

- 멀티 채널: 트랙별 OAuth 파일 지정 가능 (tracks.yaml — 리스크 분산)
- 업로드 직후 질문형 댓글 자동 게시 (참여 신호 → 노출 확대)
"""
from __future__ import annotations

import json
import time

from .. import db
from ..config import OUT_DIR, settings, tracks

YT_CATEGORY_ENTERTAINMENT = "24"
# force-ssl: 댓글 게시 / yt-analytics: M8 완주율·구독 실측
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _credentials(track=None, *, interactive: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    s = settings()
    token_file = (track and track.youtube_token_file) or s.youtube_token_file
    secret_file = ((track and track.youtube_client_secret_file)
                   or s.youtube_client_secret_file)
    creds = None
    try:
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    except (FileNotFoundError, ValueError):
        pass
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not interactive:
            return None
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return creds


def _service(track=None):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_credentials(track))


def upload_youtube(job: dict) -> str:
    from googleapiclient.http import MediaFileUpload

    # 게이트 재확인 — APPROVED가 아니면 어떤 호출 경로에서도 업로드 불가
    fresh = db.get_job(job["id"])
    if fresh["state"] != "APPROVED":
        raise PermissionError(f"job {job['id']} not APPROVED ({fresh['state']})")
    if db.uploads_today("youtube") >= settings().daily_upload_limit_yt:
        raise RuntimeError("daily YouTube upload limit reached")

    track = tracks().get(job["track_id"])
    meta = json.loads((OUT_DIR / f"{job['id']}.json").read_text(encoding="utf-8"))
    body = {
        "snippet": {"title": meta["title"][:100],
                    "description": meta["description"],
                    "tags": meta["tags"][:15],
                    "categoryId": YT_CATEGORY_ENTERTAINMENT},
        "status": {"privacyStatus": "public",
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(OUT_DIR / meta["file"]),
                            mimetype="video/mp4", resumable=True)
    svc = _service(track)
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    video_id = resp["id"]
    with db.conn() as c:
        c.execute("INSERT INTO uploads (job_id, platform, remote_id, uploaded_at)"
                  " VALUES (?,?,?,?)", (job["id"], "youtube", video_id, time.time()))
    _post_engagement_comment(svc, video_id, job)
    return video_id


def _post_engagement_comment(svc, video_id: str, job: dict) -> None:
    """질문형 작성자 댓글 — 댓글 마이닝의 open_questions 재활용 (LLM 호출 없음).

    API로는 고정(pin)이 불가하므로 작성자 댓글로 게시된다. 실패해도 업로드는 성공.
    """
    questions = job["payload"].get("insights", {}).get("open_questions", [])
    text = (f"여러분 생각은 어떤가요? {questions[0]}" if questions
            else "다음엔 어떤 해외 이슈를 다뤄볼까요? 댓글로 알려주세요 👇")
    try:
        svc.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "topLevelComment": {
                "snippet": {"textOriginal": text[:500]}}}}).execute()
    except Exception as e:  # noqa: BLE001
        print(f"comment post failed (non-fatal): {e}")


def run() -> None:
    for job in db.jobs_in_state("APPROVED"):
        try:
            video_id = upload_youtube(job)
            db.transition(job["id"], "PUBLISHED_YT",
                          payload_update={"youtube_id": video_id})
            db.transition(job["id"], "DONE")
        except Exception as e:  # noqa: BLE001
            db.record_failure(job["id"], f"publish: {e}")
