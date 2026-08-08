#!/usr/bin/env python3
import subprocess
from pathlib import Path

base = Path("/data/videos")
source = base / "e5eff5133d084459b8cac51205d8e26a_rank01.context-first-adaptive-slide.mp4"
source_ass = source.with_suffix(".ass")
out = base / "e5eff5133d084459b8cac51205d8e26a_rank01.context-first-adaptive-slide-pov-fixed.mp4"
ass = out.with_suffix(".ass")

# Ambil header dari ASS asli, buang Dialogue transcript karena sudah ter-burn di source
lines = source_ass.read_text(encoding="utf-8").splitlines()
header = "\n".join([l for l in lines if not l.startswith("Dialogue:")])

# Gunakan format persisten persis seperti render_rank01_persistent_pov_sample.py
headline = (
    "Dialogue: 5,0:00:00.00,0:00:49.61,Default,,0,0,0,,"
    "{\\an2\\pos(540,1580)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5"
    "\\3c&H00111111\\shad2\\4c&H99000000}"
    "{\\1c&H00FFFFFF}POV: GAJI UMR?\\N"
    "{\\1c&H00B000FF}MULAI INVESTASI\\N"
    "{\\1c&H00FFFFFF}DARI {\\1c&H00B000FF}RP300 RIBU"
)

ass.write_text(header + "\n" + headline + "\n", encoding="utf-8")

cmd = [
    "ffmpeg", "-y", "-i", str(source), "-vf", f"subtitles=filename='{ass}'",
    "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(out)