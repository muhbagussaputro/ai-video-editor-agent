#!/usr/bin/env python3
"""Render context-first rank 1 with full 16:9 slide preserved on a 9:16 canvas."""
import json
import subprocess
from pathlib import Path

from shared.pipeline import build_subtitle_ass

JOB = "e5eff5133d084459b8cac51205d8e26a"
START, END = 996.68, 1046.28
source = next((Path("/data/work") / JOB).glob("*.mkv"))
transcript = json.loads(((Path("/data/work") / JOB / "transcript.json").read_text(encoding="utf-8")))["segments"]
out = Path(f"/data/videos/{JOB}_rank01.context-first-adaptive-slide.mp4")
ass = out.with_suffix(".ass")

build_subtitle_ass(transcript, START, END, ass, "1080x1920", "", "")
# Slides occupy upper-middle y=250..858. Put each caption safely below them.
text = ass.read_text(encoding="utf-8").replace(r"\pos(108,1284)", r"\pos(108,1030)")
ass.write_text(text, encoding="utf-8")

fc = (
    f"[0:v]trim=start={START}:end={END},setpts=PTS-STARTPTS,fps=30,"
    "scale=1080:608,pad=1080:1920:0:250:color=black,setsar=1,format=yuv420p,"
    f"subtitles=filename='{ass}'[v]"
)
cmd = [
    "ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
    "-map", "[v]", "-map", "0:a?", "-t", f"{END-START:.3f}", "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(json.dumps({"output": str(out), "ass": str(ass), "duration": END - START}))
