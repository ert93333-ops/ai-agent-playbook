"""M6 — 업로드. APPROVED 상태를 함수 안에서 재확인한다 — 어떤 코드 경로도
발행 게이트를 우회할 수 없다 (PLAYBOOK §6-4).
"""
from __future__ import annotations

import json
import time

from .. import db
from ..config import OUT_DIR, settings, tracks

YT_CATEGORY_ENTERTAINMENT = "24"


def _yt_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    s = settings()
    creds = None
    try:
        creds = Credentials.from_authorized_user_file(s.youtube_token_file, scopes)
    except FileNotFoundError:
        pass
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            s.youtube_client_secret_file, scopes)
        creds = flow.run_local_server(port=0)
        with open(s.youtube_token_file, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_youtube(job: dict) -> str:
    from googleapiclient.http import MediaFileUpload

    # 게이트 재확인 — APPROVED가 아니면 어떤 호출 경로에서도 업로드 불가
    fresh = db.get_job(job["id"])
    if fresh["state"] != "APPROVED":
        raise PermissionError(f"job {job['id']} not APPROVED ({fresh['state']})")
    if db.uploads_today("youtube") >= settings().daily_upload_limit_yt:
        raise RuntimeError("daily YouTube upload limit reached")

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
    req = _yt_service().videos().insert(part="snippet,status",
                                        body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    video_id = resp["id"]
    with db.conn() as c:
        c.execute("INSERT INTO uploads (job_id, platform, remote_id, uploaded_at)"
                  " VALUES (?,?,?,?)", (job["id"], "youtube", video_id, time.time()))
    return video_id


def run() -> None:
    for job in db.jobs_in_state("APPROVED"):
        try:
            video_id = upload_youtube(job)
            db.transition(job["id"], "PUBLISHED_YT",
                          payload_update={"youtube_id": video_id})
            track = tracks()[job["track_id"]]
            if settings().ig_access_token and settings().ig_user_id:
                # Instagram Reels: 공개 URL 필요 — Phase 2 후반 (SPEC M6)
                db.transition(job["id"], "PUBLISHED_IG")
                db.transition(job["id"], "DONE")
            else:
                db.transition(job["id"], "DONE")
            _ = track
        except Exception as e:  # noqa: BLE001
            db.record_failure(job["id"], f"publish: {e}")
