from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

try:
    import cv2
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import mediapipe as mp
except Exception:  # pragma: no cover - optional dependency
    mp = None

from shared.router_client import RouterClient, RouterClientError
from shared.settings import settings


@dataclass
class Segment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TranscriptWord:
    start: float
    end: float
    word: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class HighlightSelection:
    start: float
    end: float
    score: float
    reason: str
    quote: str
    mode: str
    hook_text: str = ""
    clipper_style: str = ""
    style_reason: str = ""
    editing_notes: str = ""
    recommended_bgm: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class HighlightCandidate:
    selection: HighlightSelection
    subtitles_path: Path | None = None
    subtitle_info: dict[str, Any] | None = None
    crop_info: CropAnalysis | None = None
    output_path: Path | None = None


@dataclass
class CropAnalysis:
    crop_x: int
    crop_y: int
    crop_w: int
    crop_h: int
    face_hits: int
    scene_cuts: int
    samples: int
    mode: str
    reason: str
    aspect_ratio: str = "9:16"
    two_person_frames: int = 0



def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, capture_output=True)



def probe_duration(path: Path) -> float:
    result = run([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    return float(result.stdout.strip())



def extract_audio_track(input_path: Path, output_path: Path) -> None:
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ])


def _build_crop_proxy(input_path: Path, start: float, duration: float) -> Path | None:
    proxy_path = input_path.parent / f"{input_path.stem}.crop-proxy.mp4"
    clip_duration = max(1.0, float(duration))
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ss",
        str(max(0.0, start)),
        "-t",
        str(clip_duration),
        "-an",
        "-sn",
        "-dn",
        "-map",
        "0:v:0",
        "-vf",
        "fps=2,scale='min(1280,iw)':-2:flags=lanczos",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(proxy_path),
    ]
    try:
        run(cmd)
        return proxy_path if proxy_path.exists() else None
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_face_cascade() -> Any:
    if cv2 is None:
        raise RouterClientError("opencv-python-headless belum tersedia")
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        raise RouterClientError(f"Gagal memuat face cascade: {cascade_path}")
    return detector


@lru_cache(maxsize=1)
def _load_mediapipe_face_detector() -> Any:
    if mp is None:
        raise RouterClientError("mediapipe belum tersedia")
    return mp.solutions.face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=0.35,
    )


@lru_cache(maxsize=32)
def probe_video_size(path: Path) -> tuple[int, int]:
    result = run([
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
    width_str, height_str = result.stdout.strip().split("x", 1)
    return int(width_str), int(height_str)


def _calc_scaled_dims(input_w: int, input_h: int, target_w: int, target_h: int) -> tuple[int, int]:
    target_aspect = target_w / target_h
    input_aspect = input_w / input_h
    if input_aspect >= target_aspect:
        scaled_h = target_h
        scaled_w = int(round(input_w * target_h / input_h))
    else:
        scaled_w = target_w
        scaled_h = int(round(input_h * target_w / input_w))
    return max(target_w, scaled_w), max(target_h, scaled_h)


def _clamp(value: float, low: float, high: float) -> int:
    return int(round(max(low, min(high, value))))



def _even_floor(value: int) -> int:
    return value - (value % 2)



def _fit_crop_box(center_x: float, center_y: float, crop_w: int, crop_h: int, frame_w: int, frame_h: int) -> tuple[int, int]:
    crop_w = min(crop_w, frame_w)
    crop_h = min(crop_h, frame_h)
    crop_x = _clamp(center_x - crop_w / 2.0, 0, max(0, frame_w - crop_w))
    crop_y = _clamp(center_y - crop_h / 2.0, 0, max(0, frame_h - crop_h))
    crop_x = _even_floor(crop_x)
    crop_y = _even_floor(crop_y)
    crop_x = min(crop_x, max(0, frame_w - crop_w))
    crop_y = min(crop_y, max(0, frame_h - crop_h))
    return crop_x, crop_y



def analyze_stable_crop(input_path: Path, start: float, duration: float, target_resolution: str) -> CropAnalysis:
    target_w, target_h = (int(part) for part in target_resolution.split("x", 1))
    input_w, input_h = probe_video_size(input_path)
    scaled_w, scaled_h = _calc_scaled_dims(input_w, input_h, target_w, target_h)
    scale_x = scaled_w / input_w
    scale_y = scaled_h / input_h
    center_x = scaled_w / 2.0
    center_y = scaled_h / 2.0

    if cv2 is None:
        crop_x, crop_y = _fit_crop_box(center_x, center_y, target_w, target_h, scaled_w, scaled_h)
        return CropAnalysis(crop_x, crop_y, target_w, target_h, 0, 0, 0, "center", "OpenCV unavailable; using centered crop.")

    analysis_input = input_path
    analysis_offset = float(start)
    analysis_duration = max(1.0, float(duration))
    proxy_path = None

    capture = cv2.VideoCapture(str(analysis_input))
    opened = capture.isOpened()
    if opened:
        ok_probe, frame_probe = capture.read()
        if not ok_probe or frame_probe is None:
            opened = False
        capture.release()

    proxy_used = False
    if not opened:
        proxy_path = _build_crop_proxy(input_path, start, duration)
        if proxy_path is not None:
            analysis_input = proxy_path
            analysis_offset = 0.0
            analysis_duration = probe_duration(proxy_path)
            proxy_used = True

    capture = cv2.VideoCapture(str(analysis_input))
    if not capture.isOpened():
        crop_x, crop_y = _fit_crop_box(center_x, center_y, target_w, target_h, scaled_w, scaled_h)
        return CropAnalysis(crop_x, crop_y, target_w, target_h, 0, 0, 0, "center", "VideoCapture unavailable even after proxy fallback; using centered crop.")

    cascade_detector = _load_face_cascade()
    mediapipe_detector = None
    if mp is not None:
        try:
            mediapipe_detector = _load_mediapipe_face_detector()
        except Exception:
            mediapipe_detector = None

    clip_end = min(analysis_offset + analysis_duration, probe_duration(analysis_input))
    step = max(0.30, min(1.0, analysis_duration / 18.0))
    sample_times: list[float] = []
    current = analysis_offset
    while current <= clip_end + 1e-3:
        sample_times.append(current)
        current += step
    if not sample_times:
        sample_times = [analysis_offset]

    prev_gray = None
    face_hits = 0
    scene_cuts = 0
    samples = 0
    face_centers_x: list[float] = []
    face_centers_y: list[float] = []
    fallback_centers_x: list[float] = []
    fallback_centers_y: list[float] = []
    mediapipe_hits = 0
    cascade_hits = 0
    two_person_frames = 0
    two_person_spreads: list[float] = []

    for ts in sample_times:
        capture.set(cv2.CAP_PROP_POS_MSEC, ts * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            continue
        samples += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            scene_score = float(diff.mean() / 255.0)
            if scene_score > 0.18:
                scene_cuts += 1
        prev_gray = gray

        detected = False
        if mediapipe_detector is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = mediapipe_detector.process(rgb)
            detections = getattr(result, "detections", None) or []
            if detections:
                boxes: list[tuple[float, float, float, float]] = []
                for det in detections:
                    rel = det.location_data.relative_bounding_box
                    x = max(0.0, float(rel.xmin))
                    y = max(0.0, float(rel.ymin))
                    w = max(0.0, float(rel.width))
                    h = max(0.0, float(rel.height))
                    if w * h >= 0.002:
                        boxes.append((x, y, w, h))
                if len(boxes) >= 2:
                    boxes.sort(key=lambda box: box[2] * box[3], reverse=True)
                    left, right = sorted(boxes[:2], key=lambda box: box[0] + box[2] / 2.0)
                    spread = (right[0] + right[2] / 2.0) - (left[0] + left[2] / 2.0)
                    # Ignore duplicate/near-identical detector boxes; genuine two-shot
                    # podcast framing normally puts faces apart by at least 18% frame width.
                    if spread >= 0.18:
                        two_person_frames += 1
                        two_person_spreads.append(spread)
                best_box = max(boxes, key=lambda box: box[2] * box[3]) if boxes else None
                if best_box is not None:
                    x, y, w, h = best_box
                    face_hits += 1
                    mediapipe_hits += 1
                    detected = True
                    face_centers_x.append((x + w / 2.0) * input_w * scale_x)
                    face_centers_y.append((y + h * 0.42) * input_h * scale_y)

        if not detected:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
            cascade_candidates = []
            for source in (gray, clahe):
                cascade_candidates.extend(cascade_detector.detectMultiScale(source, scaleFactor=1.08, minNeighbors=4, minSize=(32, 32)))
            alt_detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_alt2.xml"))
            if not alt_detector.empty():
                cascade_candidates.extend(alt_detector.detectMultiScale(clahe, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24)))
            profile_detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
            if not profile_detector.empty():
                cascade_candidates.extend(profile_detector.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24)))
                flipped = cv2.flip(gray, 1)
                flipped_faces = profile_detector.detectMultiScale(flipped, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24))
                frame_w = gray.shape[1]
                for x, y, w, h in flipped_faces:
                    cascade_candidates.append((frame_w - x - w, y, w, h))
            if len(cascade_candidates) > 0:
                x, y, w, h = max(cascade_candidates, key=lambda rect: rect[2] * rect[3])
                face_hits += 1
                cascade_hits += 1
                detected = True
                face_centers_x.append((x + w / 2.0) * scale_x)
                face_centers_y.append((y + h * 0.42) * scale_y)

        if not detected:
            h, w = gray.shape[:2]
            fallback_centers_x.append((w / 2.0) * scale_x)
            fallback_centers_y.append((h / 2.0) * scale_y)

    capture.release()
    if proxy_path is not None and proxy_path.exists():
        try:
            proxy_path.unlink()
        except Exception:
            pass

    if face_centers_x:
        chosen_x = float(median(face_centers_x))
        chosen_y = float(median(face_centers_y))
        mode = "face-stabilized"
        detector_parts = []
        if mediapipe_hits:
            detector_parts.append(f"MediaPipe {mediapipe_hits}")
        if cascade_hits:
            detector_parts.append(f"OpenCV {cascade_hits}")
        detector_summary = ", ".join(detector_parts) if detector_parts else "unknown"
        source_note = " via H264 proxy" if proxy_used else ""
        reason = (
            f"Face-aware crop from {face_hits}/{samples} detections ({detector_summary}){source_note} with {scene_cuts} scene cut resets; "
            f"median focus point used for stability."
        )
    else:
        chosen_x = float(median(fallback_centers_x)) if fallback_centers_x else center_x
        chosen_y = float(median(fallback_centers_y)) if fallback_centers_y else center_y
        mode = "scene-stabilized" if scene_cuts else "center"
        if scene_cuts:
            reason = f"Scene-aware center crop from {scene_cuts} scene cut resets{' via H264 proxy' if proxy_used else ''}."
        elif samples == 0:
            reason = "No readable frames for crop analysis even after proxy fallback; using centered crop."
        else:
            reason = f"No faces detected even with MediaPipe/OpenCV{' via H264 proxy' if proxy_used else ''}; using centered crop."

    crop_x, crop_y = _fit_crop_box(chosen_x, chosen_y, target_w, target_h, scaled_w, scaled_h)
    two_person_ratio = two_person_frames / max(1, samples)
    # A conversational two-shot need not persist for a majority of frames: speakers
    # naturally cut away, turn profile, or temporarily leave the detector. 15% is
    # enough to protect the recurring second speaker, while one-off false hits stay 9:16.
    if two_person_ratio >= 0.15:
        # Product policy: a recurring two-person conversation keeps the original
        # horizontal composition. This prevents a centered 3:4 crop from losing
        # either participant.
        aspect_ratio = "16:9"
        reason += f" Two-person framing detected in {two_person_frames}/{samples} samples; selected 16:9 by two-speaker landscape policy."
    else:
        aspect_ratio = "9:16"
    return CropAnalysis(crop_x, crop_y, target_w, target_h, face_hits, scene_cuts, samples, mode, reason, aspect_ratio, two_person_frames)


