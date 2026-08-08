from __future__ import annotations

from pathlib import Path
import subprocess

from .edl import validate
from .models import EDL


def render(edl: EDL, output_path: Path, allowed_root: Path) -> Path:
    validate(edl, allowed_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    assets = {asset.asset_id: asset for asset in edl.assets}
    width, height = (int(x) for x in edl.target.resolution.split("x", 1))
    parts: list[str] = []
    inputs: list[str] = []
    for index, clip in enumerate(sorted(edl.video, key=lambda x: x.timeline_start)):
        asset = assets[clip.asset_id]
        inputs.extend(["-i", asset.path])
        duration = clip.duration
        # Portrait assets fit directly; landscape assets preserve full frame over a blurred canvas.
        if asset.height >= asset.width:
            visual = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        else:
            visual = (
                f"split=2[b{index}][f{index}];"
                f"[b{index}]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:10,eq=brightness=-0.22:saturation=.70[bg{index}];"
                f"[f{index}]scale={width}:608:force_original_aspect_ratio=decrease[fg{index}];"
                f"[bg{index}][fg{index}]overlay=0:656"
            )
        if "split=2" in visual:
            parts.append(f"[{index}:v]trim=start={clip.source_in}:duration={duration},setpts=PTS-STARTPTS,{visual},setsar=1[v{index}]")
        else:
            parts.append(f"[{index}:v]trim=start={clip.source_in}:duration={duration},setpts=PTS-STARTPTS,{visual},setsar=1[v{index}]")
        parts.append(f"[{index}:a]atrim=start={clip.source_in}:duration={duration},asetpts=PTS-STARTPTS[a{index}]")
    labels = "".join(f"[v{i}][a{i}]" for i in range(len(edl.video)))
    parts.append(f"{labels}concat=n={len(edl.video)}:v=1:a=1[cv][ca]")
    parts.append("[ca]highpass=f=80,equalizer=f=3000:width_type=h:width=200:g=4,loudnorm=I=-14:TP=-1:LRA=11,aformat=channel_layouts=stereo,aresample=async=1:first_pts=0[a]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(parts), "-map", "[cv]", "-map", "[a]", "-r", str(edl.target.fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output_path)], check=True)
    return output_path
