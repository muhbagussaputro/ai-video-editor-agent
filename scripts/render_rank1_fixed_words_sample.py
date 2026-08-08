#!/usr/bin/env python3
"""15s proof: every word has a fixed coordinate; only incoming word pops."""
import json
import re
from pathlib import Path

from PIL import ImageFont
from shared.pipeline import CropAnalysis, render_vertical_clip

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
START, DURATION = 3062.599, 15.0
END = START + DURATION
HOOK = "Tes Masuk Hedge Fund: 99% Orang Gagal Jawab Pertanyaan Koin Ini"
VIDEO = Path("/data/videos")
base = Path("/data/work") / JOB
source = next(base.glob("*.mkv"))
out = VIDEO / f"{JOB}.fixed-word-only-15s.mp4"
ass_path = out.with_suffix(".ass")

# Pixel layout, deliberately independent per word: prior captions never reflow.
X0, Y0 = 108, 1125
# Compact transcript rhythm: gap is measured around glyph/outline edges, not
# an artificial wide grid. Rows remain close enough to read as one block.
FONT, LINE_HEIGHT, MAX_X, SPACE = 62, 76, 920, 7
FONT_PATH = "/usr/share/fonts/opentype/montserrat/Montserrat-ExtraBold.otf"
KEYWORDS = {"500", "100", "1024", "garuda", "probabilitas", "hedge", "fund", "gagal"}


def ts(value: float) -> str:
    h, rest = divmod(max(0, value), 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


MEASURE_FONT = ImageFont.truetype(FONT_PATH, FONT)


def width(word: str) -> int:
    # Actual Montserrat glyph width: compact natural flow, no invisible slots.
    left, _top, right, _bottom = MEASURE_FONT.getbbox(word.upper(), stroke_width=8)
    return right - left


def keyword(word: str) -> bool:
    token = re.sub(r"[^a-z0-9]+", "", word.lower())
    return token in KEYWORDS or token.isdigit()

raw = json.loads((base / "transcript.json").read_text(encoding="utf-8"))["segments"]
tokens: list[str] = []
for segment in raw:
    if float(segment["end"]) <= START or float(segment["start"]) >= END:
        continue
    tokens += [word for word in str(segment.get("text", "")).split() if not re.fullmatch(r"[A-Za-z]", word)]

# Synthetic timing only for this proof: preserves native word order but avoids
# broken overlapping 50ms auto-sub timing.
weight_total = sum(max(1, len(word)) for word in tokens)
cursor = START
word_events: list[dict] = []
x, y, row = X0, Y0, 0
batch = 0
for i, word in enumerate(tokens):
    duration = DURATION * max(1, len(word)) / weight_total
    word_end = END if i == len(tokens) - 1 else cursor + duration
    w = width(word.upper())
    if x + w > MAX_X:
        if row < 2:
            row += 1
            x, y = X0, Y0 + row * LINE_HEIGHT
        else:
            batch += 1
            row, x, y = 0, X0, Y0
    # Keep each completed word at its normal left edge. No reserved pop slot.
    word_events.append({"word": word, "start": cursor, "end": word_end, "x": x, "y": y, "batch": batch})
    x += w + SPACE
    cursor = word_end

# Each old word remains a separate event at its original position. It never moves.
# End every word only at its batch reset, not upon next word arrival.
for event in word_events:
    later = [item["start"] for item in word_events if item["batch"] > event["batch"]]
    event["visible_until"] = min(later) if later else END

lines = [
    "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
    "[V4+ Styles]",
    "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
    "Style: Hook,Montserrat ExtraBold,62,&H00A7F3FF,&H00A7F3FF,&H00111111,&H50000000,1,0,0,0,100,100,0,0,1,4,0,8,130,130,173,1",
    "Style: FixedWord,Montserrat ExtraBold,62,&H00FFFFFF,&H00FFFFFF,&H00111111,&H00000000,1,0,0,0,100,100,0,0,1,8,0,1,0,0,0,1", "",
    "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    f"Dialogue: 5,0:00:00.00,0:00:07.00,Hook,,0,0,0,,Tes Masuk Hedge Fund: 99%\\NOrang Gagal Jawab Pertanyaan\\NKoin Ini",
]
for event in word_events:
    colour = "&H0000D7FF" if keyword(event["word"]) else "&H00FFFFFF"
    # This is the only moving glyph. Once it settles, it stays at this same pos.
    text = (
        f"{{\\an1\\move({event['x']},{event['y'] + 16},{event['x']},{event['y']},0,130)\\fs{FONT}\\1c{colour}\\b1\\bord8\\3c&H00111111\\shad0"
        r"\alpha&H22&\t(0,130,\alpha&H00&)}"
        + event["word"].upper()
    )
    lines.append(f"Dialogue: 1,{ts(event['start']-START)},{ts(event['visible_until']-START)},FixedWord,,0,0,0,,{text}")
ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

crop = CropAnalysis(1240, 0, 1080, 1920, 44, 3, 45, "face-stabilized", "Reuse verified rank-1 crop", "9:16", 0)
render_vertical_clip(source, out, START, DURATION, "1080x1920", 30, ass_path, crop)
print(json.dumps({"output": str(out), "ass": str(ass_path), "words": len(word_events), "batches": batch + 1, "mode": "fixed-position-active-word-only"}))
