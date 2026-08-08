from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


# Preserve source quality: request highest available video and audio. 4K wins when offered.
DEFAULT_FORMATS = ["bv*+ba/b"]
DEFAULT_MERGE_FORMAT = "mkv"
DEFAULT_MIN_HEIGHT = 0


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def yt_dlp_command() -> list[str]:
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    return ["yt-dlp"]


def build_command(
    url: str,
    output_dir: Path,
    format_selector: str,
    list_formats: bool,
    cookies_from_browser: str | None,
) -> list[str]:
    base = yt_dlp_command() + [
        "--no-playlist",
        "--format",
        format_selector,
        "--merge-output-format",
        DEFAULT_MERGE_FORMAT,
        "--paths",
        str(output_dir),
        "--impersonate", "Chrome-131:Android-14",
        "--js-runtimes", f"node:{shutil.which('node') or 'node'}",
        # Modern YouTube n-signature challenges need the official EJS solver.
        "--remote-components", "ejs:github",
    ]
    if proxy := os.getenv("YOUTUBE_PROXY", "").strip():
        base.extend(["--proxy", proxy])
    if cookies_from_browser:
        base.extend(["--cookies-from-browser", cookies_from_browser])
    if list_formats:
        base.append("--list-formats")
    base.append(url)
    return base


def probe_resolution(path: Path) -> tuple[int, int] | None:
    probe = run([
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ])
    if probe.returncode != 0:
        return None
    text = probe.stdout.strip()
    if "x" not in text:
        return None
    width, height = text.split("x", 1)
    try:
        return int(width), int(height)
    except ValueError:
        return None


def newest_video_file(paths: Iterable[Path]) -> Path | None:
    candidates = [p for p in paths if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def move_downloaded_file(src_dir: Path, dst_dir: Path) -> Path | None:
    downloaded = newest_video_file(src_dir.iterdir())
    if not downloaded:
        return None
    dst_dir.mkdir(parents=True, exist_ok=True)
    target = dst_dir / downloaded.name
    if target.exists():
        target.unlink()
    shutil.move(str(downloaded), str(target))
    return target


def cleanup_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download YouTube video in best available quality.")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument("-o", "--output-dir", default=".", help="Output directory")
    parser.add_argument("--min-height", type=int, default=DEFAULT_MIN_HEIGHT, help="Fail if downloaded video is below this height")
    parser.add_argument("--list-formats", action="store_true", help="Only list available formats")
    parser.add_argument(
        "--cookies-from-browser",
        default=None,
        help="Optional browser name for yt-dlp cookies, e.g. chrome, chromium, firefox",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.list_formats:
        cmd = build_command(args.url, output_dir, DEFAULT_FORMATS[0], True, args.cookies_from_browser)
        result = run(cmd)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        return result.returncode

    last_error_code = 1
    for attempt_index, format_selector in enumerate(DEFAULT_FORMATS, start=1):
        attempt_dir = output_dir / f".yt-dlp-attempt-{attempt_index}"
        cleanup_dir(attempt_dir)
        attempt_dir.mkdir(parents=True, exist_ok=True)

        cmd = build_command(args.url, attempt_dir, format_selector, False, args.cookies_from_browser)
        result = run(cmd)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        if result.returncode != 0:
            last_error_code = result.returncode
            cleanup_dir(attempt_dir)
            continue

        downloaded = move_downloaded_file(attempt_dir, output_dir)
        cleanup_dir(attempt_dir)
        if not downloaded:
            print("ERROR: Tidak menemukan file video hasil download.", file=sys.stderr)
            last_error_code = 1
            continue

        resolution = probe_resolution(downloaded)
        if not resolution:
            print(f"WARNING: Gagal probe resolusi untuk {downloaded}", file=sys.stderr)
            return 0

        width, height = resolution
        if height < args.min_height:
            print(
                f"WARNING: Download {downloaded.name} hanya {width}x{height}; retry format berikutnya.",
                file=sys.stderr,
            )
            downloaded.unlink(missing_ok=True)
            last_error_code = 2
            continue

        print(f"OK: downloaded {downloaded} at {width}x{height}")
        return 0

    print(
        f"ERROR: Gagal mengambil video minimal {args.min_height}p. "
        "Coba update yt-dlp, pakai cookies browser yang benar, atau gunakan URL/source lain.",
        file=sys.stderr,
    )
    return last_error_code


if __name__ == "__main__":
    raise SystemExit(main())
