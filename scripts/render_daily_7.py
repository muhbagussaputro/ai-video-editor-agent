from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EDLS = json.loads((ROOT / "edl/daily_7_edls.json").read_text())["videos"]
RAW = ROOT / "assets/source-footage/raw"
OUT = ROOT / "renders/daily_7"
OUT.mkdir(parents=True, exist_ok=True)

# ponytail: one-source cuts only; upgrade to multi-source EDL compositor when story needs cutaways.
def ass_time(seconds: float) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"

def render(item: dict) -> None:
    duration = round(item["out"] - item["in"], 3)
    stem = f"{item['rank']:02d}_{item['id']}"
    ass = OUT / f"{stem}.ass"
    mp4 = OUT / f"{stem}.mp4"
    hook_end = min(2.4, duration)
    tag_start = max(0.0, duration - 3.0)
    ass.write_text(f'''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,DejaVu Sans Bold,62,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,8,1,8,90,90,92,1
Style: Tag,DejaVu Sans Bold,34,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,4,1,2,80,80,470,1
Style: Benefit,DejaVu Sans Bold,48,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,7,0,8,100,100,150,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 3,0:00:00.00,{ass_time(hook_end)},Hook,,0,0,0,,{item['hook']}
Dialogue: 2,{ass_time(max(2.4, duration-5.0))},{ass_time(duration)},Benefit,,0,0,0,,PULSA & TOKEN PLN\\NPASTI MURAH
Dialogue: 4,{ass_time(tag_start)},{ass_time(duration)},Tag,,0,0,0,,#ShopeePayPastiMurah
''', encoding="utf-8")
    source = RAW / item["source"]
    escaped_ass = str(ass).replace("'", r"\'").replace(":", r"\:")
    fg = "scale=1080:608:force_original_aspect_ratio=decrease" if "1280" in subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width","-of","default=nw=1:nk=1",str(source)],text=True) else "scale=900:1600:force_original_aspect_ratio=decrease"
    graph=(f"[0:v]trim=start={item['in']}:duration={duration},setpts=PTS-STARTPTS,split=2[b][f];"
           f"[b]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10,eq=brightness=-0.22:saturation=0.70[bg];"
           f"[f]{fg},setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles='{escaped_ass}'[v];"
           f"[0:a]atrim=start={item['in']}:duration={duration},asetpts=PTS-STARTPTS,highpass=f=80,equalizer=f=3000:width_type=h:width=200:g=4,loudnorm=I=-14:TP=-1:LRA=11,aformat=channel_layouts=stereo,aresample=async=1:first_pts=0[a]")
    subprocess.run(["ffmpeg","-y","-v","error","-hwaccel","none","-i",str(source),"-filter_complex",graph,"-map","[v]","-map","[a]","-r","30","-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","128k","-movflags","+faststart",str(mp4)],check=True)
    print(mp4, flush=True)

for edl in EDLS:
    render(edl)
