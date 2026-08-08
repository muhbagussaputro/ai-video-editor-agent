#!/usr/bin/env python3
"""Render an explicit POV-styled rank-1 variant from the approved 1440p source."""
import json
from pathlib import Path

from shared.pipeline import CropAnalysis, build_subtitle_ass, render_vertical_clip

SOURCE_JOB = "26b9eea7dae24cfda9dc38f40d8eabde"
START = 996.68
END = 1041.68
HOOK = "POV: Gaji Kecil Tapi Mulai Investasi dari Rp300 Ribu"
base = Path("/data/work") / SOURCE_JOB
source = next(base.glob("*.mkv"))
transcript = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
out = Path("/data/videos/e189716e8086452bb7f710d93151cc9c_rank01.pov.mp4")
ass = out.with_suffix(".ass")

build_subtitle_ass(
    transcript,
    START,
    END,
    ass,
    target_resolution="1080x1920",
    opening_hook_text=HOOK,
    clipper_style="pov",
)
# Preserve the verified rank-1 face crop; only the editorial/caption treatment differs.
crop = CropAnalysis(
    crop_x=942, crop_y=0, crop_w=1080, crop_h=1920,
    face_hits=45, scene_cuts=0, samples=45,
    mode="face-stabilized", reason="Reuse verified rank-1 crop for POV variant",
    aspect_ratio="9:16", two_person_frames=0,
)
render_vertical_clip(source, out, START, END - START, "1080x1920", 30, ass, crop)
print(json.dumps({"output": str(out), "ass": str(ass), "style": "pov", "hook": HOOK, "duration": END - START}))
