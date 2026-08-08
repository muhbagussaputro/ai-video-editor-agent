from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any


def _probe(path: Path) -> dict[str, Any]:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,start_time,duration", "-of", "json", str(path)], text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "ffprobe failed")
    return json.loads(result.stdout)


def technical_qc(path: Path, resolution: str, min_duration: float = .1) -> dict[str, Any]:
    issues: list[str] = []
    checks: dict[str, bool] = {"exists": path.is_file() and path.stat().st_size > 0}
    if not checks["exists"]:
        return {"passed": False, "checks": checks, "issues": ["missing or empty output"]}
    try:
        data = _probe(path); checks["ffprobe"] = True
    except ValueError as exc:
        return {"passed": False, "checks": {**checks, "ffprobe": False}, "issues": [str(exc)]}
    streams = {item.get("codec_type"): item for item in data.get("streams", [])}
    video, audio = streams.get("video"), streams.get("audio")
    checks["video_stream"] = bool(video); checks["audio_stream"] = bool(audio)
    if not video: issues.append("missing video stream")
    if not audio: issues.append("missing audio stream")
    expected_w, expected_h = (int(x) for x in resolution.split("x", 1))
    checks["resolution"] = bool(video and video.get("width") == expected_w and video.get("height") == expected_h)
    if not checks["resolution"]: issues.append("wrong resolution")
    duration = float(data.get("format", {}).get("duration") or 0)
    checks["duration"] = duration >= min_duration
    if not checks["duration"]: issues.append("invalid duration")
    checks["start_times"] = bool(video and audio and abs(float(video.get("start_time") or 0)) < .01 and abs(float(audio.get("start_time") or 0)) < .01)
    if not checks["start_times"]: issues.append("nonzero stream start")
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"], capture_output=True, text=True)
    checks["decode"] = decode.returncode == 0
    if not checks["decode"]: issues.append("video decode failed")
    black = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=.25:pix_th=.10", "-an", "-f", "null", "-"], capture_output=True, text=True)
    checks["black_frames"] = "black_start" not in black.stderr
    if not checks["black_frames"]: issues.append("unexpected black segment")
    volume = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    checks["audio_not_silent"] = "mean_volume: -91.0 dB" not in volume.stderr
    if not checks["audio_not_silent"]: issues.append("audio silent")
    return {"passed": not issues, "checks": checks, "issues": issues, "duration": duration}
