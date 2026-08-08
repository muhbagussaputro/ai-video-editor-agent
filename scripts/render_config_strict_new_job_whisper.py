#!/usr/bin/env python3
import subprocess
import json
from pathlib import Path

base = Path("/data/videos")
JOB = "e6ef45e90ea54169b73dc19e555a7615"
source = next(Path(f"/data/work/{JOB}").glob("*.mkv"))
out = base / f"{JOB}_rank01.config-strict-sync-whisper.mp4"
ass = out.with_suffix(".ass")

ACTUAL_START = 71.84
ACTUAL_END = 104.36
DURATION = ACTUAL_END - ACTUAL_START

# Potong audio persis dari awal klip ke file sementara
audio_clip = "/tmp/clip_audio.wav"
subprocess.run([
    "ffmpeg", "-y", "-i", str(source), "-ss", str(ACTUAL_START), "-t", str(DURATION),
    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_clip, "-loglevel", "error"
], check=True)

# Generate word-level transcript menggunakan Whisper Lokal untuk rentang 32 detik ini saja!
# Ini akan mengatasi delay gila dari YouTube Auto Subs
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
segments_generator, _ = model.transcribe(audio_clip, language="id", word_timestamps=True)

normalized = []
for s in segments_generator:
    for w in s.words:
        # Kami ubah format segment faster_whisper -> ke format yang dipahami build_subtitle_ass
        # Perhatikan kita menambahkan ACTUAL_START kembali karena whisper berjalan di audio klip yang dimulai dari 0
        normalized.append({
            "start": w.start + ACTUAL_START,
            "end": w.end + ACTUAL_START,
            "duration": w.end - w.start,
            "text": w.word.strip()
        })

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
    f"subtitles=filename='{ass}'[v]; "
    f"[0:a]atrim=start={ACTUAL_START}:end={ACTUAL_END},asetpts=PTS-STARTPTS[a]"
)

cmd = [
    "ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
    "-map", "[v]", "-map", "[a]", "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(out)
