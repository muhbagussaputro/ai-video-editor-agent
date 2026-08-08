#!/usr/bin/env python3
"""Create a 10s proof: continuous transcript fills up to 3 wrapped lines, then resets."""
from __future__ import annotations

import re
from pathlib import Path

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
VIDEO_DIR = Path("/data/videos")
# Original captions include full 45s timing. Split their short phrase cues into
# deterministic word timings so this proof can run beyond the previous 10 seconds.
SOURCE_ASS = VIDEO_DIR / f"{JOB}.ass"
DEST_ASS = VIDEO_DIR / f"{JOB}.continuous-three-lines-20s.ass"
SAMPLE_DURATION = 20.0
MAX_CHARS = 24  # safe width at 1080x1920 with 62px Montserrat ExtraBold
MAX_LINES = 3
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


def append_word(lines: list[list[str]], word: str) -> list[list[str]] | None:
    """Add word to current visual block; return None only if it needs line four."""
    candidate = [line[:] for line in lines]
    if not candidate:
        return [[word]]
    current = candidate[-1]
    prospective = " ".join(current + [word])
    if len(prospective) <= MAX_CHARS:
        current.append(word)
        return candidate
    if len(candidate) < MAX_LINES:
        candidate.append([word])
        return candidate
    return None


def rendered_block(lines: list[list[str]]) -> str:
    out: list[str] = []
    for row in lines:
        tokens: list[str] = []
        for word in row:
            colour = r"{\1c&H0000D7FF}" if keyword(word) else r"{\1c&H00FFFFFF}"
            tokens.append(colour + word.upper())
        out.append(" ".join(tokens))
    return r"\N".join(out)


original = SOURCE_ASS.read_text(encoding="utf-8")
words: list[tuple[float, float, str]] = []
for line in original.splitlines():
    match = DIALOGUE.match(line)
    if not match or match.group(3) != "Default":
        continue
    start, end, text = seconds(match.group(1)), seconds(match.group(2)), plain(match.group(4))
    tokens = [token for token in text.split() if not re.fullmatch(r"[A-Za-z]", token)]
    if start >= SAMPLE_DURATION or end - start <= 0.07 or not tokens:
        continue
    # Phrase timings from native captions become deterministic token timings.
    total_chars = sum(max(1, len(token)) for token in tokens)
    cursor = start
    for index, token in enumerate(tokens):
        if index == len(tokens) - 1:
            token_end = end
        else:
            token_end = cursor + (end - start) * max(1, len(token)) / total_chars
        words.append((cursor, token_end, token))
        cursor = token_end

unique: list[tuple[float, float, str]] = []
seen: set[tuple[int, int, str]] = set()
for item in words:
    key = (round(item[0] * 100), round(item[1] * 100), item[2].lower())
    if key not in seen:
        unique.append(item)
        seen.add(key)

# Determine each snapshot first so the previous full 3-line state persists until reset.
snapshots: list[tuple[float, list[list[str]]]] = []
block: list[list[str]] = []
for start, _end, word in unique:
    updated = append_word(block, word)
    if updated is None:
        block = [[word]]  # reset only because adding word would require line four
    else:
        block = updated
    snapshots.append((start, block))

kept = [
    line for line in original.splitlines()
    if not (line.startswith("Dialogue:") and ",Stack," in line)
    and not line.startswith("Dialogue: 0,")
]
for index, (start, block) in enumerate(snapshots):
    end = min(SAMPLE_DURATION, snapshots[index + 1][0] if index + 1 < len(snapshots) else SAMPLE_DURATION)
    if end <= start:
        continue
    ass = (
        r"{\an1\pos(105,1125)\fs62\b1\bord8\3c&H00111111\shad0"
        r"\fscx100\fscy100\t(0,120,\fscx105\fscy105)\t(120,220,\fscx100\fscy100)}"
        + rendered_block(block)
    )
    kept.append(f"Dialogue: 1,{timestamp(start)},{timestamp(end)},Continuous,,0,0,0,,{ass}")

for index, line in enumerate(kept):
    if line.startswith("Style: Hook,"):
        kept.insert(index + 1, "Style: Continuous,Montserrat ExtraBold,62,&H00FFFFFF,&H00FFFFFF,&H00111111,&H00000000,1,0,0,0,100,100,0,0,1,8,0,1,0,0,0,1")
        break
DEST_ASS.write_text("\n".join(kept) + "\n", encoding="utf-8")
print(DEST_ASS)
print(f"snapshots={len(snapshots)} max_chars={MAX_CHARS} max_lines={MAX_LINES}")
