"""ASS 자막 생성 — 워드 단위 카라오케 하이라이트.

단어 타이밍은 TTS 문단 길이를 글자 수 비례로 배분해 추정한다 (±0.2초 목표).
세이프존: 상단 12% / 하단 25% 회피는 margin_v로 처리 (SPEC M4).
"""
from __future__ import annotations

from pathlib import Path

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},&H00FFFFFF,&H0000D7FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_ALIGN = {"bottom": 2, "center": 5}


def _ts(sec: float) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _line(text: str, emphasis: set[str], dur_cs: int) -> str:
    """워드 단위 \\k 카라오케 + 강조 단어 색상."""
    words = text.split()
    if not words:
        return text
    total_chars = sum(len(w) for w in words) or 1
    parts = []
    for w in words:
        k = max(1, round(dur_cs * len(w) / total_chars))
        if w.strip(".,!?") in emphasis:
            parts.append(rf"{{\k{k}\c&H00D7FF&}}{w}{{\c&HFFFFFF&}}")
        else:
            parts.append(rf"{{\k{k}}}{w}")
    return " ".join(parts)


def write_ass(subtitles: list[dict], out_path: Path, *,
              font: str = "Pretendard", size: int = 84,
              align: str = "bottom", margin_v: int = 560) -> Path:
    """subtitles: [{t_start, t_end, text, emphasis: [..]}]"""
    lines = [HEADER.format(font=font, size=size,
                           align=_ALIGN.get(align, 2), margin_v=margin_v)]
    for sub in subtitles:
        dur_cs = int((sub["t_end"] - sub["t_start"]) * 100)
        text = _line(sub["text"], set(sub.get("emphasis", [])), dur_cs)
        lines.append(f"Dialogue: 0,{_ts(sub['t_start'])},{_ts(sub['t_end'])},"
                     f"Main,,0,0,0,,{text}")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