def _adaptive_resolution(base_resolution: str, crop: CropAnalysis) -> str:
    """Preserve both speakers when the crop analyzer finds a stable two-person shot."""
    if crop.aspect_ratio == "16:9":
        return "1920x1080"
    if crop.aspect_ratio == "3:4":
        return "1080x1440"
    return base_resolution


@lru_cache(maxsize=4)
def _load_local_whisper_model(model_name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RouterClientError(f"faster-whisper tidak tersedia: {exc}") from exc

    try:
        return WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:
        raise RouterClientError(f"Gagal memuat local ASR model '{model_name}': {exc}") from exc


def _local_whisper_transcribe(audio_path: Path, language: str | None = None, prompt: str | None = None) -> dict[str, Any]:
    model = _load_local_whisper_model(
        settings.local_transcription_model,
        settings.local_transcription_device,
        settings.local_transcription_compute_type,
    )
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=(language or settings.local_transcription_language or None),
        task="transcribe",
        beam_size=max(1, settings.local_transcription_beam_size),
        word_timestamps=True,
        initial_prompt=prompt,
    )

    segments: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for segment in segments_iter:
        segment_text = str(getattr(segment, "text", "")).strip()
        if segment_text:
            text_parts.append(segment_text)
        words: list[dict[str, Any]] = []
        for word in getattr(segment, "words", []) or []:
            word_text = str(getattr(word, "word", "")).strip()
            start = getattr(word, "start", None)
            end = getattr(word, "end", None)
            if not word_text or start is None or end is None:
                continue
            words.append({"word": word_text, "start": float(start), "end": float(end)})
        segments.append(
            {
                "start": float(getattr(segment, "start", 0.0)),
                "end": float(getattr(segment, "end", 0.0)),
                "text": segment_text,
                "words": words,
            }
        )

    return {
        "text": " ".join(text_parts).strip(),
        "segments": segments,
        "source": "local-whisper",
        "model": settings.local_transcription_model,
        "device": settings.local_transcription_device,
        "compute_type": settings.local_transcription_compute_type,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
    }



def extract_silence_segments(path: Path, min_silence_dur: float = 0.6, noise_db: str = "-30dB") -> list[Segment]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db}:d={min_silence_dur}",
            "-f",
            "null",
            "-",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    silence_starts: list[float] = []
    silence_ends: list[float] = []
    for line in proc.stderr.splitlines():
        m1 = re.search(r"silence_start: ([0-9.]+)", line)
        if m1:
            silence_starts.append(float(m1.group(1)))
        m2 = re.search(r"silence_end: ([0-9.]+) \|", line)
        if m2:
            silence_ends.append(float(m2.group(1)))

    segments: list[Segment] = []
    cursor = 0.0
    for start, end in zip(silence_starts, silence_ends):
        if start > cursor:
            segments.append(Segment(cursor, start))
        cursor = max(cursor, end)
    return [s for s in segments if s.duration >= 1.0]



def choose_best_segment(segments: list[Segment], target_duration: float, total_duration: float) -> Segment:
    if not segments:
        return Segment(0.0, min(target_duration, total_duration))
    segments = sorted(segments, key=lambda s: s.duration, reverse=True)
    best = segments[0]
    if best.duration >= target_duration:
        mid = (best.start + best.end) / 2.0
        start = max(0.0, mid - target_duration / 2.0)
        end = start + target_duration
        if end > total_duration:
            end = total_duration
            start = max(0.0, end - target_duration)
        return Segment(start, end)
    return Segment(best.start, min(total_duration, best.end))



