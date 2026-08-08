#!/usr/bin/env python3
"""Rank-2 proof: face -> 4:3 slide -> face, with 150ms micro zoom transitions."""
import json
import subprocess
from pathlib import Path
from shared.pipeline import build_subtitle_ass

SOURCE_JOB = '26b9eea7dae24cfda9dc38f40d8eabde'
BASE_START, DURATION = 337.8 + 19.0, 15.0
FACE_TO_SLIDE, SLIDE_TO_FACE = 22.033 - 19.0, 32.2 - 19.0
base = Path('/data/work') / SOURCE_JOB
source = next(base.glob('*.mkv'))
transcript = json.loads((base / 'transcript.json').read_text(encoding='utf-8'))['segments']
out = Path('/data/videos/e189716e8086452bb7f710d93151cc9c_rank02.adaptive-transition-pov-proof-15s.mp4')
ass = out.with_suffix('.ass')

build_subtitle_ass(transcript, BASE_START, BASE_START + DURATION, ass, '1080x1920', '', '')
lines=[]
for line in ass.read_text(encoding='utf-8').splitlines():
    if line.startswith('Dialogue:'):
        fields=line.split(',',9)
        if len(fields)==10:
            def sec(value):
                h,m,s=value.split(':'); return int(h)*3600+int(m)*60+float(s)
            start,end=sec(fields[1]),sec(fields[2])
            fields[9]=fields[9].replace(r'\an1',r'\an7').replace(r'\pos(108,1284)',r'\pos(108,1284)')
            # Any transcript overlapping presentation mode sits tight below 4:3 panel.
            if start < SLIDE_TO_FACE and end > FACE_TO_SLIDE:
                fields[9]=fields[9].replace(r'\pos(108,1284)',r'\pos(108,1080)')
            line=','.join(fields)
    lines.append(line)
pov = (
    'Dialogue: 5,0:00:00.00,0:00:15.00,Default,,0,0,0,,'
    '{\\an8\\pos(540,1540)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5\\3c&H00111111\\shad2}'
    '{\\1c&H00FFFFFF}POV: KAMU MASIH\\N{\\1c&H00B000FF}MEREMEHKAN\\N'
    '{\\1c&H00FFFFFF}NOMINAL {\\1c&H00B000FF}KECIL'
    '{\\r\\fs32\\fnMontserrat SemiBold\\b1\\bord2\\3c&H00111111\\shad1\\1c&H00F0D0FF}\\N@gusaja.com'
)
lines.append(pov)
ass.write_text("\n".join(lines) + "\n", encoding="utf-8")

# Face crop reuse rank-2 verified focus x=1076. Slide is a 4:3 center crop.
fc=(
 f'[0:v]trim=start={BASE_START}:end={BASE_START+FACE_TO_SLIDE},setpts=PTS-STARTPTS,fps=30,settb=AVTB,scale=3414:1920,crop=1080:1920:1076:0,setsar=1,format=yuv420p[f1];'
 f'[0:v]trim=start={BASE_START+FACE_TO_SLIDE}:end={BASE_START+SLIDE_TO_FACE},setpts=PTS-STARTPTS,fps=30,settb=AVTB,crop=1920:1440:320:0,scale=1080:810,pad=1080:1920:0:250:color=black,setsar=1,format=yuv420p[s];'
 f'[0:v]trim=start={BASE_START+SLIDE_TO_FACE}:end={BASE_START+DURATION},setpts=PTS-STARTPTS,fps=30,settb=AVTB,scale=3414:1920,crop=1080:1920:1076:0,setsar=1,format=yuv420p[f2];'
 f'[f1][s]xfade=transition=zoomin:duration=0.15:offset={FACE_TO_SLIDE-0.15:.3f}[m1];'
 # m1 loses 0.15 s at the first xfade; finish the second xfade exactly at slide->face boundary.
 f'[m1][f2]xfade=transition=zoomin:duration=0.15:offset={SLIDE_TO_FACE-0.45:.3f},subtitles=filename=\'{ass}\'[v];'
 f'[0:a]atrim=start={BASE_START}:duration={DURATION},asetpts=PTS-STARTPTS[a]'
)
cmd=['ffmpeg','-y','-i',str(source),'-filter_complex',fc,'-map','[v]','-map','[a]','-t',str(DURATION),'-r','30','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(out)]
subprocess.run(cmd,check=True)
print(json.dumps({'output':str(out),'boundaries_relative':[FACE_TO_SLIDE,SLIDE_TO_FACE],'transition_seconds':0.15}))
