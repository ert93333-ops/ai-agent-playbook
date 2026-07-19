"""타임라인 JSON → 단일 ffmpeg 명령 컴파일 (SPEC M5).

출력 규격: 1080x1920, H.264 high CRF 18, 30fps, AAC 192k, loudnorm I=-14.
원본 오디오는 클립 구간만 -18dB로 깔리고 나레이션이 백본.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

DUCK_DB = -18


def build_command(timeline: dict[str, Any], *, source: Path, ass_path: Path,
                  tts_dir: Path, out_path: Path,
                  logo: Path | None = None) -> list[str]:
    segs = timeline["segments"]
    narr = timeline["narration"]

    inputs: list[str] = ["-i", str(source)]
    for n in narr:
        inputs += ["-i", str(tts_dir / n["audio"])]
    n_narr = len(narr)
    logo_idx = None
    if logo and logo.exists():
        logo_idx = 1 + n_narr
        inputs += ["-loop", "1", "-i", str(logo)]

    f: list[str] = []

    # --- 비디오: 세그먼트별 trim → 9:16 크롭 → (펀치인) → 정지 패딩 → concat
    for i, s in enumerate(segs):
        clip_len = s["src_end"] - s["src_start"]
        pad = max(0.0, s["dur"] - clip_len)
        punch = "scale=1188:2112,crop=1080:1920," if s.get("zoom") else ""
        f.append(
            f"[0:v]trim=start={s['src_start']:.3f}:end={s['src_end']:.3f},"
            f"setpts=PTS-STARTPTS,"
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,{punch}"
            f"tpad=stop_mode=clone:stop_duration={pad:.3f},fps=30[v{i}]"
        )
    f.append("".join(f"[v{i}]" for i in range(len(segs)))
             + f"concat=n={len(segs)}:v=1:a=0[vcat]")

    # 자막 burn-in (+ 로고 오버레이)
    vsub = f"[vcat]ass='{ass_path}'[vsub]"
    f.append(vsub)
    vfinal = "vsub"
    if logo_idx is not None:
        f.append(f"[{logo_idx}:v]scale=120:120[logo];"
                 f"[vsub][logo]overlay=W-w-40:40:shortest=0[vlogo]")
        vfinal = "vlogo"

    # --- 오디오: 원본(클립 구간만, 더킹) 세그먼트 concat + 나레이션 딜레이 mix
    for i, s in enumerate(segs):
        if s["kind"] == "clip":
            f.append(
                f"[0:a]atrim=start={s['src_start']:.3f}:end={s['src_end']:.3f},"
                f"asetpts=PTS-STARTPTS,volume={DUCK_DB}dB,"
                f"apad=whole_dur={s['dur']:.3f}[a{i}]")
        else:
            f.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={s['dur']:.3f}[a{i}]")
    f.append("".join(f"[a{i}]" for i in range(len(segs)))
             + f"concat=n={len(segs)}:v=0:a=1[orig]")

    for j, n in enumerate(narr):
        ms = int(n["t_start"] * 1000)
        f.append(f"[{1 + j}:a]adelay={ms}|{ms}[nd{j}]")
    narr_labels = "".join(f"[nd{j}]" for j in range(n_narr))
    f.append(f"[orig]{narr_labels}amix=inputs={n_narr + 1}:normalize=0,"
             f"loudnorm=I=-14:TP=-1.5:LRA=11[afinal]")

    return [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(f),
        "-map", f"[{vfinal}]", "-map", "[afinal]",
        "-t", f"{timeline['duration']:.2f}",
        "-c:v", "libx264", "-profile:v", "high", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out_path),
    ]
