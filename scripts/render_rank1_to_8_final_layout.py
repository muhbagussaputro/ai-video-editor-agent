#!/usr/bin/env python3
"""Render approved final style for ranks 1-8, preserving each rank's own window."""
import json
import os
import subprocess
from pathlib import Path

from shared.pipeline import build_subtitle_ass

JOB = "e189716e8086452bb7f710d93151cc9c"
SOURCE_JOB = "26b9eea7dae24cfda9dc38f40d8eabde"
base = Path("/data/work") / SOURCE_JOB
source = next(base.glob("*.mkv"))
transcript = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
# The project directory is bind-mounted into the app container; host /tmp is not.
result = json.loads(Path("/app/.rank-batch-e189-result.json").read_text(encoding="utf-8"))
outputs = sorted(result["outputs"], key=lambda row: int(row["rank"]))
# Optional comma-separated ranks for proof renders, e.g. RANKS=2.
requested_ranks = {int(value) for value in os.getenv("RANKS", "").split(",") if value.strip()}
if requested_ranks:
    outputs = [row for row in outputs if int(row["rank"]) in requested_ranks]

# Persistent editorial hook, adapted to the actual point of each ranked highlight.
POVS = {
    1: ("POV: GAJI KECIL", "MULAI INVESTASI", "DARI RP300 RIBU"),
    2: ("POV: KAMU MASIH", "MEREMEHKAN", "NOMINAL KECIL"),
    3: ("POV: SUDAH NAIK GAJI", "TAPI KAMU", "TETAP MENABUNG"),
    4: ("POV: MAU INVESTASI", "TAPI MASIH", "PUNYA UTANG"),
    5: ("POV: MAU KAYA", "TAPI MAUNYA", "INSTAN"),
    6: ("POV: NOMINAL KECIL", "TAPI MAU IKUT", "BANGUN NEGARA"),
    7: ("POV: MAKIN DEWASA", "MAKIN HARUS", "KONSERVATIF"),
    8: ("POV: MAU INVESTASI", "TAPI CASH FLOW", "BELUM AMAN"),
}

def ass_time(seconds: float) -> str:
    total_cs = int(round(seconds * 100))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    return f"{hours}:{minutes:02d}:{rem / 100:05.2f}"

for item in outputs:
    rank = int(item["rank"])
    h = item["highlight"]
    crop = item["crop"]
    start, duration = float(h["start"]), float(h["duration"])
    end = start + duration
    stem = f"{JOB}_rank{rank:02d}.final-pov-combined-v3"
    out = Path("/data/videos") / f"{stem}.mp4"
    ass = out.with_suffix(".ass")

    build_subtitle_ass(transcript, start, end, ass, "1080x1920", "", "")
    transcript_y = 1080 if rank == 1 else 1284
    # Force top-left anchoring even if a stale worker/runtime generator emits \an1.
    # This keeps line 1 fixed while lines 2-3 continue downward.
    text = ass.read_text(encoding="utf-8")
    text = text.replace(r"\an1", r"\an7").replace(r"\pos(108,1284)", rf"\pos(108,{transcript_y})")
    a, b, c = POVS[rank]
    headline = (
        f"Dialogue: 5,0:00:00.00,{ass_time(duration)},Default,,0,0,0,,"
        # Top-center anchoring makes the entire four-line POV/handle block grow down,
        # preventing it from expanding upward into the face-scene transcript.
        "{\\an8\\pos(540,1540)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5\\3c&H00111111\\shad2}"
        f"{{\\1c&H00FFFFFF}}{a}\\N{{\\1c&H00B000FF}}{b}\\N"
        f"{{\\1c&H00FFFFFF}}{c}"
        "{\\r\\fs32\\fnMontserrat SemiBold\\b1\\bord2\\3c&H00111111\\shad1\\1c&H00F0D0FF}\\N@gusaja.com"
    )
    ass.write_text(text.rstrip() + "\n" + headline + "\n", encoding="utf-8")

    if rank == 1:
        # Presentation: 16:9 -> 4:3 center crop, scale 1080x810, upper-middle.
        video = "crop=1920:1440:320:0,scale=1080:810,pad=1080:1920:0:250:color=black"
    else:
        # Face-led ranks retain individually verified face-aware crop coordinates.
        crop_x = int(crop["crop_x"])
        video = f"scale=3414:1920,crop=1080:1920:{crop_x}:0"
    fc = (
        f"[0:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS,fps=30,{video},"
        f"subtitles=filename='{ass}'[v];"
        f"[0:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS[a]"
    )
    cmd = ["ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
           "-map", "[v]", "-map", "[a]", "-t", str(duration), "-r", "30",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    print(json.dumps({"rank": rank, "start": start, "duration": duration, "layout": "4:3-slide" if rank == 1 else "9:16-face", "output": str(out)}, ensure_ascii=False), flush=True)
    subprocess.run(cmd, check=True)

print(json.dumps({"status": "completed", "ranks": len(outputs), "prefix": f"/data/videos/{JOB}_rankNN.final-pov-combined"}))
