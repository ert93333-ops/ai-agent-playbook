"""Edge-TTS 나레이션 생성. 문단 단위로 mp3 생성 후 실측 길이를 돌려준다."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path


def media_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


async def _synth(text: str, voice: str, rate: str, out_path: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out_path))


def synthesize(paragraphs: list[str], *, voice: str, rate: str,
               out_dir: Path) -> list[dict]:
    """각 문단을 mp3로 합성. [{idx, text, audio, dur}] 반환. 멱등."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, text in enumerate(paragraphs):
        path = out_dir / f"tts_{i:03d}.mp3"
        if not path.exists():
            tmp = path.with_suffix(".tmp.mp3")
            asyncio.run(_synth(text, voice, rate, tmp))
            tmp.rename(path)
        results.append({"idx": i, "text": text, "audio": path.name,
                        "dur": media_duration(path)})
    return results
