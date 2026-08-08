#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

base = Path("/data/videos")
JOB = "e6ef45e90ea54169b73dc19e555a7615"
source = next(Path(f"/data/work/{JOB}").glob("*.mkv"))
out = base / f"{JOB}_rank01.config-strict-sync4.mp4"
ass = out.with_suffix(".ass")

# POTONGAN ABSOLUT BERDASARKAN WORD TIMESTAMPS:
# Kata "Dunia" (mulai kalimat highlight) = 71.84s
# Akhir kata "hidupnya" = 104.36s (asumsi duration 32.52s)
ACTUAL_START = 71.84
ACTUAL_END = 104.36
DURATION = ACTUAL_END - ACTUAL_START

# Baca transkrip untuk subtitle, dan KITA HAPUS segmen "berkali-kali lipat" agar 
# subtitle dimulai tepat di kalimat "Dunia yang sekarang..."
transcript_path = Path(f"/data/work/{JOB}/transcript.json")
transcript = json.loads(transcript_path.read_text(encoding="utf-8"))["segments"]

normalized = []
last_end = ACTUAL_START
for s in transcript:
    if s["end"] <= ACTUAL_START:
        continue  # skip semua sebelum Dunia
        
    n_s = dict(s)
    # Jika segmen YouTube overlap ke "berkali-kali lipat. Dunia...",
    # Kita overwrite text nya jadi "Dunia yang sekarang..." saja
    if "berkali-kali" in n_s["text"].lower() and "dunia" in n_s["text"].lower():
        n_s["text"] = "Dunia yang sekarang"
        
    if n_s['start'] < last_end:
        n_s['start'] = last_end
    if n_s['end'] <= n_s['start']:
        n_s['end'] = n_s['start'] + 0.1
    n_s['duration'] = n_s['end'] - n_s['start']
    
    if n_s['start'] >= ACTUAL_END:
        break
        
    normalized.append(n_s)
    last_end = n_s['end']

# 1. Generate subtitle ASS
from shared.pipeline import build_subtitle_ass
build_subtitle_ass(normalized, ACTUAL_START, ACTUAL_END, ass, "1080x1920", "", "")

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

# 3. Trim dan Crop
fc = (
    f"[0:v]trim=start={ACTUAL_START}:end={ACTUAL_END},setpts=PTS-STARTPTS,fps=30,"
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
