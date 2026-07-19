"""타임라인 컴파일 + 0-1-1 변형 규칙 검증 (SPEC M4).

나레이션이 뼈대: 문단별 TTS 실측 길이가 세그먼트 길이를 결정하고,
클립은 그 위에 얹히는 증거 화면이다. 클립이 나레이션보다 짧으면 마지막
프레임을 정지(tpad clone)로 채운다 — 정지 구간은 푸티지 비율에 안 잡히므로
변형 규칙에도 유리하다.
"""
from __future__ import annotations

from typing import Any

from ..config import COMMENTARY_RULES, MAX_DURATION_SEC

PAD_SEC = 0.25  # 문단 사이 호흡


class TransformRuleViolation(Exception):
    pass


def compile_timeline(*, job_id: int, clips: list[dict], script: list[dict],
                     narration: list[dict], params: dict[str, Any],
                     license_type: str) -> dict[str, Any]:
    """clips: [{start,end,role}] / script: [{text,clip_ref,emphasis_words}]
    narration: tts.synthesize() 결과 (script와 같은 순서).
    """
    if len(script) != len(narration):
        raise ValueError("script/narration length mismatch")

    max_clip = COMMENTARY_RULES["max_clip_sec"]
    segments, subtitles, narr_track = [], [], []
    t = 0.0
    for para, tts in zip(script, narration):
        dur = tts["dur"] + PAD_SEC
        ref = para.get("clip_ref")
        if ref is not None and 0 <= ref < len(clips):
            clip = clips[ref]
            clip_len = min(clip["end"] - clip["start"], max_clip, dur)
            segments.append({
                "kind": "clip", "src_start": clip["start"],
                "src_end": clip["start"] + clip_len, "dur": dur,
                "footage_sec": clip_len,
                "zoom": bool(para.get("emphasis_words")) and params.get("zoom_on_emphasis", True),
            })
        else:
            # 클립 없는 문단: 직전 클립 마지막 프레임 정지 or 첫 클립 프레임
            anchor = clips[0] if clips else {"start": 0.0, "end": 0.1}
            segments.append({
                "kind": "freeze", "src_start": anchor["start"],
                "src_end": anchor["start"] + 0.1, "dur": dur,
                "footage_sec": 0.0, "zoom": False,
            })
        subtitles.append({"t_start": t, "t_end": t + tts["dur"],
                          "text": para["text"],
                          "emphasis": para.get("emphasis_words", [])})
        narr_track.append({**tts, "t_start": t})
        t += dur

    timeline = {
        "job_id": job_id, "width": 1080, "height": 1920, "fps": 30,
        "duration": round(t, 2), "segments": segments,
        "narration": narr_track, "subtitles": subtitles,
        "params": params, "license_type": license_type,
    }
    validate(timeline)
    return timeline


def validate(timeline: dict[str, Any]) -> None:
    """규격 + commentary 변형 규칙 기계 검증. 위반 시 예외 (렌더 진입 불가)."""
    total = timeline["duration"]
    if total <= 0 or total > MAX_DURATION_SEC:
        raise TransformRuleViolation(
            f"duration {total:.1f}s out of range (0, {MAX_DURATION_SEC}]")

    if timeline["license_type"] != "commentary":
        return

    r = COMMENTARY_RULES
    narr = sum(n["dur"] for n in timeline["narration"])
    coverage = narr / total
    if coverage < r["min_narration_coverage"]:
        raise TransformRuleViolation(
            f"narration coverage {coverage:.0%} < {r['min_narration_coverage']:.0%}")

    footage = 0.0
    for seg in timeline["segments"]:
        if seg["footage_sec"] > r["max_clip_sec"] + 1e-6:
            raise TransformRuleViolation(
                f"clip {seg['footage_sec']:.1f}s > {r['max_clip_sec']}s limit")
        footage += seg["footage_sec"]
    ratio = footage / total
    if ratio > r["max_footage_ratio"]:
        raise TransformRuleViolation(
            f"footage ratio {ratio:.0%} > {r['max_footage_ratio']:.0%}")
