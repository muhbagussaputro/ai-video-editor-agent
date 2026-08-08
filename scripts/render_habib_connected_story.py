from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/source-footage/raw/habib-jafar-iklan-shopeepay.mkv"
OUT = ROOT / "renders/habib_shopeepay_connected_story.mp4"
ASS = ROOT / "renders/habib_shopeepay_connected_story.ass"
OUT.parent.mkdir(exist_ok=True)
segments = [(1.71, 6.35), (6.83, 11.93), (12.45, 21.65), (22.49, 29.85)]
durations = [round(end - start, 3) for start, end in segments]
total = round(sum(durations), 3)

ASS.write_text(r'''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,DejaVu Sans Bold,62,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,8,1,8,90,90,92,1
Style: Caption,DejaVu Sans Bold,52,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,7,0,2,110,110,560,1
Style: Tag,DejaVu Sans Bold,34,&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,1,0,0,0,100,100,0,0,1,4,1,2,80,80,700,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 3,0:00:00.00,0:00:02.40,Hook,,0,0,0,,KALAU TOKEN + PULSA\NSAMA-SAMA MAHAL?
Dialogue: 2,0:00:00.00,0:00:01.48,Caption,,0,0,0,,YA, MATI LAMPU.
Dialogue: 2,0:00:01.74,0:00:04.64,Caption,,0,0,0,,HARUS BELI TOKEN PLN\NTAPI LUMAYAN MAHAL.
Dialogue: 2,0:00:04.64,0:00:05.80,Caption,,0,0,0,,HALO, HALO.
Dialogue: 2,0:00:05.80,0:00:07.58,Caption,,0,0,0,,MESTI ISI PULSA.
Dialogue: 2,0:00:07.92,0:00:09.04,Caption,,0,0,0,,TAPI KOK MAHAL YA?
Dialogue: 2,0:00:09.04,0:00:11.42,Caption,,0,0,0,,SABAR, IZIN INFO.
Dialogue: 2,0:00:11.42,0:00:14.30,Caption,,0,0,0,,PULSA DAN TOKEN PLN\NPASTI MURAH.
Dialogue: 2,0:00:14.30,0:00:16.42,Caption,,0,0,0,,SHOPEEPAY, TOKEN PLN\NPASTI MURAH.
Dialogue: 2,0:00:16.42,0:00:19.06,Caption,,0,0,0,,SHOPEEPAY, PULSA\NPASTI MURAH.
Dialogue: 2,0:00:19.06,0:00:21.28,Caption,,0,0,0,,DOWNLOAD DAN LOGIN YUK.
Dialogue: 4,0:00:23.30,0:00:26.30,Tag,,0,0,0,,#ShopeePayPastiMurah
''', encoding="utf-8")

# Every audio branch follows its matching video branch. concat produces one coherent story.
parts = []
for index, ((start, _), duration) in enumerate(zip(segments, durations)):
    parts.append(f"[0:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS[v{index}]")
    parts.append(f"[0:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.06,afade=t=out:st={max(0.0,duration-0.06):.3f}:d=0.06[a{index}]")
labels = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
escaped = str(ASS).replace("'", r"\'").replace(":", r"\:")
parts.extend([
    f"{labels}concat=n={len(segments)}:v=1:a=1[cv][ca]",
    "[cv]split=2[b][f]",
    "[b]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10,eq=brightness=-0.22:saturation=0.70[bg]",
    f"[f]scale=1080:608:force_original_aspect_ratio=decrease,setsar=1[fg]",
    f"[bg][fg]overlay=0:340,subtitles='{escaped}'[v]",
    "[ca]highpass=f=80,equalizer=f=3000:width_type=h:width=200:g=4,loudnorm=I=-14:TP=-1:LRA=11,aformat=channel_layouts=stereo,aresample=async=1:first_pts=0[a]",
])
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SOURCE), "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(OUT)], check=True)
print(OUT)
assert abs(total - 26.3) < 0.02
