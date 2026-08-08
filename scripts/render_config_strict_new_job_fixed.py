#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path
import urllib.request

base = Path("/data/videos")
JOB = "e6ef45e90ea54169b73dc19e555a7615"
source = next(Path(f"/data/work/{JOB}").glob("*.mkv"))
transcript_path = Path(f"/data/work/{JOB}/transcript.json")
out = base / f"{JOB}_rank01.config-strict.mp4"
ass = out.with_suffix(".ass")

# Ambil metadata LLM via API langsung karena di dalam container tidak ada /tmp/...-status.json
url = f"http://127.0.0.1:8000/jobs/{JOB}"
req = urllib.request.urlopen(url)
data = json.loads(req.read().decode('utf-8'))
res = json.loads(data['result_json'])
h = res['outputs'][0]['highlight']
TARGET_START = h["start"]
TARGET_END = h["end"]

# Baca segment transcript asli
transcript = json.loads(transcript_path.read_text(encoding="utf-8"))["segments"]

# Cari segmen PERTAMA yang menyentuh batas TARGET_START
actual_start = TARGET_START
for s in transcript:
    if s["end"] > TARGET_START and s["start"] <= TARGET_START:
        # Jika segmen ini kepotong di tengah, mundurkan trim FFmpeg ke awal segmen!
        # Agar suara dan teks yang di-generate sama-sama mulai dari kata pertama segmen itu
        actual_start = s["start"]
        break

# Lakukan hal yang sama untuk akhir (pastikan tidak memotong kalimat di akhir)
actual_end = TARGET_END
for s in transcript:
    if s["start"] < TARGET_END and s["end"] >= TARGET_END:
        actual_end = s["end"]
        break

DURATION = actual_end - actual_start

# 1. Generate subtitle dengan batas waktu yang disesuaikan
from shared.pipeline import build_subtitle_ass
build_subtitle_ass(transcript, actual_start, actual_end, ass, "1080x1920", "", "")

text = ass.read_text(encoding="utf-8")

# 2. Add Persistent POV
pov_event = (
    f"Dialogue: 5,0:00:00.00,0:00:{DURATION:.2f},Default,,0,0,0,,"
    "{\\an8\\pos(540,1540)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5"
    "\\3c&H00111111\\shad2\\4c&H99000000}"
    "{\\1c&H00FFFFFF}POV: KELAS MENENGAH\\N"
    "{\\1c&H00B000FF}AKAN HANCUR?\\N"
    "{\\fs32\\1c&H00FFFFFF\\bord3}@gusaja.com"
)
ass.write_text(text + pov_event + "\n", encoding="utf-8")

# 3. Trim dan Crop menggunakan waktu ACTUAL yang sinkron dengan transcript
fc = (
    f"[0:v]trim=start={actual_start}:end={actual_end},setpts=PTS-STARTPTS,fps=30,"
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
