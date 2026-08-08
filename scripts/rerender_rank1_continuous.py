#!/usr/bin/env python3
"""Rerender approved rank 1 with the persisted continuous three-line captions."""
import json
from pathlib import Path

from shared.pipeline import CropAnalysis, build_subtitle_ass, render_vertical_clip

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
START = 3062.599
END = 3107.599
HOOK = "Tes Masuk Hedge Fund: 99% Orang Gagal Jawab Pertanyaan Koin Ini"
base = Path("/data/work") / JOB
source = next(base.glob("*.mkv"))
transcript = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
out = Path("/data/videos") / f"{JOB}.normal-text-run-lower-20pct-full.mp4"
ass = out.with_suffix(".ass")
subtitle = build_subtitle_ass(
    transcript,
    START,
    END,
    ass,
    target_resolution="1080x1920",
    opening_hook_text=HOOK,
    clipper_style="aura",
)
crop = CropAnalysis(
    crop_x=1240, crop_y=0, crop_w=1080, crop_h=1920,
    face_hits=44, scene_cuts=3, samples=45,
    mode="face-stabilized", reason="Reuse verified rank-1 crop",
    aspect_ratio="9:16", two_person_frames=0,
)
render_vertical_clip(source, out, START, END - START, "1080x1920", 30, ass, crop)
print(json.dumps({"output": str(out), "ass": str(ass), "subtitle": subtitle, "duration": END - START}))
