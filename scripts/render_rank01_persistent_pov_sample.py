#!/usr/bin/env python3
"""Proof persistent editorial POV headline in the lower safe area of rank 1."""
import subprocess
from pathlib import Path

base = Path("/data/videos")
source = base / "e189716e8086452bb7f710d93151cc9c_rank01.adaptive-slide-upper-topdown.mp4"
source_ass = source.with_suffix(".ass")
out = base / "e189716e8086452bb7f710d93151cc9c_rank01.pov-persistent-editorial-15s.mp4"
ass = out.with_suffix(".ass")

# Keep transcript under the upper-middle slide (y=1030). The persistent POV sits
# separately in the lower safe area and remains visible from first to final frame.
headline = (
    "Dialogue: 5,0:00:00.00,0:00:45.00,Default,,0,0,0,,"
    "{\\an2\\pos(540,1580)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5"
    "\\3c&H00111111\\shad2\\4c&H99000000}"
    "{\\1c&H00FFFFFF}POV: GAJI KECIL\\N"
    "{\\1c&H00B000FF}MULAI INVESTASI\\N"
    "{\\1c&H00FFFFFF}DARI {\\1c&H00B000FF}RP300 RIBU"
)
# The input MP4 already has the transcript burned in. Retain only ASS headers/styles,
# then append the persistent POV overlay (not every transcript Dialogue again).
header = "\n".join(source_ass.read_text(encoding="utf-8").splitlines()[:14])
ass.write_text(header + "\n" + headline + "\n", encoding="utf-8")

cmd = [
    "ffmpeg", "-y", "-i", str(source), "-vf", f"subtitles=filename='{ass}'",
    "-t", "15", "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(out)
