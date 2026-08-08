#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

base = Path("/data/videos")
JOB = "e6ef45e90ea54169b73dc19e555a7615"
# Cari MKV source-nya dari folder job
source = next(Path(f"/data/work/{JOB}").glob("*.mkv"))
transcript_path = Path(f"/data/work/{JOB}/transcript.json")
out = base / f"{JOB}_rank01.config-strict.mp4"
ass = out.with_suffix(".ass")

# Ambil rentang asli quote yang terpilih dari metadata job!
# Kita tidak boleh hardcode START & END dari job lama.
job_status = json.loads(Path(f"/tmp/{JOB}-status.json").read_text(encoding="utf-8"))
result_json = json.loads(job_status["result_json"])
highlight = result_json["outputs"][0]["highlight"]
START = highlight["start"]
END = highlight["end"]
DURATION = highlight["duration"]

# 1. Generate subtitle
from shared.pipeline import build_subtitle_ass
transcript = json.loads(transcript_path.read_text(encoding="utf-8"))["segments"]
build_subtitle_ass(transcript, START, END, ass, "1080x1920", "", "")

# Subtitle biarkan di posisi wajah (y=1284) karena adegan ini adalah talking head.
text = ass.read_text(encoding="utf-8")

# 2. Add Persistent POV + Handle per adaptive-layout.json
# position: x=540, y=1540 (Bottom center)
# alignment: an8
pov_event = (
    f"Dialogue: 5,0:00:00.00,0:00:{DURATION:.2f},Default,,0,0,0,,"
    "{\\an8\\pos(540,1540)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5"
    "\\3c&H00111111\\shad2\\4c&H99000000}"
    "{\\1c&H00FFFFFF}POV: KELAS MENENGAH\\N"
    "{\\1c&H00B000FF}AKAN HANCUR?\\N"
    "{\\fs32\\1c&H00FFFFFF\\bord3}@gusaja.com"
)
ass.write_text(text + pov_event + "\n", encoding="utf-8")

# 3. Apply Full-Height Face Crop (Karena Face, MediaPipe mendeteksi 35 wajah)
# Kita terapkan crop wajah statis ke tengah: crop=in_h*9/16:in_h
# Note: Source asli (MKV) beresolusi 2560x1440. in_h = 1440. 9/16 * 1440 = 810.
# Jadi crop=810:1440, baru scale ke 1080:1920.
fc = (
    f"[0:v]trim=start={START}:end={END},setpts=PTS-STARTPTS,fps=30,"
    "crop=in_h*9/16:in_h,scale=1080:1920,setsar=1,format=yuv420p,"
    f"subtitles=filename='{ass}'[v]"
)

cmd = [
    "ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
    "-map", "[v]", "-map", "0:a?", "-t", f"{DURATION:.3f}", "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(out)
