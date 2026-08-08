#!/usr/bin/env python3
"""Create a 10s proof: each row grows word-by-word, three persistent rows per batch."""
from __future__ import annotations

import re
from pathlib import Path

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
VIDEO_DIR = Path("/data/videos")
SOURCE_ASS = VIDEO_DIR / f"{JOB}.one-word-stack-10s.ass"
DEST_ASS = VIDEO_DIR / f"{JOB}.three-row-cumulative-10s.ass"
KEYWORDS = {"investasi", "judi", "bola", "bisnis", "bakar", "miliar", "utang", "aset", "koin", "500", "garuda", "gagal", "hedge", "fund"}
DIALOGUE = re.compile(r"^Dialogue: \d+,([^,]+),([^,]+),([^,]+),[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,(.*)$")
TAG = re.compile(r"\{[^}]*\}")
ROWS = 3
WORDS_PER_ROW = 3


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


def coloured(tokens: list[str]) -> str:
    return " ".join(
        (r"{\1c&H0000D7FF}" if keyword(token) else r"{\1c&H00FFFFFF}") + token.upper()
        for token in tokens
    )


original = SOURCE_ASS.read_text(encoding="utf-8")
words: list[tuple[float, float, str]] = []
for line in original.splitlines():
    match = DIALOGUE.match(line)
    if not match or match.group(3) != "Stack":
        continue
    start, end, text = seconds(match.group(1)), seconds(match.group(2)), plain(match.group(4))
    if start < 10.0 and end - start > 0.07 and text:
        words.append((start, end, text))

# Source proof is already serialized word-by-word. Ensure no accidental duplicates.
unique: list[tuple[float, float, str]] = []
seen: set[tuple[int, int, str]] = set()
for item in words:
    key = (round(item[0] * 100), round(item[1] * 100), item[2].lower())
    if key not in seen:
        unique.append(item)
        seen.add(key)

kept = [
    line for line in original.splitlines()
    if not (line.startswith("Dialogue:") and ",Stack," in line)
    and not line.startswith("Dialogue: 0,")
]

# A batch = 3 rows x 3 words. A row keeps its completed phrase visible while rows below grow.
batch_size = ROWS * WORDS_PER_ROW
for batch_start in range(0, len(unique), batch_size):
    batch = unique[batch_start:batch_start + batch_size]
    batch_end = min(10.0, batch[-1][1])
    for index, (start, _end, word) in enumerate(batch):
        row = index // WORDS_PER_ROW
        within_row = index % WORDS_PER_ROW
        row_start = row * WORDS_PER_ROW
        row_tokens = [entry[2] for entry in batch[row_start:row_start + within_row + 1]]
        y = 1130 + row * 102
        ass = (
            rf"{{\an1\pos(105,{y})\fs62\b1\bord8\3c&H00111111\shad0"
            r"\fscx100\fscy100\t(0,120,\fscx106\fscy106)\t(120,220,\fscx100\fscy100)}"
            + coloured(row_tokens)
        )
        kept.append(f"Dialogue: 1,{timestamp(start)},{timestamp(batch_end)},ThreeRow,,0,0,0,,{ass}")

for index, line in enumerate(kept):
    if line.startswith("Style: Hook,"):
        kept.insert(index + 1, "Style: ThreeRow,Montserrat ExtraBold,62,&H00FFFFFF,&H00FFFFFF,&H00111111,&H00000000,1,0,0,0,100,100,0,0,1,8,0,1,0,0,0,1")
        break
DEST_ASS.write_text("\n".join(kept) + "\n", encoding="utf-8")
print(DEST_ASS)
