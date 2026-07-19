"""M3 — 전사 → 댓글 마이닝 → 하이라이트+해설 대본 → 제목.

토큰 절약: 전사문(가장 큰 입력)은 system 프리픽스에 cache_control로 배치해
대본 생성·제목 생성·리스크 심사(M10)가 같은 캐시를 읽는다. 댓글 마이닝은
light 모델.
"""
from __future__ import annotations

import json

import httpx

from .. import db, llm, optimize, schemas
from ..config import Track, job_dir, persona, settings, tracks
from .m1_discover import hook_patterns

TARGET_SEC = 50   # 나레이션 목표 길이 (아웃트로 여유 포함 60초 규격 대비)


def transcribe(job: dict) -> list[dict]:
    """faster-whisper 단어 타임스탬프 전사. 결과는 파일 캐시(멱등)."""
    d = job_dir(job["id"])
    cache = d / "transcript.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel
    model = WhisperModel("medium", compute_type="int8")
    segments, _ = model.transcribe(str(d / "source.wav"), word_timestamps=True)
    out = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
           for s in segments]
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def fetch_comments(video_id: str, limit: int = 100) -> list[str]:
    try:
        r = httpx.get(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={"part": "snippet", "videoId": video_id, "order": "relevance",
                    "maxResults": min(limit, 100),
                    "key": settings().youtube_api_key},
            timeout=30)
        r.raise_for_status()
        return [i["snippet"]["topLevelComment"]["snippet"]["textDisplay"][:300]
                for i in r.json().get("items", [])]
    except httpx.HTTPError:
        return []   # 댓글 비활성 영상 등 — 인사이트 없이 진행


def mine_comments(job: dict) -> dict:
    comments = fetch_comments(job["payload"].get("video_id", ""))
    if not comments:
        return {"peak_moments": [], "memes": [], "open_questions": [],
                "local_context": [], "sensitive": []}
    prompt = llm.load_prompt("comment_mining", title=job["source_title"],
                             comments="\n".join(f"- {c}" for c in comments))
    return llm.complete_json(prompt, schemas.COMMENT_INSIGHTS, tier="light",
                             max_tokens=4000)


def _transcript_system(transcript: list[dict]) -> str:
    lines = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}"
                      for s in transcript)
    return ("아래는 원본 영상의 전사문(초 단위 타임스탬프)이다. 클립 선정과 "
            "대본의 사실 관계는 반드시 이 전사문에 근거해야 한다.\n\n" + lines)


def write_script(job: dict, track: Track, transcript: list[dict],
                 insights: dict, params: dict) -> dict:
    p = persona(track)
    tone = params.get("stance", "")
    humor = params.get("humor_density", "normal")
    persona_text = (f"{p['voice']}\n유머: {p['humor']}\n"
                    f"이번 영상 톤 지시: {tone} / 드립 밀도: {humor}\n"
                    f"금지: {', '.join(p['forbidden'])}\n마무리: {p['signoff']}")
    prompt = llm.load_prompt(
        "commentary_script", persona=persona_text, category=job["category"],
        angle_hint=job["payload"].get("angle_hint", ""),
        comment_insights=json.dumps(insights, ensure_ascii=False),
        hook_patterns=json.dumps(hook_patterns(track.id), ensure_ascii=False),
        max_clip_sec=8, target_sec=TARGET_SEC)
    return llm.complete_json(prompt, schemas.SCRIPT,
                             system=_transcript_system(transcript))


def make_title(job: dict, track: Track, script: dict,
               transcript: list[dict], params: dict) -> dict:
    summary = " / ".join(s["text"] for s in script["script"][:4])
    formula = params.get("preset_names", {}).get("title_formula", "question")
    prompt = llm.load_prompt(
        "title_gen", script_summary=summary, title_formula=formula,
        hook_patterns=json.dumps(hook_patterns(track.id), ensure_ascii=False))
    return llm.complete_json(prompt, schemas.TITLES,
                             system=_transcript_system(transcript),
                             max_tokens=2000)


def analyze(job: dict) -> None:
    track = tracks()[job["track_id"]]
    params = optimize.resolve(job["template_params"]
                              or optimize.choose_params(job["category"]))
    transcript = transcribe(job)
    insights = mine_comments(job)
    script = write_script(job, track, transcript, insights, params)
    titles = make_title(job, track, script, transcript, params)
    with db.conn() as c:
        c.execute("UPDATE jobs SET template_params=? WHERE id=?",
                  (json.dumps(params.get("preset_names", {})), job["id"]))
    db.transition(job["id"], "ANALYZED", payload_update={
        "insights": insights, "script": script,
        "title": titles["chosen"]["title"],
        "title_candidates": titles["candidates"],
        "resolved_params": params,
    })


def run() -> None:
    for job in db.jobs_in_state("ACQUIRED"):
        try:
            analyze(job)
        except Exception as e:  # noqa: BLE001
            db.record_failure(job["id"], f"analyze: {e}")
