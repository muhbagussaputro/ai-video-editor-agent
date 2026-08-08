#!/usr/bin/env python3
"""Rerender approved ranks 2–5 with persisted continuous three-line captions."""
import json
from pathlib import Path

from shared.pipeline import CropAnalysis, build_subtitle_ass, render_vertical_clip

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
base = Path("/data/work") / JOB
source = next(base.glob("*.mkv"))
transcript = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
outputs = json.loads(Path("/tmp/outputs-all.json").read_text(encoding="utf-8"))

for item in outputs:
    rank = int(item["rank"])
    if rank not in {2, 3, 4}:
        continue
    highlight = item["highlight"]
    crop_data = item["crop"]
    start = float(highlight["start"])
    end = float(highlight["end"])
    hook = str(highlight.get("hook_text", ""))
    style = str(highlight.get("clipper_style", ""))
    out = Path("/data/videos") / f"{JOB}_highlight_{rank:02d}.normal-text-run-lower-20pct-full.mp4"
    ass = out.with_suffix(".ass")
    subtitle = build_subtitle_ass(
        transcript, start, end, ass, "1080x1920", hook, style
    )
    crop = CropAnalysis(
        crop_x=int(crop_data["crop_x"]), crop_y=int(crop_data["crop_y"]),
        crop_w=int(crop_data["crop_w"]), crop_h=int(crop_data["crop_h"]),
        face_hits=int(crop_data.get("face_hits", 0)), scene_cuts=int(crop_data.get("scene_cuts", 0)),
        samples=int(crop_data.get("samples", 0)), mode=str(crop_data.get("mode", "face-stabilized")),
        reason=str(crop_data.get("reason", "Reuse verified crop")),
        aspect_ratio=str(crop_data.get("aspect_ratio", "9:16")),
        two_person_frames=int(crop_data.get("two_person_frames", 0)),
    )
    render_vertical_clip(source, out, start, end - start, "1080x1920", 30, ass, crop)
    print(json.dumps({"rank": rank, "output": str(out), "ass": str(ass), "subtitle": subtitle, "duration": end - start}))