def render_vertical_clip(
    input_path: Path,
    output_path: Path,
    start: float,
    duration: float,
    target_resolution: str = "1080x1920",
    fps: int = 30,
    subtitles_path: Path | None = None,
    crop_analysis: CropAnalysis | None = None,
) -> None:
    width, height = (int(part) for part in target_resolution.split("x", 1))
    
    # Adaptive layout processing
    if crop_analysis is not None and crop_analysis.aspect_ratio == "3:4":
        vf = "crop=in_h*4/3:in_h,scale=1080:810,pad=1080:1920:0:250:color=black"
    elif crop_analysis is not None:
        crop_x = crop_analysis.crop_x
        crop_y = crop_analysis.crop_y
        crop_w = crop_analysis.crop_w
        crop_h = crop_analysis.crop_h
        vf = f"scale={crop_w}:{crop_h}:force_original_aspect_ratio=increase,crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
    else:
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        
    if subtitles_path is not None:
        vf = f"{vf},subtitles=\'{_escape_ffmpeg_filter_path(subtitles_path)}\'"
    # Trim and reset both streams from the same source window. Keeping this in
    # filter_complex avoids timestamp drift between the portrait video, audio,
    # and ASS cues when rendering a highlight from a long source.
    # Keep the input seek before the filters. With long AV1 sources, applying
    # -ss after the input makes FFmpeg decode from timestamp zero and can leave
    # the filter graph in a broken/timeout state. The trimmed input window is
    # then reset for both streams before crop/subtitle processing.
    filter_complex = (
        f"[0:v]trim=start=0:duration={max(0.1, duration):.3f},"
        f"setpts=PTS-STARTPTS,{vf}[v];"
        f"[0:a]atrim=start=0:duration={max(0.1, duration):.3f},"
        "asetpts=PTS-STARTPTS,highpass=f=80,equalizer=f=3000:width_type=h:width=200:g=4,loudnorm=I=-14:TP=-1.0:LRA=11,aresample=async=1:first_pts=0[a]"
    )
    run([
        "ffmpeg", "-y",
        "-hwaccel", "none",
        "-c:v", "libdav1d",
        "-ss", f"{max(0.0, start):.3f}",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-r", str(fps),
        "-c:v", "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ])


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()



def _segment_score(text: str) -> float:
    normalized = _normalize_text(text)
    words = normalized.split()
    if not words:
        return 0.0

    score = min(30.0, len(words) * 2.0)
    score += 8.0 if "?" in text else 0.0
    score += 6.0 if "!" in text else 0.0
    score += 4.0 if len(words) >= 6 else 0.0
    score += 4.0 if len(words) <= 24 else 0.0
    hook_terms = {
        "why",
        "how",
        "what",
        "secret",
        "mistake",
        "problem",
        "important",
        "actually",
        "but",
        "however",
        "because",
        "crazy",
        "best",
        "worst",
        "change",
        "learn",
        "never",
        "always",
    }
    score += sum(2.5 for word in words if word in hook_terms)
    if any(token in normalized for token in ("you know", "here's", "listen", "look")):
        score += 5.0
    return min(100.0, score)


def _normalized_heuristic_score(window_score: float, segment_count: int, duration: float, desired_duration: float) -> float:
    if segment_count <= 0:
        return 0.0
    avg_segment_score = window_score / max(1, segment_count)
    engagement_score = min(55.0, avg_segment_score * 0.55)
    coverage_score = min(20.0, max(0.0, duration) * 0.35)
    duration_fit = 25.0 * max(0.0, 1.0 - abs(duration - desired_duration) / max(desired_duration, 1.0))
    return min(100.0, engagement_score + coverage_score + duration_fit)



def _parse_transcript_segments(raw_segments: list[dict[str, Any]]) -> list[TranscriptSegment]:
    parsed: list[TranscriptSegment] = []
    for segment in raw_segments:
        try:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
            text = str(segment.get("text", "")).strip()
        except (TypeError, ValueError):
            continue
        if text:
            parsed.append(TranscriptSegment(start=start, end=end, text=text))
    return parsed


def _parse_transcript_words(raw_words: list[dict[str, Any]]) -> list[TranscriptWord]:
    parsed: list[TranscriptWord] = []
    for word in raw_words:
        try:
            start = float(word.get("start", 0.0))
            end = float(word.get("end", start))
            text = str(word.get("word", "")).strip()
        except (TypeError, ValueError, AttributeError):
            continue
        if text:
            parsed.append(TranscriptWord(start=start, end=end, word=text))
    return parsed


_SUBTITLE_TEXT_REPLACEMENTS = {
    "buuka": "buka",
    "menyetuh": "menyentuh",
    "ngerilase": "ngerilis",
    "comedi": "komedi",
    "Udemi": "Udemy",
}


_SPOKEN_CURRENCY_REPLACEMENTS = {
    "seratus juta": "Rp100 juta",
    "seratus ribu": "Rp100 ribu",
    "satu juta": "Rp1 juta",
    "sepuluh juta": "Rp10 juta",
    "dua puluh juta": "Rp20 juta",
    "lima puluh juta": "Rp50 juta",
}


def _apply_exact_word_replacements(text: str, replacements: dict[str, str]) -> str:
    updated = text
    for source, replacement in replacements.items():
        updated = re.sub(rf"\b{re.escape(source)}\b", replacement, updated, flags=re.IGNORECASE)
    return updated


def _normalize_currency_surface_forms(text: str) -> str:
    normalized = text
    for spoken, formatted in _SPOKEN_CURRENCY_REPLACEMENTS.items():
        normalized = re.sub(rf"(?<!Rp)\b{spoken}\b", formatted, normalized, flags=re.IGNORECASE)
    # Auto captions occasionally emit currency as R100 / R00, or leave a stray slash.
    normalized = re.sub(r"\bR(?=\d)", "Rp", normalized)
    normalized = re.sub(r"\bRp\s+(\d)", r"Rp\1", normalized)
    normalized = re.sub(r"(?<=\d)/(?!\d)", "", normalized)
    normalized = re.sub(r"\bRp00\b", "Rp100", normalized)
    normalized = re.sub(r"\bRpO0\b", "Rp100", normalized, flags=re.IGNORECASE)
    return normalized


def _clean_subtitle_text(text: str) -> str:
    """Apply only deterministic cosmetic fixes to known auto-caption artifacts.

    This deliberately avoids rewriting spoken phrasing or inventing content: timestamps
    must stay aligned with the original YouTube caption segment.
    """
    cleaned = " ".join(str(text or "").split())
    cleaned = _apply_exact_word_replacements(cleaned, _SUBTITLE_TEXT_REPLACEMENTS)
    cleaned = _normalize_currency_surface_forms(cleaned)
    return cleaned



def _canonical_currency_amount(amount: str, unit: str) -> str:
    unit = unit.lower()
    if unit == "jt":
        unit = "juta"
    return f"Rp{amount} {unit}"


def _extract_currency_amount(text: str) -> str:
    match = re.search(r"\bRp\s?(\d+(?:[.,]\d+)?)\s*(juta|ribu|miliar|jt)\b", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return _canonical_currency_amount(match.group(1), match.group(2))


def _replace_bare_currency_fragment(text: str, last_currency_amount: str) -> str:
    if not last_currency_amount:
        return text
    return re.sub(r"\b(?:R|Rp)\s+(juta|ribu|miliar|jt)\b", last_currency_amount, text, flags=re.IGNORECASE)


def _recover_split_currency_token(
    token: TranscriptWord,
    next_token: TranscriptWord | None,
    last_currency_amount: str,
) -> tuple[TranscriptWord | None, str, int]:
    text = _clean_subtitle_text(token.word)
    next_text = _clean_subtitle_text(next_token.word) if next_token else ""

    known_amount = _extract_currency_amount(text)
    if known_amount:
        return None, known_amount, 0

    split_amount = re.fullmatch(r"Rp\s?(\d+(?:[.,]\d+)?)", text, flags=re.IGNORECASE)
    split_unit = re.fullmatch(r"(juta|ribu|miliar|jt)", next_text, flags=re.IGNORECASE)
    if split_amount and split_unit and next_token:
        recovered = _canonical_currency_amount(split_amount.group(1), split_unit.group(1))
        merged = TranscriptWord(start=token.start, end=next_token.end, word=recovered)
        return merged, recovered, 2

    if (
        last_currency_amount
        and next_token
        and re.fullmatch(r"(?:R|Rp)", text, flags=re.IGNORECASE)
        and re.fullmatch(r"(?:juta|ribu|miliar|jt)", next_text, flags=re.IGNORECASE)
    ):
        merged = TranscriptWord(start=token.start, end=next_token.end, word=last_currency_amount)
        return merged, last_currency_amount, 2

    repaired_text = _replace_bare_currency_fragment(text, last_currency_amount)
    recovered_amount = _extract_currency_amount(repaired_text) or last_currency_amount
    return TranscriptWord(start=token.start, end=token.end, word=repaired_text), recovered_amount, 1


def _repair_currency_context(words: list[TranscriptWord]) -> list[TranscriptWord]:
    repaired: list[TranscriptWord] = []
    last_currency_amount = ""
    index = 0
    while index < len(words):
        token = words[index]
        next_token = words[index + 1] if index + 1 < len(words) else None
        merged_token, next_currency_amount, consumed = _recover_split_currency_token(token, next_token, last_currency_amount)
        if merged_token is not None:
            repaired.append(merged_token)
        last_currency_amount = next_currency_amount
        index += max(consumed, 1)
    return repaired


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _escape_ffmpeg_filter_path(path: Path) -> str:
    return str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def _format_ass_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:d}:{minutes:02d}:{secs:05.2f}"


def _visible_text_length(text: str) -> int:
    return len(_normalize_text(text).replace(" ", ""))



def _choose_wrap_index(lengths: list[int], max_chars: int, words_for_rules: list[str] | None = None) -> int | None:
    if len(lengths) < 2:
        return None
    total = sum(lengths) + max(0, len(lengths) - 1)
    if total <= max_chars:
        return None

    bad_endings = {
        "dan", "atau", "yang", "di", "ke", "dari", "untuk", "karena", "kalau",
        "jadi", "itu", "ini", "ya", "deh", "nih", "sih", "pun", "lagi", "aja",
    }
    bad_starts = {
        "dan", "atau", "yang", "di", "ke", "dari", "untuk", "karena", "kalau",
        "jadi", "itu", "ini", "ya", "deh", "nih", "sih", "pun", "lagi", "aja",
        "adalah", "akan",
    }

    best_idx = None
    best_score = None
    prefix = 0
    for i in range(1, len(lengths)):
        prefix += lengths[i - 1]
        line_one_len = prefix + (i - 1)
        line_two_len = (total - line_one_len - 1)
        if line_one_len > max_chars or line_two_len > max_chars:
            continue

        score = abs(line_one_len - line_two_len)
        if line_one_len < max(8, int(max_chars * 0.45)):
            score += 25
        if line_two_len < max(8, int(max_chars * 0.45)):
            score += 25
        if i == 1 or i == len(lengths) - 1:
            score += 20
        if words_for_rules:
            left = re.sub(r"[^\\w]+$", "", words_for_rules[i - 1].lower())
            right = re.sub(r"^[^\\w]+", "", words_for_rules[i].lower())
            if left in bad_endings:
                score += 8
            if right in bad_starts:
                score += 8
            if len(left) <= 2:
                score += 3
            if len(right) <= 2:
                score += 3
            if len(left) <= 4:
                score += 5
            if len(right) <= 4:
                score += 5

        if best_score is None or score < best_score:
            best_score = score
            best_idx = i

    if best_idx is not None:
        return best_idx

    prefix = 0
    best_idx = 1
    best_over = None
    for i in range(1, len(lengths)):
        prefix += lengths[i - 1]
        line_one_len = prefix + (i - 1)
        overflow = max(0, line_one_len - max_chars)
        score = overflow
        if line_one_len < max(8, int(max_chars * 0.45)):
            score += 25
        if i == 1 or i == len(lengths) - 1:
            score += 20
        if best_over is None or score < best_over:
            best_over = score
            best_idx = i
    return best_idx


def _wrap_ass_tokens(tokens: list[str], max_chars: int = 30) -> str:
    if not tokens:
        return ""
    lengths = [_visible_text_length(token) for token in tokens]
    visible_words = [re.sub(r"\{[^}]*\}", "", token).strip() for token in tokens]
    split_at = _choose_wrap_index(lengths, max_chars, visible_words)
    if split_at is None:
        return " ".join(tokens).strip()
    line_one = " ".join(tokens[:split_at]).strip()
    line_two = " ".join(tokens[split_at:]).strip()
    return line_one + r"\N" + line_two



def _wrap_plain_text(text: str, max_chars: int = 24) -> str:
    words = [token for token in text.split() if token.strip()]
    if not words:
        return ""
    lengths = [len(token) for token in words]
    split_at = _choose_wrap_index(lengths, max_chars, words)
    if split_at is None:
        return " ".join(words).strip()
    return " ".join(words[:split_at]).strip() + r"\N" + " ".join(words[split_at:]).strip()


def _wrap_plain_ass_text(text: str, max_chars: int = 24) -> str:
    words = [token for token in text.split() if token.strip()]
    if not words:
        return ""
    
    lines = []
    for i in range(0, len(words), 3):
        escaped_words = [_escape_ass_text(w) for w in words[i:i+3]]
        lines.append(" ".join(escaped_words))
        
    return r"\N".join(lines)



def _chunk_transcript_words(words: list[TranscriptWord], chunk_size: int = 3) -> list[TranscriptWord]:
    chunk_size = max(1, int(chunk_size or 1))
    if chunk_size <= 1 or len(words) <= 1:
        return words
    chunks: list[TranscriptWord] = []
    for index in range(0, len(words), chunk_size):
        group = words[index:index + chunk_size]
        if not group:
            continue
        text = " ".join(word.word.strip() for word in group if word.word.strip()).strip()
        if not text:
            continue
        chunks.append(TranscriptWord(start=group[0].start, end=group[-1].end, word=text))
    return chunks



def _caption_base_size(text: str, default_size: int) -> int:
    """Scale a caption by visible density: short hooks read larger than long sentences."""
    visible = max(1, _visible_text_length(text))
    if visible <= 10:
        factor = 1.50
    elif visible <= 18:
        factor = 1.32
    elif visible <= 28:
        factor = 1.15
    elif visible >= 46:
        factor = 0.84
    elif visible >= 36:
        factor = 0.93
    else:
        factor = 1.0
    return max(36, int(round(default_size * factor)))


def _is_caption_keyword(word: str) -> bool:
    normalized = re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "", word).lower()
    if re.fullmatch(r"rp?\d+[a-z]*", normalized):
        return True
    return normalized in {
        "uang", "juta", "miliar", "ribu", "pertama", "rahasia", "cara",
        "bisnis", "investasi", "invest", "modal", "profit", "produk", "digital",
        "viral", "penting", "harus", "jangan", "gagal", "sukses",
    }


def _format_ass_base_line(words: list[TranscriptWord], max_chars: int) -> str:
    """Render a stable white sentence; active-word emphasis is emitted separately."""
    tokens = [_escape_ass_text(word.word) for word in words]
    return _wrap_ass_tokens(tokens, max_chars=max_chars).strip()


def _active_word_text(word: str, default_size: int, style_profile: dict[str, Any] | None = None) -> str:
    """A per-word pop overlay, deliberately without karaoke/purple letter fill."""
    profile = style_profile or {}
    is_keyword = _is_caption_keyword(word)
    normal_scale = float(profile.get("word_normal_scale", 1.45))
    keyword_scale = float(profile.get("word_keyword_scale", 1.62))
    size = int(round(default_size * (keyword_scale if is_keyword else normal_scale)))
    colour = str(profile.get("word_keyword_colour", "&H0000D7FF")) if is_keyword else str(profile.get("word_normal_colour", "&H00FFFFFF"))
    border = int(profile.get("word_border", 8))
    prefix = str(profile.get("word_prefix", "{\\an2}"))
    return (
        prefix[:-1] + "\\fs" + str(size)
        + "\\1c" + colour
        + "\\b1\\bord" + str(border) + "\\3c&H00111111\\shad0}"
        + _escape_ass_text(word)
    )


def _progressive_stack_text(
    text: str,
    default_size: int,
    line_index: int,
    style_profile: dict[str, Any] | None = None,
) -> str:
    """Render one persistent left-entering row in a 3x3 caption stack."""
    profile = style_profile or {}
    is_keyword_phrase = any(_is_caption_keyword(token) for token in text.split())
    size = int(round(default_size * (1.13 if is_keyword_phrase else 1.05)))
    colour = (
        str(profile.get("word_keyword_colour", "&H0000D7FF"))
        if is_keyword_phrase
        else str(profile.get("word_normal_colour", "&H00FFFFFF"))
    )
    border = int(profile.get("word_border", 8))
    # Three rows stay in lower-middle, clear of the TikTok bottom UI.
    y = 1165 + (line_index * 120)
    return (
        "{\\an1\\move(-90," + str(y) + ",150," + str(y) + ",0,180)"
        + "\\fscx118\\fscy118\\t(0,160,\\fscx100\\fscy100)"
        + "\\fs" + str(size) + "\\1c" + colour
        + "\\b1\\bord" + str(border) + "\\3c&H00111111\\shad0}"
        + _escape_ass_text(text.upper())
    )


def _segment_to_word_karaoke(text: str, start: float, end: float) -> list[TranscriptWord]:
    cleaned = [token for token in text.split() if token.strip()]
    if not cleaned:
        return []
    total_duration = max(0.2, end - start)
    total_chars = sum(max(1, len(token.strip(".,!?;:()[]{}\"'"))) for token in cleaned)
    cursor = start
    words: list[TranscriptWord] = []
    for index, token in enumerate(cleaned):
        weight = max(1, len(token.strip(".,!?;:()[]{}\"'")))
        if index == len(cleaned) - 1:
            word_end = end
        else:
            word_end = cursor + (total_duration * (weight / total_chars))
        words.append(TranscriptWord(word=token, start=cursor, end=max(cursor + 0.05, word_end)))
        cursor = words[-1].end
    if words:
        words[-1].end = max(words[-1].start + 0.05, end)
    return words


def _extract_reason_meta(reason: str, key: str) -> str:
    match = re.search(r"(?:^|\|)\s*" + re.escape(key) + r"=([^|]+)", reason or "")
    if not match:
        return ""
    return _clean_subtitle_text(match.group(1).strip())


def _extract_hook_text(reason: str) -> str:
    return _extract_reason_meta(reason, "hook")


def _extract_clipper_style(reason: str) -> str:
    value = _extract_reason_meta(reason, "clipper_style").lower()
    return value if value in {"memes", "pov", "aura", "motivasi"} else ""


def _subtitle_style_profile(clipper_style: str) -> dict[str, Any]:
    style = (clipper_style or "").lower()
    if style == "memes":
        return {
            "hook_colour": "&H00FFFFFF",
            "hook_back_colour": "&H78000000",
            "hook_alignment": 8,
            # Fill the usable horizontal safe area before wrapping; avoid a tall,
            # word-by-word hook column when a balanced headline fits.
            "hook_wrap": 18,
            "hook_duration": 7.0,
            "hook_margin_lr_ratio": 0.12,
            "hook_margin_v_ratio": 0.09,
            "caption_mode": "continuous_three_lines",
            "word_normal_scale": 1.34,
            "word_keyword_scale": 1.5,
            "word_normal_colour": "&H00FFFFFF",
            "word_keyword_colour": "&H0077FFFF",
            "word_border": 9,
            "word_alignment": 2,
            "word_prefix": "{\\an2\\fsp1}",
            "plain_alignment": "{\\an2}",
            "plain_wrap": 20,
        }
    if style == "pov":
        return {
            "hook_colour": "&H00FFFFFF",
            "hook_back_colour": "&H7A101010",
            "hook_alignment": 8,
            # Fill the usable horizontal safe area before wrapping; avoid a tall,
            # word-by-word hook column when a balanced headline fits.
            "hook_wrap": 18,
            "hook_duration": 7.0,
            "hook_margin_lr_ratio": 0.12,
            "hook_margin_v_ratio": 0.09,
            "word_normal_scale": 1.28,
            "word_keyword_scale": 1.44,
            "word_normal_colour": "&H00FFFFFF",
            "word_keyword_colour": "&H0099D8FF",
            "word_border": 8,
            "word_alignment": 2,
            "word_prefix": "{\\an2\\fsp1}",
            "plain_alignment": "{\\an2}",
            "plain_wrap": 18,
        }
    if style == "aura":
        return {
            "hook_colour": "&H00A7F3FF",
            "hook_back_colour": "&H50000000",
            "hook_alignment": 8,
            # Fill the usable horizontal safe area before wrapping; avoid a tall,
            # word-by-word hook column when a balanced headline fits.
            "hook_wrap": 18,
            "hook_duration": 7.0,
            "hook_margin_lr_ratio": 0.12,
            "hook_margin_v_ratio": 0.09,
            "word_normal_scale": 1.5,
            "word_keyword_scale": 1.72,
            "word_normal_colour": "&H00FFFFFF",
            "word_keyword_colour": "&H00A7F3FF",
            "word_border": 10,
            "word_alignment": 2,
            "word_prefix": "{\\an2\\fsp1}",
            "plain_alignment": "{\\an2}",
            "plain_wrap": 24,
        }
    return {
        "hook_colour": "&H0000D7FF",
        "hook_back_colour": "&H64000000",
        "hook_alignment": 8,
        "hook_wrap": 18,
        "hook_duration": 7.0,
        "hook_margin_lr_ratio": 0.12,
        "hook_margin_v_ratio": 0.09,
        "word_normal_scale": 1.45,
        "word_keyword_scale": 1.62,
        "word_normal_colour": "&H00FFFFFF",
        "word_keyword_colour": "&H0000D7FF",
        "word_border": 8,
        "word_alignment": 2,
        "word_prefix": "{\\an2\\fsp1}",
        "plain_alignment": "{\\an2}",
        "plain_wrap": 24,
    }


def build_subtitle_ass(
    raw_segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    output_path: Path,
    target_resolution: str = "1080x1920",
    opening_hook_text: str = "",
    clipper_style: str = "",
) -> dict[str, Any]:
    play_res_x, play_res_y = target_resolution.split("x", 1)
    font_size = max(42, int(round(int(play_res_x) * 0.043)))
    margin_lr = max(180, int(round(int(play_res_x) * 0.17)))
    # Keep spoken captions clear of TikTok's bottom caption/control area.
    margin_v = max(250, int(round(int(play_res_y) * 0.19)))
    outline = max(3, int(round(int(play_res_x) * 0.0038)))
    shadow = 0
    primary_colour = "&H00FFFFFF"
    secondary_colour = "&H0000D7FF"
    outline_colour = "&H00111111"
    back_colour = "&H5A000000"
    style_profile = _subtitle_style_profile(clipper_style)
    hook_font_size = max(font_size + 16, int(round(font_size * 1.18)))
    hook_margin_lr = max(
        margin_lr,
        int(round(int(play_res_x) * float(style_profile.get("hook_margin_lr_ratio", 0.20)))),
    )
    hook_margin_v = max(
        110,
        int(round(int(play_res_y) * float(style_profile.get("hook_margin_v_ratio", 0.08)))),
    )
    hook_colour = str(style_profile.get("hook_colour", "&H0000D7FF"))
    hook_back_colour = str(style_profile.get("hook_back_colour", "&H64000000"))
    hook_alignment = int(style_profile.get("hook_alignment", 8))
    plain_wrap = int(style_profile.get("plain_wrap", 24))
    hook_wrap = int(style_profile.get("hook_wrap", 18))
    hook_duration = float(style_profile.get("hook_duration", 1.8))
    lines: list[str] = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {int(play_res_x)}",
        f"PlayResY: {int(play_res_y)}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,Montserrat SemiBold,{font_size},{primary_colour},{secondary_colour},{outline_colour},{back_colour},1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1",
        f"Style: Hook,Montserrat ExtraBold,{hook_font_size},{hook_colour},{hook_colour},{outline_colour},{hook_back_colour},1,0,0,0,100,100,0,0,1,{outline},0,{hook_alignment},{hook_margin_lr},{hook_margin_lr},{hook_margin_v},1",
        f"Style: Watermark,Montserrat SemiBold,32,&H00FFFFFF,&H00FFFFFF,&H00111111,&H5A000000,1,0,0,0,100,100,0,0,1,2,1,2,0,0,140,1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    if opening_hook_text:
        if not settings.keep_pov_prefix:
            opening_hook_text = re.sub(r"^POV\s*:\s*", "", opening_hook_text, flags=re.IGNORECASE).strip()
        # Wrap strictly by 3 words per line as user requested earlier
        words = opening_hook_text.split()
        lines_arr = []
        for i in range(0, len(words), 3):
            lines_arr.append(" ".join(words[i:i+3]).upper())
        
        # Color specific words pink, make the rest white
        colored_lines = []
        for i, line in enumerate(lines_arr):
            # First line white with "POV: ", second line pink, etc.
            if i == 0:
                if line.startswith("POV:"):
                    colored_lines.append(f"{{\\1c&H00FFFFFF}}{line}")
                else:
                    colored_lines.append(f"{{\\1c&H00FFFFFF}}POV: {line}")
            elif i % 2 != 0:
                colored_lines.append(f"{{\\1c&H00B000FF}}{line}")
            else:
                colored_lines.append(f"{{\\1c&H00FFFFFF}}{line}")
            
        hook_text = "\\N".join(colored_lines)
        
        # Persistent duration (full clip)
        clip_dur = clip_end - clip_start
        lines.append(
            "Dialogue: 5,"
            f"{_format_ass_timestamp(0.0)},"
            f"{_format_ass_timestamp(clip_dur)},"
            "Hook,,0,0,0,,"
            f"{hook_text}"
        )
        lines.append(
            "Dialogue: 4,"
            f"{_format_ass_timestamp(0.0)},"
            f"{_format_ass_timestamp(clip_dur)},"
            "Watermark,,0,0,0,,"
            "@gusaja.com"
        )
    

    prepared_segments: list[dict[str, Any]] = []
    for segment in raw_segments:
        try:
            seg_start = float(segment.get("start", 0.0))
            seg_end = float(segment.get("end", seg_start))
        except (TypeError, ValueError, AttributeError):
            continue
        # YouTube auto-caption segments overlap heavily. Never carry a segment
        # that started before the clip boundary into the new clip: doing so
        # makes the first subtitle lead or lag the actual spoken audio. The
        # selector should align clip_start to a complete transcript boundary;
        # this guard is the final safety net for persisted/legacy highlights.
        if seg_start < clip_start or seg_end <= clip_start or seg_start >= clip_end:
            continue
        text = _clean_subtitle_text(str(segment.get("text", "")).strip())
        if not text:
            continue
        prepared_segments.append(
            {
                "start": max(seg_start, clip_start),
                "end": min(seg_end, clip_end),
                "text": text,
                "words": segment.get("words") or [],
            }
        )

    prepared_segments.sort(key=lambda item: (float(item["start"]), float(item["end"])))

    # Recover a bare "R juta" only when the immediately preceding captions establish
    # one exact amount. This fixes auto-sub continuation such as "Rp100 juta pertama"
    # → "duit R juta" without guessing in unrelated clips.
    last_currency_amount = ""
    last_currency_time = -1_000_000.0
    for segment in prepared_segments:
        text = str(segment["text"])
        known_amount = _extract_currency_amount(text)
        if known_amount:
            last_currency_amount = known_amount
            last_currency_time = float(segment["end"])
        elif last_currency_amount and float(segment["start"]) - last_currency_time <= 25.0:
            text = _replace_bare_currency_fragment(text, last_currency_amount)
            segment["text"] = text
            recovered_amount = _extract_currency_amount(text)
            if recovered_amount:
                last_currency_amount = recovered_amount

    cue_count = 0
    word_cues = 0
    min_gap = 0.01
    caption_mode = str(style_profile.get("caption_mode", "continuous_three_lines"))
    continuous_words: list[TranscriptWord] = []
    for index, segment in enumerate(prepared_segments):
        start = float(segment["start"])
        end = float(segment["end"])
        next_start = None
        if index + 1 < len(prepared_segments):
            next_start = float(prepared_segments[index + 1]["start"])
        if next_start is not None and next_start < end:
            end = max(start + 0.05, next_start - min_gap)
        if end <= start + 0.04:
            continue

        text = str(segment["text"]).strip()
        raw_words = segment.get("words") or []
        words = _parse_transcript_words(raw_words) if isinstance(raw_words, list) else []
        # YouTube auto-subs normally have no reliable word timestamps. When they do,
        # prefer the cleaned segment text below so number normalization stays visible.
        words = [word for word in words if word.end > start and word.start < end]
        if words:
            trimmed_words: list[TranscriptWord] = []
            for word in words:
                word_start = max(start, word.start)
                word_end = min(end, word.end)
                if word_end <= word_start:
                    continue
                trimmed_words.append(TranscriptWord(start=word_start, end=word_end, word=_clean_subtitle_text(word.word)))
            words = _repair_currency_context(trimmed_words)
        if not words:
            words = _repair_currency_context(_segment_to_word_karaoke(text, start, end))

        if words and caption_mode == "continuous_three_lines":
            # Preserve the normal transcript flow across segments. Rendering occurs
            # after collection so a block can fill three visual lines before reset.
            continuous_words.extend(words)
            continue

        if words:
            # Legacy fallback mode: short multi-word cues.
            words = _chunk_transcript_words(words, chunk_size=3)
            emitted_words = 0
            for word in words:
                word_start = max(start, word.start)
                word_end = min(end, max(word_start + 0.09, word.end))
                if word_end <= word_start:
                    continue
                lines.append(
                    "Dialogue: 0,"
                    f"{_format_ass_timestamp(word_start - clip_start)},"
                    f"{_format_ass_timestamp(word_end - clip_start)},"
                    "Default,,0,0,0,,"
                    f"{_active_word_text(word.word, font_size, style_profile)}"
                )
                emitted_words += 1
            if emitted_words:
                cue_count += 1
                word_cues += emitted_words
                continue

        lines.append(
            "Dialogue: 0,"
            f"{_format_ass_timestamp(start - clip_start)},"
            f"{_format_ass_timestamp(end - clip_start)},"
            "Default,,0,0,0,,"
            + str(style_profile.get("plain_alignment", "{\\an2}"))
            + _escape_ass_text(_wrap_plain_text(text, max_chars=plain_wrap))
        )
        cue_count += 1

    if caption_mode == "continuous_three_lines" and continuous_words:
        # One accumulating transcript block: fill line 1, then line 2, then line 3.
        # Reset only when the next whole word would require a fourth line.
        safe_chars = int(style_profile.get("continuous_line_chars", 24))
        max_lines = int(style_profile.get("continuous_max_lines", 3))
        block: list[list[TranscriptWord]] = []
        snapshots: list[tuple[float, list[list[TranscriptWord]]]] = []
        seen_words: set[tuple[int, int, str]] = set()
        for word in sorted(continuous_words, key=lambda item: (item.start, item.end)):
            cleaned = _clean_subtitle_text(word.word).strip()
            if not cleaned or re.fullmatch(r"[A-Za-z]", cleaned):
                continue
            dedupe_key = (round(word.start * 100), round(word.end * 100), cleaned.lower())
            if dedupe_key in seen_words:
                continue
            seen_words.add(dedupe_key)
            candidate = [[*row] for row in block]
            if not candidate:
                candidate = [[TranscriptWord(start=word.start, end=word.end, word=cleaned)]]
            elif len(" ".join(item.word for item in candidate[-1] + [word])) <= safe_chars:
                candidate[-1].append(TranscriptWord(start=word.start, end=word.end, word=cleaned))
            elif len(candidate) < max_lines:
                candidate.append([TranscriptWord(start=word.start, end=word.end, word=cleaned)])
            else:
                candidate = [[TranscriptWord(start=word.start, end=word.end, word=cleaned)]]
            block = candidate
            snapshots.append((max(clip_start, word.start), [[*row] for row in block]))

        for index, (snapshot_start, snapshot) in enumerate(snapshots):
            snapshot_end = clip_end if index + 1 >= len(snapshots) else min(clip_end, snapshots[index + 1][0])
            if snapshot_end <= snapshot_start + 0.03:
                continue
            rendered_rows: list[str] = []
            for row in snapshot:
                rendered_rows.append(" ".join(
                    ("{\\1c" + str(style_profile.get("word_keyword_colour", "&H0000D7FF")) + "}" if _is_caption_keyword(item.word) else "{\\1c" + str(style_profile.get("word_normal_colour", "&H00FFFFFF")) + "}")
                    + _escape_ass_text(item.word.upper())
                    for item in row
                ))
            # A single normal text-run lets libass own glyph spacing and wrapping.
            # Anchor the whole caption block lower in the portrait-safe area; do not
            # position or animate individual words, which reads as a visual grid.
            # Top-left anchoring is intentional: as the transcript fills line 2
            # and line 3, line 1 remains fixed and newer lines extend downward.
            # Bottom-left (\\an1) makes every extra row grow upward, which reads as
            # the prior lines being pushed/jumped toward the slide.
            ass_text = (
                "{\\an7\\pos" + "(" + str(max(90, int(play_res_x) // 10)) + "," + str(int(int(play_res_y) * 0.669)) + ")"
                + "\\fs" + str(max(52, int(round(int(play_res_x) * 0.057))))
                + "\\b1\\bord" + str(max(7, outline + 4)) + "\\3c&H00111111\\shad0}"
                + r"\N".join(rendered_rows)
            )
            lines.append(
                "Dialogue: 1,"
                f"{_format_ass_timestamp(snapshot_start - clip_start)},"
                f"{_format_ass_timestamp(snapshot_end - clip_start)},"
                "Default,,0,0,0,,"
                + ass_text
            )
            cue_count += 1
            word_cues += sum(len(row) for row in snapshot)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(output_path), "cue_count": cue_count, "word_cues": word_cues, "caption_mode": caption_mode}



def _join_segment_texts(segments: list[TranscriptSegment], start: int, end: int) -> str:
    return " ".join(segment.text for segment in segments[start : end + 1]).strip()



def _expand_window(
    start: float,
    end: float,
    total_duration: float,
    target_duration: float,
    min_duration: float,
    max_duration: float,
) -> tuple[float, float]:
    total_duration = max(0.0, total_duration)
    if total_duration <= 0:
        return 0.0, 0.0

    min_target = min(max(0.1, min_duration), total_duration)
    max_target = min(max(min_target, max_duration), total_duration)
    preferred = min(max(min_target, target_duration), max_target)
    current = max(0.1, end - start)

    if current > max_target:
        midpoint = (start + end) / 2.0
        new_start = max(0.0, midpoint - preferred / 2.0)
        new_end = new_start + preferred
        if new_end > total_duration:
            new_end = total_duration
            new_start = max(0.0, new_end - preferred)
        return new_start, new_end

    if current >= min_target:
        return max(0.0, start), min(total_duration, end)

    missing = min_target - current
    pad_left = missing / 2.0
    pad_right = missing - pad_left
    new_start = max(0.0, start - pad_left)
    new_end = min(total_duration, end + pad_right)
    if new_end - new_start < min_target:
        if new_start == 0.0:
            new_end = min(total_duration, min_target)
        elif new_end == total_duration:
            new_start = max(0.0, total_duration - min_target)
    return new_start, new_end



def _locate_quote_window(segments: list[TranscriptSegment], quote: str) -> tuple[float, float] | None:
    normalized_quote = _normalize_text(quote)
    if not normalized_quote:
        return None
    # Locate the quote's actual first segment, not merely the first segment of
    # the search buffer. Captions often overlap; returning the buffer start could
    # otherwise leave 1-3 minutes of unrelated lead-in before the hook.
    combined = ""
    offsets: list[tuple[int, int]] = []
    for index, segment in enumerate(segments):
        part = _normalize_text(segment.text)
        if not part:
            continue
        start_offset = len(combined) + (1 if combined else 0)
        combined = f"{combined} {part}".strip()
        offsets.append((index, start_offset))
    match_at = combined.find(normalized_quote)
    if match_at < 0:
        return None
    start_index = 0
    for index, offset in offsets:
        if offset <= match_at:
            start_index = index
        else:
            break
    match_end = match_at + len(normalized_quote)
    end_index = start_index
    for index, offset in offsets:
        if offset < match_end:
            end_index = index
        else:
            break
    return segments[start_index].start, segments[end_index].end


def _ranges_overlap(start_a: float, end_a: float, start_b: float, end_b: float, padding: float = 0.0) -> bool:
    return max(start_a, start_b) < min(end_a, end_b) + padding


def _quote_key(text: str) -> str:
    normalized = _normalize_text(text)
    tokens = normalized.split()
    if len(tokens) > 32:
        tokens = tokens[:32]
    return " ".join(tokens)



def _heuristic_highlight(
    segments: list[TranscriptSegment],
    target_duration: float,
    min_duration: float,
    max_duration: float,
    total_duration: float,
) -> HighlightSelection:
    if not segments:
        end = min(total_duration, max(min_duration, target_duration))
        return HighlightSelection(0.0, end, 0.0, "No transcript segments available; fell back to start of video.", "", "fallback")

    best_score = float("-inf")
    best = (segments[0].start, segments[0].end, segments[0].text)
    for start_index in range(len(segments)):
        accumulated_duration = 0.0
        collected_texts: list[str] = []
        window_score = 0.0
        for end_index in range(start_index, len(segments)):
            seg = segments[end_index]
            collected_texts.append(seg.text)
            window_score += _segment_score(seg.text)
            accumulated_duration = segments[end_index].end - segments[start_index].start
            if accumulated_duration <= 0:
                continue
            # Do not cut a coherent thought merely to satisfy the preferred
            # short duration. Keep collecting transcript segments up to the
            # configured safety cap; the editorial target is only a preference.
            if accumulated_duration > max_duration:
                break
            desired = min(max(min_duration, target_duration), max_duration)
            score = _normalized_heuristic_score(
                window_score=window_score,
                segment_count=(end_index - start_index + 1),
                duration=accumulated_duration,
                desired_duration=desired,
            )
            if score > best_score:
                best_score = score
                best = (segments[start_index].start, segments[end_index].end, " ".join(collected_texts))

    start, end, quote = best
    start, end = _expand_window(start, end, total_duration, target_duration, min_duration, max_duration)
    return HighlightSelection(start, end, max(0.0, best_score), "Heuristic transcript scoring (flexible range).", quote, "heuristic")


def _fallback_highlight_pool(
    transcript_segments: list[TranscriptSegment],
    total_duration: float,
    target_duration: float,
    min_duration: float,
    max_duration: float,
    highlight_count: int,
) -> list[HighlightSelection]:
    ranked: list[tuple[float, HighlightSelection]] = []
    for start_index in range(len(transcript_segments)):
        collected_texts: list[str] = []
        window_score = 0.0
        for end_index in range(start_index, len(transcript_segments)):
            seg = transcript_segments[end_index]
            collected_texts.append(seg.text)
            window_score += _segment_score(seg.text)
            raw_start = transcript_segments[start_index].start
            raw_end = transcript_segments[end_index].end
            accumulated_duration = raw_end - raw_start
            if accumulated_duration <= 0:
                continue
            if max_duration > 0 and accumulated_duration > max_duration:
                break
            start, end = _expand_window(raw_start, raw_end, total_duration, target_duration, min_duration, max_duration)
            duration = end - start
            desired = min(max(min_duration, target_duration), max_duration)
            score = _normalized_heuristic_score(
                window_score=window_score,
                segment_count=(end_index - start_index + 1),
                duration=duration,
                desired_duration=desired,
            )
            ranked.append((score, HighlightSelection(start, end, score, "Heuristic transcript scoring (candidate pool).", " ".join(collected_texts), "heuristic")))

    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen: list[HighlightSelection] = []
    chosen_keys: set[str] = set()
    for _, candidate in ranked:
        if any(_ranges_overlap(candidate.start, candidate.end, existing.start, existing.end, padding=2.0) for existing in chosen):
            continue
        candidate_key = _quote_key(candidate.quote)
        if candidate_key in chosen_keys:
            continue
        chosen.append(candidate)
        chosen_keys.add(candidate_key)
        if len(chosen) >= highlight_count:
            break
    return chosen



def _llm_highlights(
    router_client: RouterClient,
    transcript_text: str,
    target_duration: float,
    min_duration: float,
    max_duration: float,
    highlight_count: int,
) -> list[dict[str, Any]]:
    prompt = (
        f"Pilih {int(highlight_count)} highlight paling kuat dari transkrip berikut. "
        "Balas HANYA JSON valid tanpa markdown, dengan key utama highlights yang berisi array object. "
        "Setiap object wajib punya key: highlight_quote, hook_text, reason, score. "
        "- hook_text MUST NOT BE EMPTY. Generate a short, punchy, truthful on-screen headline, max 12 words. Do NOT leave this blank. Create a strong POV or headline text that triggers curiosity.\n"
        f"Pilih highlight viral dengan durasi final fleksibel, bisa pendek bila memang sudah kuat, dan boleh sampai {int(max_duration)} detik, dengan durasi ideal sekitar {int(target_duration)} detik. "
        "Pilih kutipan yang benar-benar ada di transkrip dan jangan ubah kata-katanya. "
        "Setiap highlight harus berbeda, tidak tumpang tindih idenya, dan urutkan dari yang paling viral.\n\n"
        f"TRANSKRIP:\n{transcript_text}"
    )
    content = router_client.chat(
        [
            {"role": "system", "content": "You are a concise video editor that selects short viral highlight quotes."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []
        else:
            return []

    if isinstance(payload, dict):
        highlights = payload.get("highlights")
        if isinstance(highlights, list):
            return [item for item in highlights if isinstance(item, dict)]
        if all(key in payload for key in ("highlight_quote", "reason", "score")):
            return [payload]
    return []



def _count_passing(items: list[HighlightSelection], threshold: float) -> int:
    return sum(1 for item in items if item.score >= threshold)



def _mark_threshold_reason(items: list[HighlightSelection], threshold: float) -> None:
    threshold_tag = f"threshold={threshold}"
    for item in items:
        pass_tag = "passed" if item.score >= threshold else "below_threshold"
        parts = item.reason.split(" | ") if item.reason else []
        filtered = [part for part in parts if not part.startswith("threshold=") and not part.startswith("threshold_result=")]
        filtered.append(threshold_tag)
        filtered.append(f"threshold_result={pass_tag}")
        item.reason = " | ".join(filtered)



def _apply_threshold_backoff(
    selections: list[HighlightSelection],
    requested_count: int,
    score_threshold: float,
    min_output_count: int,
    threshold_backoff_step: float,
    min_score_threshold_floor: float,
) -> tuple[list[HighlightSelection], dict[str, Any]]:
    requested_count = max(1, requested_count)
    min_output_count = max(1, min(min_output_count, requested_count))
    threshold_backoff_step = max(0.1, threshold_backoff_step)
    floor = max(0.0, min(min_score_threshold_floor, score_threshold))
    effective_threshold = max(0.0, score_threshold)
    backoff_applied = False
    while effective_threshold > floor and _count_passing(selections, effective_threshold) < min_output_count:
        next_threshold = max(floor, effective_threshold - threshold_backoff_step)
        if next_threshold == effective_threshold:
            break
        effective_threshold = next_threshold
        backoff_applied = True
    _mark_threshold_reason(selections, effective_threshold)
    filtered = [candidate for candidate in selections if candidate.score >= effective_threshold]
    if filtered:
        return filtered[:requested_count], {
            "requested_count": requested_count,
            "initial_threshold": score_threshold,
            "effective_threshold": effective_threshold,
            "min_output_count": min_output_count,
            "threshold_backoff_step": threshold_backoff_step,
            "min_score_threshold_floor": floor,
            "backoff_applied": backoff_applied,
            "output_count": len(filtered[:requested_count]),
            "available_candidates": len(selections),
        }
    return selections[:requested_count], {
        "requested_count": requested_count,
        "initial_threshold": score_threshold,
        "effective_threshold": effective_threshold,
        "min_output_count": min_output_count,
        "threshold_backoff_step": threshold_backoff_step,
        "min_score_threshold_floor": floor,
        "backoff_applied": backoff_applied,
        "output_count": len(selections[:requested_count]),
        "available_candidates": len(selections),
        "fallback_used": True,
    }



def select_highlights(
    transcript_segments: list[TranscriptSegment],
    total_duration: float,
    target_duration: float,
    min_duration: float,
    max_duration: float,
    highlight_count: int,
    score_threshold: float,
    min_output_count: int,
    threshold_backoff_step: float,
    min_score_threshold_floor: float,
    router_client: RouterClient | None = None,
    precomputed_llm_results: list[dict[str, Any]] | None = None,
) -> tuple[list[HighlightSelection], dict[str, Any]]:
    if not transcript_segments:
        raise RouterClientError("Tidak ada transcript segments untuk dipilih highlight-nya")

    selections: list[HighlightSelection] = []
    used_quotes: set[str] = set()

    llm_candidates = 0
    llm_accepted = 0
    # URL ingestion may finish the Gemini editorial pass while yt-dlp is still
    # downloading. Reuse that persisted result rather than paying/awaiting twice.
    llm_results = precomputed_llm_results or []
    if not llm_results and router_client and settings.router_ready:
        transcript_text = "\n".join(segment.text for segment in transcript_segments)
        llm_results = _llm_highlights(router_client, transcript_text, target_duration, min_duration, max_duration, highlight_count)
    if llm_results:
        llm_candidates = len(llm_results)
        for item in llm_results:
            quote = str(item.get("highlight_quote", "")).strip()
            quote_key = _quote_key(quote)
            if not quote or not quote_key or quote_key in used_quotes:
                continue
            reason = str(item.get("reason", "LLM selection.")).strip() or "LLM selection."
            hook_text = str(item.get("hook_text", "")).strip()
            if not hook_text:
                hook_text = " ".join(quote.split()[:5])
            clipper_style = str(item.get("clipper_style", "")).strip().lower()
            style_reason = str(item.get("style_reason", "")).strip()
            editing_notes = str(item.get("editing_notes", "")).strip()
            recommended_bgm = item.get("recommended_bgm", [])
            if not isinstance(recommended_bgm, list):
                recommended_bgm = []
            try:
                score = float(item.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0
            window = _locate_quote_window(transcript_segments, quote)
            if not window:
                continue
            # For an editorial candidate, its first words ARE the proposed hook.
            # Do not midpoint-trim a long quote: that can cut the hook off the
            # rendered clip. Anchor at the grounded quote start and extend forward.
            quote_start, quote_end = window
            preferred = min(max(min_duration, target_duration), max_duration)
            start = max(0.0, quote_start)
            # Preserve the full grounded quote first. Duration is only a
            # preference; never truncate its conclusion to hit target_duration.
            end = min(total_duration, max(quote_end, start + preferred))
            if end - start > max_duration:
                # Safety cap only: a candidate quote itself must remain intact.
                end = min(total_duration, max(quote_end, start + max_duration))
            if end - start < min_duration:
                end = min(total_duration, start + min_duration)
                if end - start < min_duration:
                    start = max(0.0, end - min_duration)
            if any(_ranges_overlap(start, end, existing.start, existing.end, padding=2.0) for existing in selections):
                continue
            final_duration = end - start
            normalized_score = max(0.0, min(100.0, score))
            pass_tag = "passed" if normalized_score >= score_threshold else "below_threshold"
            selections.append(
                HighlightSelection(
                    start,
                    end,
                    normalized_score,
                    f"{reason} | score_source=llm | threshold={score_threshold} | threshold_result={pass_tag} | requested_range=free-{int(max_duration)}s | actual_duration={round(final_duration, 3)}s",
                    quote,
                    "llm",
                    hook_text=hook_text,
                    clipper_style=clipper_style,
                    style_reason=style_reason,
                    editing_notes=editing_notes,
                    recommended_bgm=[str(x).strip() for x in recommended_bgm if str(x).strip()],
                )
            )
            used_quotes.add(quote_key)
            if normalized_score >= score_threshold:
                llm_accepted += 1
            if len(selections) >= highlight_count:
                break

    if len(selections) < highlight_count:
        fallback_pool = _fallback_highlight_pool(
            transcript_segments,
            total_duration=total_duration,
            target_duration=target_duration,
            min_duration=min_duration,
            max_duration=max_duration,
            highlight_count=highlight_count * 3,
        )
        need_fallback = llm_accepted < highlight_count
        for candidate in fallback_pool:
            if not need_fallback:
                break
            quote_key = _quote_key(candidate.quote)
            if quote_key in used_quotes:
                continue
            if any(_ranges_overlap(candidate.start, candidate.end, existing.start, existing.end, padding=2.0) for existing in selections):
                continue
            candidate.reason = f"{candidate.reason} | score_source=heuristic | threshold={score_threshold} | threshold_result=passed"
            selections.append(candidate)
            used_quotes.add(quote_key)
            if candidate.score >= score_threshold:
                need_fallback = sum(1 for item in selections if item.score >= score_threshold) < highlight_count
            else:
                need_fallback = True
            if len(selections) >= highlight_count:
                break

    if not selections:
        fallback = _heuristic_highlight(transcript_segments, target_duration, min_duration, max_duration, total_duration)
        fallback.reason = f"{fallback.reason} | score_source=heuristic | threshold={score_threshold} | threshold_result=passed"
        selections.append(fallback)

    return _apply_threshold_backoff(
        selections=selections,
        requested_count=highlight_count,
        score_threshold=score_threshold,
        min_output_count=min_output_count,
        threshold_backoff_step=threshold_backoff_step,
        min_score_threshold_floor=min_score_threshold_floor,
    )



def _transcribe_router_chunked(
    client: RouterClient,
    audio_path: Path,
    language: str | None = None,
    prompt: str | None = None,
    chunk_seconds: int = 30,
) -> dict[str, Any]:
    import tempfile

    chunk_seconds = max(15, int(chunk_seconds))
    with tempfile.TemporaryDirectory(prefix="router_chunks_", dir=str(audio_path.parent)) as tmpdir:
        tmpdir_path = Path(tmpdir)
        chunk_pattern = tmpdir_path / "chunk_%05d.mp3"
        run([
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-reset_timestamps",
            "1",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "32k",
            str(chunk_pattern),
        ])

        chunk_paths = sorted(tmpdir_path.glob("chunk_*.mp3"))
        if not chunk_paths:
            raise RouterClientError("Gagal memecah audio menjadi chunk untuk 9router")

        merged_segments: list[dict[str, Any]] = []
        text_parts: list[str] = []
        offset = 0.0
        for index, chunk_path in enumerate(chunk_paths):
            raw = client.transcribe_audio(
                chunk_path,
                language=language or settings.transcription_language or None,
                prompt=prompt if index == 0 else None,
            )
            text = str(raw.get("text", "")).strip()
            if text:
                text_parts.append(text)
            chunk_duration = probe_duration(chunk_path)
            for segment in raw.get("segments", []) or []:
                try:
                    seg_start = float(segment.get("start", 0.0)) + offset
                    seg_end = float(segment.get("end", seg_start)) + offset
                except (TypeError, ValueError, AttributeError):
                    continue
                words_out: list[dict[str, Any]] = []
                for word in segment.get("words", []) or []:
                    try:
                        word_start = float(word.get("start", 0.0)) + offset
                        word_end = float(word.get("end", word_start)) + offset
                        word_text = str(word.get("word", "")).strip()
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if word_text:
                        words_out.append({"word": word_text, "start": word_start, "end": word_end})
                merged_segments.append(
                    {
                        "start": seg_start,
                        "end": seg_end,
                        "text": str(segment.get("text", "")).strip(),
                        "words": words_out,
                    }
                )
            offset += chunk_duration

    return {
        "text": " ".join(text_parts).strip(),
        "segments": merged_segments,
        "source": "router",
        "model": settings.transcription_model,
        "language": language,
    }


def transcribe_audio(
    audio_path: Path,
    router_client: RouterClient | None = None,
    language: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    return _local_whisper_transcribe(audio_path, language=language, prompt=prompt)



def process_video(
    input_path: str,
    output_path: str,
    target_duration: float = 45.0,
    min_duration: float = 1.0,
    max_duration: float = 120.0,
    highlight_count: int = 8,
    score_threshold: float = 70.0,
    min_output_count: int = 3,
    threshold_backoff_step: float = 5.0,
    min_score_threshold_floor: float = 60.0,
    target_resolution: str = "1080x1920",
    fps: int = 30,
    router_client: RouterClient | None = None,
    transcript_override: dict[str, Any] | None = None,
    precomputed_llm_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    in_path = Path(input_path)
    out_path = Path(output_path)
    total_duration = probe_duration(in_path)
    work_audio = out_path.with_suffix(".wav")
    subtitle_path = out_path.with_suffix(".ass")
    target_duration = min(max(0.1, target_duration), total_duration if total_duration > 0 else max_duration)
    min_duration = min(max(0.1, min_duration), total_duration if total_duration > 0 else min_duration)
    # MAX_HIGHLIGHT_DURATION=0 means context-driven/unlimited: only the source
    # duration remains the upper bound. A positive value is an optional safety cap.
    effective_max_duration = total_duration if max_duration <= 0 else max_duration
    max_duration = min(max(min_duration, effective_max_duration), total_duration if total_duration > 0 else effective_max_duration)

    transcript_raw: dict[str, Any] = {"text": "", "segments": [], "source": "skipped"}
    transcript_segments: list[TranscriptSegment] = []
    highlights: list[HighlightSelection] = []
    selection_debug: dict[str, Any] = {
        "requested_count": highlight_count,
        "initial_threshold": score_threshold,
        "effective_threshold": score_threshold,
        "min_output_count": min_output_count,
        "threshold_backoff_step": threshold_backoff_step,
        "min_score_threshold_floor": min_score_threshold_floor,
        "backoff_applied": False,
        "output_count": 0,
    }
    subtitle_info: dict[str, Any] | None = None
    crop_info: CropAnalysis | None = None
    outputs: list[dict[str, Any]] = []

    try:
        if transcript_override:
            transcript_raw = transcript_override
        else:
            extract_audio_track(in_path, work_audio)
            transcript_raw = transcribe_audio(work_audio, router_client=router_client)
        transcript_segments = _parse_transcript_segments(transcript_raw.get("segments", []))
        highlights, selection_debug = select_highlights(
            transcript_segments,
            total_duration=total_duration,
            target_duration=target_duration,
            min_duration=min_duration,
            max_duration=max_duration,
            highlight_count=highlight_count,
            score_threshold=score_threshold,
            min_output_count=min_output_count,
            threshold_backoff_step=threshold_backoff_step,
            min_score_threshold_floor=min_score_threshold_floor,
            router_client=router_client,
            precomputed_llm_results=precomputed_llm_results,
        )

        if not highlights:
            silence_segments = extract_silence_segments(in_path)
            chosen = choose_best_segment(silence_segments, target_duration=max(min_duration, target_duration), total_duration=total_duration)
            chosen_start, chosen_end = _expand_window(
                chosen.start,
                chosen.end,
                total_duration,
                target_duration,
                min_duration,
                max_duration,
            )
            highlights = [HighlightSelection(chosen_start, chosen_end, 0.0, f"Fallback silence-based selection. requested_range=free-{int(max_duration)}s", "", "silence")]

        raw_segments = transcript_raw.get("segments", [])
        for index, highlight in enumerate(highlights, start=1):
            clip_output_path = out_path if index == 1 else out_path.with_name(f"{out_path.stem}_highlight_{index:02d}{out_path.suffix}")
            clip_subtitle_path = subtitle_path if index == 1 else subtitle_path.with_name(f"{subtitle_path.stem}_highlight_{index:02d}{subtitle_path.suffix}")
            if isinstance(raw_segments, list) and raw_segments:
                subtitle_info = build_subtitle_ass(
                    raw_segments=raw_segments,
                    clip_start=highlight.start,
                    clip_end=highlight.end,
                    output_path=clip_subtitle_path,
                    target_resolution=target_resolution,
                    opening_hook_text=highlight.hook_text if highlight.hook_text else " ".join(highlight.quote.split()[:5]),
                    clipper_style=highlight.clipper_style,
                )
            else:
                subtitle_info = {"path": str(clip_subtitle_path), "cue_count": 0, "word_cues": 0}

            clip_duration = highlight.duration if highlight.duration > 0 else min(target_duration, total_duration)
            crop_info = analyze_stable_crop(in_path, highlight.start, clip_duration, target_resolution)
            render_resolution = _adaptive_resolution(target_resolution, crop_info)
            if render_resolution != target_resolution:
                # Recalculate actual crop bounds for the selected canvas rather than
                # stretching a 9:16 crop into the wider two-speaker composition.
                crop_info = analyze_stable_crop(in_path, highlight.start, clip_duration, render_resolution)
            if isinstance(raw_segments, list) and raw_segments:
                subtitle_info = build_subtitle_ass(
                    raw_segments=raw_segments,
                    clip_start=highlight.start,
                    clip_end=highlight.end,
                    output_path=clip_subtitle_path,
                    target_resolution=render_resolution,
                    opening_hook_text=highlight.hook_text if highlight.hook_text else " ".join(highlight.quote.split()[:5]),
                    clipper_style=highlight.clipper_style,
                )
            render_vertical_clip(
                input_path=in_path,
                output_path=clip_output_path,
                start=highlight.start,
                duration=clip_duration,
                target_resolution=render_resolution,
                fps=fps,
                subtitles_path=clip_subtitle_path if subtitle_info and subtitle_info.get("cue_count", 0) > 0 else None,
                crop_analysis=crop_info,
            )
            outputs.append({
                "rank": index,
                "output_path": str(clip_output_path),
                "subtitles": subtitle_info,
                "highlight": {
                    "start": round(highlight.start, 3),
                    "end": round(highlight.end, 3),
                    "duration": round(highlight.duration, 3),
                    "score": round(highlight.score, 2),
                    "reason": highlight.reason,
                    "quote": highlight.quote,
                    "mode": highlight.mode,
                    "hook_text": highlight.hook_text,
                    "clipper_style": highlight.clipper_style,
                    "style_reason": highlight.style_reason,
                    "editing_notes": highlight.editing_notes,
                    "recommended_bgm": highlight.recommended_bgm,
                },
                "crop": {
                    "mode": crop_info.mode,
                    "reason": crop_info.reason,
                    "crop_x": crop_info.crop_x,
                    "crop_y": crop_info.crop_y,
                    "crop_w": crop_info.crop_w,
                    "crop_h": crop_info.crop_h,
                    "face_hits": crop_info.face_hits,
                    "scene_cuts": crop_info.scene_cuts,
                    "samples": crop_info.samples,
                    "aspect_ratio": crop_info.aspect_ratio,
                    "two_person_frames": crop_info.two_person_frames,
                    "render_resolution": render_resolution,
                },
            })

        highlight = highlights[0]
        subtitle_info = outputs[0]["subtitles"] if outputs else {"path": str(subtitle_path), "cue_count": 0, "word_cues": 0}
        crop_info = (
            CropAnalysis(**{key: value for key, value in outputs[0]["crop"].items() if key != "render_resolution"})
            if outputs
            else None
        )
    finally:
        if work_audio.exists():
            work_audio.unlink(missing_ok=True)

    return {
        "input_path": str(in_path),
        "output_path": str(out_path),
        "source_duration": total_duration,
        "target_duration": target_duration,
        "highlight_constraints": {
            "min_duration": min_duration,
            "max_duration": max_duration,
            "preferred_duration": target_duration,
            "requested_count": highlight_count,
            "score_threshold": score_threshold,
            "min_output_count": min_output_count,
            "threshold_backoff_step": threshold_backoff_step,
            "min_score_threshold_floor": min_score_threshold_floor,
            "effective_threshold": selection_debug.get("effective_threshold", score_threshold),
        },
        "selection_debug": selection_debug,
        "transcript": transcript_raw,
        "transcript_segments": len(transcript_segments),
        "subtitles": subtitle_info or {"path": str(subtitle_path), "cue_count": 0, "word_cues": 0},
        "highlight": {
            "start": round(highlight.start if highlight else 0.0, 3),
            "end": round(highlight.end if highlight else min(target_duration, total_duration), 3),
            "duration": round(highlight.duration if highlight else min(target_duration, total_duration), 3),
            "score": round(highlight.score if highlight else 0.0, 2),
            "reason": highlight.reason if highlight else "",
            "quote": highlight.quote if highlight else "",
            "mode": highlight.mode if highlight else "fallback",
            "hook_text": highlight.hook_text if highlight else "",
            "clipper_style": highlight.clipper_style if highlight else "",
            "style_reason": highlight.style_reason if highlight else "",
            "editing_notes": highlight.editing_notes if highlight else "",
            "recommended_bgm": highlight.recommended_bgm if highlight else [],
        },
        "highlights": [item["highlight"] for item in outputs],
        "outputs": outputs,
        "crop": {
            "mode": crop_info.mode if crop_info else "center",
            "reason": crop_info.reason if crop_info else "",
            "crop_x": crop_info.crop_x if crop_info else 0,
            "crop_y": crop_info.crop_y if crop_info else 0,
            "crop_w": crop_info.crop_w if crop_info else 0,
            "crop_h": crop_info.crop_h if crop_info else 0,
            "face_hits": crop_info.face_hits if crop_info else 0,
            "scene_cuts": crop_info.scene_cuts if crop_info else 0,
            "samples": crop_info.samples if crop_info else 0,
        },
    }
