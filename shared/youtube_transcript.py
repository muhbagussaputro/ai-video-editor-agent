from __future__ import annotations

import json
import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget


class YouTubeTranscriptRateLimited(RuntimeError):
    """YouTube temporarily rejected caption retrieval; never replace it with ASR."""


def _is_rate_limited(exc: Exception | None) -> bool:
    return bool(exc) and ("429" in str(exc) or "too many requests" in str(exc).lower())


@dataclass(frozen=True)
class YouTubeTranscriptResult:
    video_id: str
    language: str
    segments: list[dict[str, Any]]
    full_text: str
    source: str = "youtube-transcript-api"


def extract_video_id(url_or_id: str) -> str:
    value = (url_or_id or "").strip()
    patterns = [
        r"(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})",
        r"\[([a-zA-Z0-9_-]{11})\]",
        r"\b([a-zA-Z0-9_-]{11})\b",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return value


def _normalize_result(video_id: str, fetched: Any, preferred: list[str]) -> YouTubeTranscriptResult:
    language = getattr(fetched, "language_code", None) or (preferred[0] if preferred else "")
    segments: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for item in fetched:
        text = str(getattr(item, "text", "")).strip()
        start = float(getattr(item, "start", 0.0))
        duration = float(getattr(item, "duration", 0.0))
        end = max(start, start + duration)
        if text:
            text_parts.append(text)
            segments.append({"text": text, "start": start, "end": end, "duration": duration, "words": []})
    return YouTubeTranscriptResult(video_id, language, segments, " ".join(text_parts).strip())


def _normalize_json3_events(video_id: str, language: str, payload: dict[str, Any]) -> YouTubeTranscriptResult:
    segments: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or event.get("tStartMs") is None or not isinstance(event.get("segs"), list):
            continue
        text = "".join(str(seg.get("utf8", "")) for seg in event["segs"] if isinstance(seg, dict)).replace("\n", " ").strip()
        if not text:
            continue
        start = float(event["tStartMs"]) / 1000.0
        duration = float(event.get("dDurationMs") or 0.0) / 1000.0
        text_parts.append(text)
        segments.append({"text": text, "start": start, "end": max(start, start + duration), "duration": duration, "words": []})
    if not segments:
        raise RuntimeError("yt-dlp subtitle file contained no usable transcript segments")
    return YouTubeTranscriptResult(video_id, language, segments, " ".join(text_parts).strip(), "yt-dlp-auto-sub")


def _fetch_via_ytdlp(url_or_id: str, video_id: str, preferred: list[str], last_error: Exception | None, cookies_from_browser: str = "", proxy: str = "") -> YouTubeTranscriptResult:
    """Fetch one preferred auto-caption language with browser-like request settings.

    A 429 is terminal for this attempt: trying another language immediately hits the
    same timedtext endpoint and makes the rate-limit worse.
    """
    with tempfile.TemporaryDirectory(prefix="yt-sub-") as tmpdir:
        tmp_path = Path(tmpdir)
        for code in preferred or ["id", "en"]:
            candidate = tmp_path / f"{video_id}.{code}.json3"
            opts: dict[str, Any] = {
                "skip_download": True,
                # Subtitle retrieval must not inherit a source-quality selector.
                # `best` only resolves page metadata; no media is downloaded.
                "format": "best",
                "writeautomaticsub": True,
                "writesubtitles": True,
                "subtitleslangs": [code],
                "subtitlesformat": "json3",
                "outtmpl": str(tmp_path / "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                # Use a target present in the modern yt-dlp/curl-cffi runtime registry.
                # CLI display: “Chrome-131 / Android-14”.
                "impersonate": ImpersonateTarget(client="chrome", version="131", os="android", os_version="14"),
            }
            if cookies_from_browser:
                opts["cookiesfrombrowser"] = (cookies_from_browser,)
            if proxy:
                opts["proxy"] = proxy
            latest_error = last_error
            for attempt in range(3):
                try:
                    with YoutubeDL(opts) as ydl:
                        ydl.download([url_or_id])
                    latest_error = None
                    break
                except Exception as exc:
                    latest_error = exc
                    if not _is_rate_limited(exc) or attempt == 2:
                        break
                    time.sleep((15 * (2 ** attempt)) + random.uniform(0, 3))
            if candidate.exists():
                return _normalize_json3_events(video_id, code, json.loads(candidate.read_text(encoding="utf-8")))
            if _is_rate_limited(latest_error):
                raise YouTubeTranscriptRateLimited(str(latest_error))
            last_error = latest_error
    raise RuntimeError(str(last_error) if last_error else "failed to fetch YouTube transcript")


def _cache_path(cache_dir: Path | None, video_id: str) -> Path | None:
    return cache_dir / "youtube-transcripts" / f"{video_id}.json" if cache_dir else None


def fetch_youtube_transcript(url_or_id: str, languages: list[str] | None = None, *, cookies_from_browser: str = "", cache_dir: Path | None = None, proxy: str = "") -> YouTubeTranscriptResult:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("youtube-transcript-api not installed") from exc

    video_id = extract_video_id(url_or_id)
    if not video_id:
        raise RuntimeError("invalid YouTube URL or video ID")
    preferred = [lang.strip() for lang in (languages or []) if lang and lang.strip()]
    cached = _cache_path(cache_dir, video_id)
    if cached and cached.exists():
        payload = json.loads(cached.read_text(encoding="utf-8"))
        segments = payload.get("segments")
        if isinstance(segments, list) and segments:
            return YouTubeTranscriptResult(video_id, str(payload.get("language") or ""), segments, str(payload.get("full_text") or ""), "youtube-transcript-cache")

    api = YouTubeTranscriptApi()
    last_error: Exception | None = None
    result: YouTubeTranscriptResult | None = None
    if preferred:
        try:
            for code in preferred:
                transcript_list = api.list(video_id)
                for transcript in transcript_list:
                    if getattr(transcript, "language_code", "") == code:
                        result = _normalize_result(video_id, transcript.fetch(), [code])
                        break
                if result:
                    break
        except Exception as exc:
            last_error = exc
    if result is None:
        try:
            result = _normalize_result(video_id, api.fetch(video_id), preferred)
        except Exception as exc:
            last_error = exc
            result = _fetch_via_ytdlp(url_or_id, video_id, preferred, last_error, cookies_from_browser, proxy)
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"language": result.language, "segments": result.segments, "full_text": result.full_text}, ensure_ascii=False), encoding="utf-8")
    return result
