#!/usr/bin/env python3
"""Add an opening POV hook to the verified adaptive-slide rank 1 render."""
import subprocess
from pathlib import Path

base = Path("/data/videos")
source = base / "e5eff5133d084459b8cac51205d8e26a_rank01.context-first-adaptive-slide.mp4"
out = base / "e5eff5133d084459b8cac51205d8e26a_rank01.context-first-adaptive-slide-pov.mp4"
ass = out.with_suffix(".ass")

ass.write_text(
    """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: POV,Montserrat ExtraBold,52,&H00FFFFFF,&H000000FF,&H00111111,&H99000000,-1,0,0,0,100,100,0,0,1,5,2,2,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 5,0:00:00.00,0:00:07.00,POV,,0,0,0,,{\\an2\\pos(540,150)\\bord5\\shad2}{\\1c&H00FFFFFF}POV: GAJI UMR?\\N{\\1c&H0000C8FF}RP300 RIBU/BULAN\\N{\\1c&H00FFFFFF}BISA JADI RP1 MILIAR
""",
    encoding="utf-8",
)
cmd = [
    "ffmpeg", "-y", "-i", str(source), "-vf", f"subtitles=filename='{ass}'",
    "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(out)
