#!/usr/bin/env python3
"""15s proof: normal compact subtitle text-runs, no per-word absolute layout."""
import json
import re
from pathlib import Path

from shared.pipeline import CropAnalysis, build_subtitle_ass, render_vertical_clip

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
START, DURATION = 3062.599, 15.0
END = START + DURATION
HOOK = "Tes Masuk Hedge Fund: 99% Orang Gagal Jawab Pertanyaan Koin Ini"
base = Path("/data/work") / JOB
source = next(base.glob("*.mkv"))
out = Path("/data/videos") / f"{JOB}.normal-text-run-lower-20pct-15s.mp4"
ass = out.with_suffix(".ass")

raw_segments = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
# Make one sequential transcript stream only for this proof; native source text
# is retained, while corrupt overlapping micro-cue timing is normalized.
words: list[str] = []
for segment in raw_segments:
    if float(segment["end"]) <= START or float(segment["start"]) >= END:
        continue
    words.extend(token for token in str(segment.get("text", "")).split() if not re.fullmatch(r"[A-Za-z]", token))
segments = [{"start": START, "end": END, "text": " ".join(words), "words": []}]

build_subtitle_ass(segments, START, END, ass, "1080x1920", HOOK, "aura")
text = ass.read_text(encoding="utf-8")
# No whole-block pop / no per-word coordinates: libass owns natural word spacing.
text = re.sub(r"\\fscx100\\fscy100\\t\(0,120,\\fscx105\\fscy105\)\\t\(120,220,\\fscx100\\fscy100\)", "", text)
# The normal-text proof anchors the entire subtitle run once. Shift it 20% of
# the remaining safe canvas height toward the bottom: y=1125 -> 1284 px.
text = text.replace(r"\an1\pos(108,1125)", r"\an1\pos(108,1284)")
if r"\an1\pos(108,1125)" in text or r"\an1\pos(108,1284)" not in text:
    raise RuntimeError("normal-text subtitle anchor replacement failed")
ass.write_text(text, encoding="utf-8")

crop = CropAnalysis(1240, 0, 1080, 1920, 44, 3, 45, "face-stabilized", "Reuse verified rank-1 crop", "9:16", 0)
render_vertical_clip(source, out, START, DURATION, "1080x1920", 30, ass, crop)
print(json.dumps({"output": str(out), "ass": str(ass), "duration": DURATION, "mode": "normal-text-run"}))
