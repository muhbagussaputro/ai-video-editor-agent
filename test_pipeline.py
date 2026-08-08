import re

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "r") as f:
    text = f.read()

new_render = """
def render_vertical_clip(
    input_path: Path,
    output_path: Path,
    start: float,
    duration: float,
    target_resolution: str = "1080x1920",
    fps: int = 30,
    subtitles_path: Path | None = None,
    crop_analysis: CropAnalysis | None = None,
) -> None:
    width, height = (int(part) for part in target_resolution.split("x", 1))
    
    # Adaptive layout
    if crop_analysis is not None and crop_analysis.aspect_ratio == "3:4":
        vf = "crop=in_h*4/3:in_h,scale=1080:810,pad=1080:1920:0:250:color=black"
    elif crop_analysis is not None:
        crop_x = crop_analysis.crop_x
        crop_y = crop_analysis.crop_y
        crop_w = crop_analysis.crop_w
        crop_h = crop_analysis.crop_h
        vf = f"scale={crop_w}:{crop_h}:force_original_aspect_ratio=increase,crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
    else:
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        
    if subtitles_path is not None:
        vf = f"{vf},subtitles=filename='{_escape_ffmpeg_filter_path(subtitles_path)}'"
"""

text = re.sub(
    r'def render_vertical_clip\([^:]+:\s*None\n\) -> None:\n.*?if subtitles_path is not None:\n        vf = f"\{vf\},subtitles=filename=\'\{_escape_ffmpeg_filter_path\(subtitles_path\)\}\'"',
    new_render.strip(),
    text,
    flags=re.DOTALL
)

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "w") as f:
    f.write(text)
