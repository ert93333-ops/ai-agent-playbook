"""편집 코어 단위 테스트 — 변형 규칙(0-1-1) 기계 검증."""
import pytest

from app.editing import timeline as tl


def _narr(durs):
    return [{"idx": i, "text": f"p{i}", "audio": f"tts_{i:03d}.mp3", "dur": d}
            for i, d in enumerate(durs)]


def _script(refs):
    return [{"text": f"p{i}", "clip_ref": r, "emphasis_words": []}
            for i, r in enumerate(refs)]


CLIPS = [{"start": 10.0, "end": 16.0, "role": "hook"},
         {"start": 30.0, "end": 34.0, "role": "evidence"}]


def test_compile_ok_commentary():
    t = tl.compile_timeline(
        job_id=1, clips=CLIPS, script=_script([0, None, 1, None]),
        narration=_narr([8.0, 8.0, 8.0, 8.0]), params={},
        license_type="commentary")
    assert len(t["segments"]) == 4
    assert t["duration"] == pytest.approx(4 * 8.25, abs=0.01)
    # 나레이션 커버리지 100%, 푸티지 = 6 + 4 = 10s / 33s < 50%
    assert sum(s["footage_sec"] for s in t["segments"]) == pytest.approx(10.0)


def test_clip_clamped_to_8s():
    long_clip = [{"start": 0.0, "end": 20.0, "role": "hook"}]
    t = tl.compile_timeline(
        job_id=1, clips=long_clip, script=_script([0, None]),
        narration=_narr([12.0, 12.0]), params={}, license_type="commentary")
    assert t["segments"][0]["footage_sec"] <= 8.0


def test_footage_ratio_violation():
    # 전 문단 클립 → 푸티지 비율 초과
    with pytest.raises(tl.TransformRuleViolation, match="footage ratio"):
        tl.compile_timeline(
            job_id=1, clips=CLIPS, script=_script([0, 1, 0, 1]),
            narration=_narr([6.0, 4.0, 6.0, 4.0]), params={},
            license_type="commentary")


def test_duration_cap():
    with pytest.raises(tl.TransformRuleViolation, match="duration"):
        tl.compile_timeline(
            job_id=1, clips=CLIPS, script=_script([None] * 10),
            narration=_narr([8.0] * 10), params={}, license_type="commentary")


def test_own_license_skips_commentary_rules():
    # own 소스는 푸티지 100%여도 허용 (규격 검증만)
    t = tl.compile_timeline(
        job_id=1, clips=CLIPS, script=_script([0, 1]),
        narration=_narr([6.0, 4.0]), params={}, license_type="own")
    assert t["duration"] < 60
