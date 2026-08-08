#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

base = Path("/data/videos")
# We must use the original MKV source for rendering, NOT the already-cropped 9:16 fallback MP4
source = Path("/data/work/e5eff5133d084459b8cac51205d8e26a/Cara Merubah 300 Ribu Menjadi 1 Miliar [TrdUby31y84].mkv")
transcript_path = Path("/data/work/e5eff5133d084459b8cac51205d8e26a/transcript.json")
out = base / "e5eff5133d084459b8cac51205d8e26a_rank01.config-strict.mp4"
ass = out.with_suffix(".ass")

START, END = 996.68, 1046.28

# 1. Create subtitles adhering to adaptive-layout.json anchor
from shared.pipeline import build_subtitle_ass
transcript = json.loads(transcript_path.read_text(encoding="utf-8"))["segments"]
build_subtitle_ass(transcript, START, END, ass, "1080x1920", "", "")

# Modify ASS to use 4:3 presentation anchor (\an7, y=1080) since this entire clip is presentation mode
text = ass.read_text(encoding="utf-8")
text = text.replace(r"\pos(108,1284)", r"\pos(108,1080)")

# 2. Add Persistent POV + Handle per adaptive-layout.json
pov_event = (
    "Dialogue: 5,0:00:00.00,0:00:49.61,Default,,0,0,0,,"
    "{\\an8\\pos(540,1540)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5"
    "\\3c&H00111111\\shad2\\4c&H99000000}"
    "{\\1c&H00FFFFFF}POV: GAJI UMR?\\N"
    "{\\1c&H00B000FF}MULAI INVESTASI\\N"
    "{\\1c&H00FFFFFF}DARI {\\1c&H00B000FF}RP300 RIBU\\N"
    "{\\fs32\\1c&H00FFFFFF\\bord3}@gusaja.com"
)
ass.write_text(text + pov_event + "\n", encoding="utf-8")

# 3. Apply Presentation Mode Crop (center 16:9 -> 4:3 -> fit 1080x810, placed at y=250)
fc = (
    f"[0:v]trim=start={START}:end={END},setpts=PTS-STARTPTS,fps=30,"
    "crop=in_h*4/3:in_h,scale=1080:810,pad=1080:1920:0:250:color=black,setsar=1,format=yuv420p,"
    f"subtitles=filename='{ass}'[v]"
)

cmd = [
    "ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
    "-map", "[v]", "-map", "0:a?", "-t", f"{END-START:.3f}", "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(out)
