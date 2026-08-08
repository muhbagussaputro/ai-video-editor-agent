#!/usr/bin/env python3
"""Render progressive three-row caption variants for an existing clip job."""
from __future__ import annotations

import re
from pathlib import Path

JOB = "9f8d3aa64a3f4cf28546c4c4d2ba2797"
VIDEO_DIR = Path("/data/videos")
KEYWORDS = {"investasi", "judi", "bola", "bisnis", "bakar", "miliar", "utang", "aset", "koin", "500", "garuda", "gagal", "hedge", "fund"}
DIALOGUE = re.compile(r"^Dialogue: \d+,([^,]+),([^,]+),([^,]+),[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,(.*)$")
TAG = re.compile(r"\{[^}]*\}")


def to_seconds(value: str) -> float:
    hour, minute, second = value.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(second)


def ts(value: float) -> str:
    hours, remaining = divmod(max(0.0, value), 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:05.2f}"


def plain(text: str) -> str:
    return TAG.sub("", text).replace(r"\N", " ").strip()


def is_keyword(text: str) -> bool:
    tokens = {re.sub(r"[^a-z0-9]+", "", item.lower()) for item in text.split()}
    return bool(tokens & KEYWORDS) or any(token.isdigit() for token in tokens)


def make_ass(source: Path, destination: Path) -> None:
    original = source.read_text(encoding="utf-8")
    phrases: list[tuple[float, float, str]] = []
    for line in original.splitlines():
        match = DIALOGUE.match(line)
        if not match or match.group(3) != "Default":
            continue
        start, end = to_seconds(match.group(1)), to_seconds(match.group(2))
        text = plain(match.group(4))
        if end - start > 0.07 and text:
            phrases.append((start, end, text))
    # Remove exact timing/text duplicates produced by overlapping auto-sub events.
    unique: list[tuple[float, float, str]] = []
    seen: set[tuple[int, int, str]] = set()
    for start, end, text in phrases:
        key = (round(start * 100), round(end * 100), text)
        if key not in seen:
            unique.append((start, end, text))
            seen.add(key)

    kept = [line for line in original.splitlines() if not line.startswith("Dialogue: 0,")]
    for batch_start in range(0, len(unique), 3):
        batch = unique[batch_start:batch_start + 3]
        batch_end = batch[-1][1]
        for row, (start, _end, text) in enumerate(batch):
            y = 1165 + row * 120
            color = "&H0000D7FF" if is_keyword(text) else "&H00FFFFFF"
            font_size = 70 if is_keyword(text) else 65
            border = 10 if is_keyword(text) else 9
            ass = (
                f"{{\\an1\\move(-90,{y},145,{y},0,180)"
                f"\\fscx118\\fscy118\\t(0,160,\\fscx100\\fscy100)"
                f"\\fs{font_size}\\1c{color}\\b1\\bord{border}\\3c&H00111111\\shad0}}"
                f"{text.upper()}"
            )
            kept.append(f"Dialogue: 1,{ts(start)},{ts(batch_end)},Stack,,0,0,0,,{ass}")
    # Add a named stack style after the Default style for artifact readability.
    for index, line in enumerate(kept):
        if line.startswith("Style: Default,"):
            kept.insert(index + 1, "Style: Stack,Montserrat ExtraBold,65,&H00FFFFFF,&H00FFFFFF,&H00111111,&H00000000,1,0,0,0,100,100,1,0,1,9,0,1,0,0,0,1")
            break
    destination.write_text("\n".join(kept) + "\n", encoding="utf-8")


for rank in range(1, 6):
    suffix = "" if rank == 1 else f"_highlight_{rank:02d}"
    source = VIDEO_DIR / f"{JOB}{suffix}.ass"
    destination = VIDEO_DIR / f"{JOB}{suffix}.progressive-stack.ass"
    make_ass(source, destination)
    print(destination)
