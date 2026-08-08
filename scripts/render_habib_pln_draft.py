from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/source-footage/raw/habib-jafar-iklan-shopeepay.mkv"
ASS = ROOT / "renders/draft_01.ass"
OUT = ROOT / "renders/draft_01.mp4"
START = 1.71
DURATION = 19.94
OUT.parent.mkdir(parents=True, exist_ok=True)

ASS.write_text(r'''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,DejaVu Sans Bold,64,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,8,1,8,90,90,92,1
Style: Caption,DejaVu Sans Bold,54,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,7,0,2,120,120,560,1
Style: Tag,DejaVu Sans Bold,34,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,4,1,2,80,80,470,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 3,0:00:00.00,0:00:02.40,Hook,,0,0,0,,MATI LAMPU, TOKEN\NMALAH MAHAL?
Dialogue: 2,0:00:00.00,0:00:01.48,Caption,,0,0,0,,YA, MATI LAMPU.
Dialogue: 2,0:00:01.74,0:00:04.64,Caption,,0,0,0,,HARUS BELI TOKEN PLN\NTAPI LUMAYAN MAHAL.
Dialogue: 2,0:00:05.12,0:00:06.28,Caption,,0,0,0,,HALO, HALO.
Dialogue: 2,0:00:06.98,0:00:08.76,Caption,,0,0,0,,MESTI ISI PULSA.
Dialogue: 2,0:00:09.10,0:00:10.22,Caption,,0,0,0,,TAPI KOK MAHAL YA?
Dialogue: 2,0:00:10.74,0:00:13.12,Caption,,0,0,0,,SABAR, IZIN INFO.
Dialogue: 2,0:00:13.12,0:00:15.88,Caption,,0,0,0,,PULSA DAN TOKEN PLN\NPASTI MURAH.
Dialogue: 2,0:00:15.88,0:00:17.94,Caption,,0,0,0,,SHOPEEPAY, TOKEN PLN\NPASTI MURAH.
Dialogue: 2,0:00:17.94,0:00:19.94,Caption,,0,0,0,,SHOPEEPAY, PULSA\NPASTI MURAH.
Dialogue: 4,0:00:17.30,0:00:19.94,Tag,,0,0,0,,#ShopeePayPastiMurah
''', encoding="utf-8")

filter_graph = (
    f"[0:v]trim=start={START}:duration={DURATION},setpts=PTS-STARTPTS,split=2[bgsrc][fgsrc];"
    "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
    "boxblur=20:10,eq=brightness=-0.22:saturation=0.70[bg];"
    "[fgsrc]scale=1080:608:force_original_aspect_ratio=decrease,setsar=1[fg];"
    "[bg][fg]overlay=0:340,subtitles='" + str(ASS).replace("'", r"\'").replace(":", r"\:") + "'[v];"
    f"[0:a]atrim=start={START}:duration={DURATION},asetpts=PTS-STARTPTS,"
    "highpass=f=80,equalizer=f=3000:width_type=h:width=200:g=4,"
    "loudnorm=I=-14:TP=-1.0:LRA=11,aformat=channel_layouts=stereo,aresample=async=1:first_pts=0[a]"
)
cmd = [
    "ffmpeg", "-y", "-hwaccel", "none", "-i", str(SOURCE),
    "-filter_complex", filter_graph, "-map", "[v]", "-map", "[a]",
    "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(OUT),
]
subprocess.run(cmd, check=True)
print(OUT)
