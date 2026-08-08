#!/usr/bin/env python3
"""15s proof: portrait speaker <-> full 16:9 slide using zoom transitions."""
import json
import subprocess
from pathlib import Path

from shared.pipeline import build_subtitle_ass

SOURCE_JOB = "26b9eea7dae24cfda9dc38f40d8eabde"
START, END = 304.0, 319.0
FACE_TO_SLIDE, SLIDE_TO_FACE = 311.0, 317.0
source = next((Path("/data/work") / SOURCE_JOB).glob("*.mkv"))
transcript = json.loads(((Path("/data/work") / SOURCE_JOB / "transcript.json").read_text(encoding="utf-8")))['segments']
out = Path("/data/videos/e189716e8086452bb7f710d93151cc9c.adaptive-slide-upper-caption-below-topdown-15s.mp4")
ass = out.with_suffix(".ass")
build_subtitle_ass(transcript, START, END, ass, "1080x1920", "", "")

# In the presentation interval the complete 16:9 slide is deliberately raised
# to y=250..858. Re-anchor only overlapping transcript events just below it,
# leaving speaker-scene captions at the approved y=1284 position.
def _ass_seconds(value: str) -> float:
    hour, minute, second = value.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(second)


lines = []
for line in ass.read_text(encoding="utf-8").splitlines():
    if line.startswith("Dialogue:"):
        fields = line.split(",", 9)
        if len(fields) == 10:
            cue_start, cue_end = _ass_seconds(fields[1]), _ass_seconds(fields[2])
            # Relative sample slide span is 7.0..13.0 seconds.
            if cue_start < 13.0 and cue_end > 7.0:
                fields[9] = fields[9].replace(r"\pos(108,1284)", r"\pos(108,1030)")
                line = ",".join(fields)
    lines.append(line)
ass.write_text("\n".join(lines) + "\n", encoding="utf-8")

# Portrait speaking scenes use a full-height center crop. Slide scenes retain the
# entire 16:9 composition on the portrait canvas. xfade 'zoomin' bridges them.
fc = (
    "[0:v]trim=start=304:end=311,setpts=PTS-STARTPTS,fps=30,settb=AVTB,"
    "scale=3414:1920,crop=1080:1920:1167:0,setsar=1,format=yuv420p[face_a];"
    "[0:v]trim=start=311:end=317,setpts=PTS-STARTPTS,fps=30,settb=AVTB,"
    "scale=1080:608,pad=1080:1920:0:250:color=black,setsar=1,format=yuv420p[slide];"
    "[0:v]trim=start=317:end=319,setpts=PTS-STARTPTS,fps=30,settb=AVTB,"
    "scale=3414:1920,crop=1080:1920:1167:0,setsar=1,format=yuv420p[face_b];"
    # Change exactly with the detected scene boundary. 150 ms keeps a subtle
    # zoom feel while avoiding the delayed/slow transition of the first proof.
    "[face_a][slide]xfade=transition=zoomin:duration=0.15:offset=6.85[m1];"
    "[m1][face_b]xfade=transition=zoomin:duration=0.15:offset=12.70,"
    f"subtitles=filename='{ass}'[v]"
)
cmd = [
    "ffmpeg", "-y", "-i", str(source), "-filter_complex", fc,
    "-map", "[v]", "-map", "0:a?", "-t", "15", "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
print(json.dumps({"output": str(out), "ass": str(ass), "timeline": {"face": "304-311", "slide": "311-317", "face_return": "317-319", "micro_zoom_transitions": [310.85, 316.85], "duration_seconds": 0.15}}))
