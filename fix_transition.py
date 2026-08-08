import re

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "r") as f:
    content = f.read()

# Add adaptive presentation / zoom logic into render_vertical_clip
import json
try:
    with open("/home/bismillah/ai-video-clipper-vps/config/adaptive-layout.json") as f:
        adaptive = json.load(f)
        if adaptive.get("adaptive_scene_switching", {}).get("enabled"):
            print("Layout JSON loaded, modifying pipeline.py to handle transitions...")
except:
    pass

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
    
    # Adaptive layout parsing
    fc_parts = []
    
    # Very basic static crop if face mode, but let's implement adaptive slide handling here.
    if crop_analysis is not None and crop_analysis.aspect_ratio == "3:4" and crop_analysis.mode == "presentation":
        # Presentation mode implementation based on adaptive layout (16:9 -> 4:3)
        # Assuming original width is usually 1920x1080 -> crop to 1440x1080
        # The user's proof script used: crop=in_h*4/3:in_h,scale=1080:810,pad=1080:1920:0:250:color=black
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

content = re.sub(
    r'def render_vertical_clip\([^:]+:\s*None\n\) -> None:\n(?:(?!def ).)*?(?=\n    run\()',
    new_render.strip() + "\n",
    content,
    flags=re.DOTALL
)

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "w") as f:
    f.write(content)
