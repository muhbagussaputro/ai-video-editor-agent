#!/usr/bin/env python3
"""15-second proof: slide upper-middle, transcript tight below, persistent POV lower-third."""
import json
import subprocess
from pathlib import Path
from shared.pipeline import build_subtitle_ass

SOURCE_JOB = "26b9eea7dae24cfda9dc38f40d8eabde"
START, DURATION = 996.68, 15.0
base = Path("/data/work") / SOURCE_JOB
source = next(base.glob("*.mkv"))
transcript = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
out = Path("/data/videos/e189716e8086452bb7f710d93151cc9c_rank01.pov-persistent-tight-transcript-15s.mp4")
ass = out.with_suffix(".ass")

build_subtitle_ass(transcript, START, START + DURATION, ass, "1080x1920", "", "")
text = ass.read_text(encoding="utf-8").replace(r"\pos(108,1284)", r"\pos(108,880)")
headline = (
    "Dialogue: 5,0:00:00.00,0:00:15.00,Default,,0,0,0,,"
    "{\\an2\\pos(540,1580)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5"
    "\\3c&H00111111\\shad2\\4c&H99000000}"
    "{\\1c&H00FFFFFF}POV: GAJI KECIL\\N"
    "{\\1c&H00B000FF}MULAI INVESTASI\\N"
    "{\\1c&H00FFFFFF}DARI {\\1c&H00B000FF}RP300 RIBU"
)
ass.write_text(text.rstrip() + "\n" + headline + "\n", encoding="utf-8")

fc = (
    f"[0:v]trim=start={START}:duration={DURATION},setpts=PTS-STARTPTS,"
    "fps=30,scale=1080:608,pad=1080:1920:0:250:color=black,"
    f"subtitles=filename='{ass}'[v]"
)
cmd = ["ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
       "-map", "[v]", "-map", "0:a?", "-t", str(DURATION), "-r", "30",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
subprocess.run(cmd, check=True)
print(out)
