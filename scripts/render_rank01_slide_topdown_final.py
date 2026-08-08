#!/usr/bin/env python3
"""Render rank 1 as an upper-middle full 16:9 presentation with top-down captions below."""
import json
import subprocess
from pathlib import Path

from shared.pipeline import build_subtitle_ass

SOURCE_JOB = "26b9eea7dae24cfda9dc38f40d8eabde"
START = 996.68
DURATION = 45.0
base = Path("/data/work") / SOURCE_JOB
source = next(base.glob("*.mkv"))
transcript = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
out = Path("/data/videos/e189716e8086452bb7f710d93151cc9c_rank01.adaptive-slide-upper-topdown.mp4")
ass = out.with_suffix(".ass")

# The current renderer uses \an7 so the first line remains fixed while lines 2-3
# accumulate downward. Re-anchor the entire presentation-heavy clip below the slide.
build_subtitle_ass(transcript, START, START + DURATION, ass, "1080x1920", "", "")
text = ass.read_text(encoding="utf-8")
text = text.replace(r"\pos(108,1284)", r"\pos(108,1030)")
ass.write_text(text, encoding="utf-8")

fc = (
    f"[0:v]trim=start={START}:duration={DURATION},setpts=PTS-STARTPTS,"
    "fps=30,scale=1080:608,pad=1080:1920:0:250:color=black,"
    f"subtitles=filename='{ass}'[v]"
)
cmd = [
    "ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
    "-map", "[v]", "-map", "0:a?", "-t", str(DURATION), "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(json.dumps({"output": str(out), "ass": str(ass), "source_window": [START, START + DURATION], "layout": "upper-middle 16:9 slide; below-slide top-down transcript"}))
