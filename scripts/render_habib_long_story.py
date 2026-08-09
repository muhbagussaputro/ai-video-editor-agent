from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "assets/source-footage/raw/habib-jafar-iklan-shopeepay.mkv"
B = ROOT / "assets/source-footage/raw/habib-jafar-pantun-hari-ini-shopee.mkv"
OUT = ROOT / "renders/habib_shopeepay_long_story.mp4"
ASS = ROOT / "renders/habib_shopeepay_long_story.ass"
OUT.parent.mkdir(exist_ok=True)

ASS.write_text(r'''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,DejaVu Sans Bold,62,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,8,1,8,90,90,92,1
Style: Tag,DejaVu Sans Bold,34,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,4,1,2,80,80,700,1
Style: Reset,DejaVu Sans Bold,54,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,7,0,8,100,100,150,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 3,0:00:00.00,0:00:02.40,Hook,,0,0,0,,TOKEN PLN + PULSA\NKOK SAMA-SAMA MAHAL?
Dialogue: 2,0:00:19.94,0:00:22.60,Reset,,0,0,0,,TOKEN PLN MAU HABIS?\NDENGERIN PANTUN INI.
Dialogue: 4,0:00:37.80,0:00:40.80,Tag,,0,0,0,,#ShopeePayPastiMurah
''', encoding="utf-8")

e = str(ASS).replace("'", r"\'").replace(":", r"\:")
graph = (
    "[0:v]trim=start=1.71:duration=19.94,setpts=PTS-STARTPTS,split=2[ab][af];"
    "[ab]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10,eq=brightness=-0.22:saturation=.70[abg];"
    "[af]scale=1080:608:force_original_aspect_ratio=decrease[afg];"
    "[abg][afg]overlay=0:656,setsar=1[v0];"
    f"[0:a]atrim=start=1.71:duration=19.94,asetpts=PTS-STARTPTS[a0];"
    "[1:v]trim=start=18.34:duration=20.86,setpts=PTS-STARTPTS,scale=900:1600:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih):color=black,setsar=1[v1];"
    "[1:a]atrim=start=18.34:duration=20.86,asetpts=PTS-STARTPTS[a1];"
    "[v0][a0][v1][a1]concat=n=2:v=1:a=1[cv][ca];"
    f"[cv]subtitles='{e}'[v];"
    "[ca]highpass=f=80,equalizer=f=3000:width_type=h:width=200:g=4,loudnorm=I=-14:TP=-1:LRA=11,aformat=channel_layouts=stereo,aresample=async=1:first_pts=0[a]"
)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(A), "-i", str(B), "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(OUT)], check=True)
print(OUT)
