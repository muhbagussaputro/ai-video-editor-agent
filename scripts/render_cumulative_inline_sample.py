#!/usr/bin/env python3
"""Create one 10s proof: words accumulate inline, then reset after 3 words."""
from __future__ import annotations

import re
from pathlib import Path

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
VIDEO_DIR = Path("/data/videos")
# This existing 10s proof already contains serialized one-word timings, unlike
# the original overlapping auto-sub cues. Reuse it only as a timing source.
SOURCE_ASS = VIDEO_DIR / f"{JOB}.one-word-stack-10s.ass"
DEST_ASS = VIDEO_DIR / f"{JOB}.cumulative-inline-10s.ass"
KEYWORDS = {"investasi", "judi", "bola", "bisnis", "bakar", "miliar", "utang", "aset", "koin", "500", "garuda", "gagal", "hedge", "fund"}
DIALOGUE = re.compile(r"^Dialogue: \d+,([^,]+),([^,]+),([^,]+),[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,(.*)$")
TAG = re.compile(r"\{[^}]*\}")


def seconds(value: str) -> float:
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def timestamp(value: float) -> str:
    h, rem = divmod(max(0.0, value), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def plain(text: str) -> str:
    return TAG.sub("", text).replace(r"\N", " ").strip()


def keyword(word: str) -> bool:
    token = re.sub(r"[^a-z0-9]+", "", word.lower())
    return token in KEYWORDS or token.isdigit()


original = SOURCE_ASS.read_text(encoding="utf-8")
words: list[tuple[float, float, str]] = []
for line in original.splitlines():
    match = DIALOGUE.match(line)
    if not match or match.group(3) not in {"Default", "Stack"}:
        continue
    start, end, text = seconds(match.group(1)), seconds(match.group(2)), plain(match.group(4))
    if start >= 10.0 or end - start <= 0.07 or not text:
        continue
    for word in text.split():
        words.append((start, end, word))

# Deduplicate overlap artifacts and preserve ordered, genuinely spoken tokens.
unique: list[tuple[float, float, str]] = []
seen: set[tuple[int, int, str]] = set()
for item in words:
    key = (round(item[0] * 100), round(item[1] * 100), item[2].lower())
    if key not in seen:
        unique.append(item)
        seen.add(key)

# Remove every old spoken-caption event; preserve only hook and add Inline events below.
kept = [
    line for line in original.splitlines()
    if not (line.startswith("Dialogue:") and ",Stack," in line)
    and not line.startswith("Dialogue: 0,")
]
for batch_start in range(0, len(unique), 3):
    batch = unique[batch_start:batch_start + 3]
    batch_end = min(10.0, batch[-1][1])
    cumulative: list[str] = []
    for start, _end, word in batch:
        cumulative.append(word.upper())
        # The full growing phrase remains one inline line: ADA -> ADA KOIN -> ADA KOIN NIH.
        rendered = " ".join(
            (r"{\1c&H0000D7FF}" if keyword(token) else r"{\1c&H00FFFFFF}") + token.upper()
            for token in cumulative
        )
        ass = (
            r"{\an1\pos(105,1245)\fs68\b1\bord9\3c&H00111111\shad0"
            r"\fscx100\fscy100\t(0,130,\fscx106\fscy106)\t(130,230,\fscx100\fscy100)}"
            + rendered
        )
        kept.append(f"Dialogue: 1,{timestamp(start)},{timestamp(batch_end)},Inline,,0,0,0,,{ass}")

for index, line in enumerate(kept):
    if line.startswith("Style: Hook,"):
        kept.insert(index + 1, "Style: Inline,Montserrat ExtraBold,68,&H00FFFFFF,&H00FFFFFF,&H00111111,&H00000000,1,0,0,0,100,100,0,0,1,9,0,1,0,0,0,1")
        break
DEST_ASS.write_text("\n".join(kept) + "\n", encoding="utf-8")
print(DEST_ASS)
