from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis

from shared.router_client import RouterClient, RouterClientError
from shared.settings import settings
from shared.viral_editorial import analyze_viral_hooks, editorial_candidate_previews, editorial_candidates_for_selector
from shared.youtube_transcript import YouTubeTranscriptRateLimited, extract_video_id, fetch_youtube_transcript

JOB_QUEUE = "video_jobs"
APP_ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_HELPER = APP_ROOT / "scripts" / "download_youtube_hd.py"
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
TEXT_ARTIFACT_SUFFIXES = {".ass": "text/plain; charset=utf-8", ".srt": "text/plain; charset=utf-8", ".vtt": "text/vtt; charset=utf-8"}

app = FastAPI(title="AI Video Clipper VPS")
app.mount("/ui", StaticFiles(directory=str(APP_ROOT / "ui"), html=True), name="ui")
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
router_client = RouterClient()


def _decode_json_field(data: dict[str, str], key: str, default=None):
    raw = data.get(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _load_outputs(data: dict[str, str]) -> list[dict]:
    outputs = _decode_json_field(data, "outputs_json", [])
    return outputs if isinstance(outputs, list) else []


def _load_candidate_previews(data: dict[str, str]) -> list[dict]:
    previews = _decode_json_field(data, "candidate_preview_json", [])
    return previews if isinstance(previews, list) else []


def _pick_output_by_rank(data: dict[str, str], rank: int) -> dict | None:
    if rank < 1:
        return None
    for item in _load_outputs(data):
        if int(item.get("rank", 0)) == rank:
            return item
    return None


def _bundle_outputs_zip(job_id: str, outputs: list[dict]) -> Path:
    bundle_path = settings.video_dir / f"{job_id}_outputs.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = []
        for item in outputs:
            rank = int(item.get("rank", 0))
            output_path = Path(str(item.get("output_path", "")))
            subtitle_path = Path(str((item.get("subtitles") or {}).get("path", "")))
            if output_path.exists() and output_path.is_file():
                zf.write(output_path, arcname=f"highlight_{rank:02d}{output_path.suffix.lower()}")
            if subtitle_path.exists() and subtitle_path.is_file():
                zf.write(subtitle_path, arcname=f"highlight_{rank:02d}{subtitle_path.suffix.lower()}")
            manifest.append({
                "rank": rank,
                "output_path": str(output_path),
                "subtitle_path": str(subtitle_path),
                "highlight": item.get("highlight", {}),
            })
        zf.writestr("manifest.json", json.dumps({"job_id": job_id, "outputs": manifest}, ensure_ascii=False, indent=2))
    return bundle_path


def ensure_dirs() -> None:
    for directory in (settings.work_dir, settings.video_dir, settings.log_dir, settings.cache_dir):
        directory.mkdir(parents=True, exist_ok=True)


def newest_video_file(paths: list[Path]) -> Path | None:
    candidates = [path for path in paths if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def download_youtube_source(url: str, destination_dir: Path, cookies_from_browser: str | None) -> Path:
    if not YOUTUBE_HELPER.exists():
        raise HTTPException(status_code=500, detail="youtube HD helper script missing")
    cmd = [sys.executable, str(YOUTUBE_HELPER), "--output-dir", str(destination_dir)]
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    cmd.append(url)
    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"youtube download failed with exit code {result.returncode}"
        raise HTTPException(status_code=502, detail=detail[:1200])
    downloaded = newest_video_file(list(destination_dir.iterdir()))
    if not downloaded:
        raise HTTPException(status_code=500, detail="youtube helper finished but no video file was found")
    return downloaded


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/router/config")
def router_config() -> dict[str, object]:
    return router_client.config()


@app.get("/router/ping")
def router_ping() -> dict[str, object]:
    try:
        return router_client.ping()
    except Exception as exc:
        return JSONResponse(status_code=502, content={"ok": False, "error": str(exc)})


@app.post("/jobs")
async def create_job(
    file: UploadFile | None = File(default=None),
    youtube_url: str | None = Form(default=None),
    target_duration: float = Form(default=settings.target_duration),
    target_duration_min: float = Form(default=settings.min_highlight_duration),
    target_duration_max: float = Form(default=settings.max_highlight_duration),
    highlight_count: int = Form(default=settings.highlight_count),
    highlight_score_threshold: float = Form(default=settings.highlight_score_threshold),
    min_output_count: int = Form(default=settings.min_output_count),
    threshold_backoff_step: float = Form(default=settings.threshold_backoff_step),
    min_score_threshold_floor: float = Form(default=settings.min_score_threshold_floor),
    cookies_from_browser: str | None = Form(default=None),
    prefer_youtube_transcript: bool = Form(default=True),
    build_mode: str = Form(default="first_only"),
):
    ensure_dirs()
    if file is None and not youtube_url:
        raise HTTPException(status_code=400, detail="provide either file or youtube_url")
    if file is not None and youtube_url:
        raise HTTPException(status_code=400, detail="provide only one source: file or youtube_url")

    build_mode = build_mode.strip().lower()
    if build_mode not in {"first_only", "sequential_all"}:
        raise HTTPException(status_code=400, detail="build_mode must be one of: first_only, sequential_all")

    if target_duration_min <= 0:
        raise HTTPException(status_code=400, detail="target_duration_min must be > 0")
    # target_duration_max=0 is context-driven: no artificial cap.
    if target_duration_max < 0:
        raise HTTPException(status_code=400, detail="target_duration_max must be >= 0")
    if target_duration_max > 0 and target_duration_min > target_duration_max:
        raise HTTPException(status_code=400, detail="target_duration_min must be <= target_duration_max")
    if highlight_count <= 0 or highlight_count > 20:
        raise HTTPException(status_code=400, detail="highlight_count must be between 1 and 20")
    if highlight_score_threshold < 0:
        raise HTTPException(status_code=400, detail="highlight_score_threshold must be >= 0")
    if min_output_count <= 0 or min_output_count > highlight_count:
        raise HTTPException(status_code=400, detail="min_output_count must be between 1 and highlight_count")
    if threshold_backoff_step <= 0:
        raise HTTPException(status_code=400, detail="threshold_backoff_step must be > 0")
    if min_score_threshold_floor < 0 or min_score_threshold_floor > highlight_score_threshold:
        raise HTTPException(status_code=400, detail="min_score_threshold_floor must be between 0 and highlight_score_threshold")
    if target_duration_max > 0:
        target_duration = min(max(target_duration, target_duration_min), target_duration_max)
    else:
        target_duration = max(target_duration, target_duration_min)

    job_id = uuid4().hex
    job_dir = settings.work_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    output_path = settings.video_dir / f"{job_id}.mp4"

    source_kind = "upload"
    source_ref = ""
    transcript_override: dict[str, object] | None = None
    transcript_source = ""
    if file is not None:
        source_ref = file.filename or "input.mp4"
        if prefer_youtube_transcript:
            candidate_video_id = extract_video_id(source_ref)
            if candidate_video_id and len(candidate_video_id) == 11:
                try:
                    fetched = fetch_youtube_transcript(
                        candidate_video_id,
                        settings.youtube_transcript_languages,
                        cookies_from_browser=cookies_from_browser or "",
                        cache_dir=settings.cache_dir,
                        proxy=settings.youtube_proxy,
                    )
                    transcript_override = {
                        "text": fetched.full_text,
                        "segments": fetched.segments,
                        "language": fetched.language,
                        "video_id": fetched.video_id,
                        "source": fetched.source,
                    }
                    transcript_source = fetched.source
                except Exception as exc:
                    transcript_source = f"fallback_local_asr:{exc}"
    viral_analysis: dict[str, object] | None = None
    viral_analysis_error = ""
    candidate_previews: list[dict[str, object]] = []
    if youtube_url:
        source_kind = "youtube"
        source_ref = youtube_url
        if prefer_youtube_transcript:
            try:
                fetched = fetch_youtube_transcript(
                    youtube_url,
                    settings.youtube_transcript_languages,
                    cookies_from_browser=cookies_from_browser or "",
                    cache_dir=settings.cache_dir,
                    proxy=settings.youtube_proxy,
                )
                transcript_override = {
                    "text": fetched.full_text,
                    "segments": fetched.segments,
                    "language": fetched.language,
                    "video_id": fetched.video_id,
                    "source": fetched.source,
                }
                transcript_source = fetched.source
                (job_dir / "transcript.json").write_text(json.dumps(transcript_override, ensure_ascii=False, indent=2), encoding="utf-8")
            except YouTubeTranscriptRateLimited as exc:
                # Preserve transcript quality: a rate-limited caption endpoint must
                # not silently cause a local-ASR transcript substitution.
                raise HTTPException(
                    status_code=503,
                    detail=f"YouTube captions are rate-limited; retry later without ASR fallback: {exc}",
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"YouTube transcript retrieval failed; job was not queued and ASR fallback is disabled: {exc}",
                ) from exc

        # After captions are fetched, Gemini editorial analysis and HD media download
        # deliberately run concurrently. Both artifacts are persisted before queueing.
        download_dir = job_dir / "download"
        download_dir.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="youtube-ingest") as pool:
            download_future = pool.submit(download_youtube_source, youtube_url, download_dir, cookies_from_browser)
            analysis_future = None
            if transcript_override and settings.router_ready:
                analysis_future = pool.submit(
                    analyze_viral_hooks,
                    RouterClient(),
                    str(transcript_override["text"]),
                    target_duration=target_duration,
                    min_duration=target_duration_min,
                    max_duration=target_duration_max,
                    candidate_count=highlight_count,
                )
            downloaded = download_future.result()
            if analysis_future:
                try:
                    viral_analysis = analysis_future.result()
                    candidate_previews = editorial_candidate_previews(viral_analysis)
                    (job_dir / "viral-analysis.json").write_text(json.dumps(viral_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
                    (job_dir / "candidate-previews.json").write_text(json.dumps(candidate_previews, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as exc:
                    viral_analysis_error = str(exc)

        input_path = job_dir / downloaded.name
        if input_path.exists():
            input_path.unlink()
        shutil.move(str(downloaded), str(input_path))
        shutil.rmtree(download_dir, ignore_errors=True)
    else:
        input_filename = file.filename or "input.mp4"
        input_path = job_dir / input_filename
        with input_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        source_ref = input_filename

    now = str(time.time())
    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "input_path": str(input_path),
            "output_path": str(output_path),
            "filename": Path(source_ref).name if source_kind == "upload" else Path(input_path).name,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "target_duration": str(target_duration),
            "target_duration_min": str(target_duration_min),
            "target_duration_max": str(target_duration_max),
            "highlight_count": str(highlight_count),
            "highlight_score_threshold": str(highlight_score_threshold),
            "min_output_count": str(min_output_count),
            "threshold_backoff_step": str(threshold_backoff_step),
            "min_score_threshold_floor": str(min_score_threshold_floor),
            "prefer_youtube_transcript": str(prefer_youtube_transcript),
            "transcript_source": transcript_source,
            "transcript_override_json": json.dumps(transcript_override, ensure_ascii=False) if transcript_override else "",
            "viral_analysis_json": json.dumps(viral_analysis, ensure_ascii=False) if viral_analysis else "",
            "candidate_preview_json": json.dumps(candidate_previews, ensure_ascii=False) if candidate_previews else "",
            "candidate_preview_path": str(job_dir / "candidate-previews.json") if candidate_previews else "",
            "viral_analysis_path": str(job_dir / "viral-analysis.json") if viral_analysis else "",
            "viral_analysis_error": viral_analysis_error,
            "build_mode": build_mode,
            "next_rank": "1",
            "ingestion_mode": "parallel_transcript_gemini_download" if youtube_url else "upload",
        },
    )
    redis_client.lpush(JOB_QUEUE, job_id)
    return {
        "job_id": job_id,
        "status": "queued",
        "target_duration": target_duration,
        "target_duration_min": target_duration_min,
        "target_duration_max": target_duration_max,
        "highlight_count": highlight_count,
        "highlight_score_threshold": highlight_score_threshold,
        "min_output_count": min_output_count,
        "threshold_backoff_step": threshold_backoff_step,
        "min_score_threshold_floor": min_score_threshold_floor,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "transcript_source": transcript_source,
        "prefer_youtube_transcript": prefer_youtube_transcript,
        "build_mode": build_mode,
        "candidate_previews": candidate_previews,
        "next_rank": 1,
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})

    response = dict(data)
    if response.get("transcript_override_json"):
        response["transcript_override_json"] = "<stored>"

    heartbeat_at = data.get("heartbeat_at")
    heartbeat_stale = None
    if heartbeat_at:
        try:
            heartbeat_age = max(0.0, time.time() - float(heartbeat_at))
            response["heartbeat_age_seconds"] = round(heartbeat_age, 1)
            heartbeat_stale = heartbeat_age > settings.worker_heartbeat_stale_seconds
            response["heartbeat_stale"] = heartbeat_stale
        except ValueError:
            response["heartbeat_stale"] = None
    elif data.get("status") == "processing":
        response["heartbeat_stale"] = True

    candidate_previews = _load_candidate_previews(data)
    if candidate_previews:
        response["candidate_previews"] = candidate_previews

    result = _decode_json_field(data, "result_json")
    if isinstance(result, dict):
        response["result"] = result
        selection_debug = result.get("selection_debug")
        if selection_debug is not None:
            response["selection_debug"] = selection_debug
        highlight_constraints = result.get("highlight_constraints")
        if highlight_constraints is not None:
            response["highlight_constraints"] = highlight_constraints
            effective_threshold = highlight_constraints.get("effective_threshold")
            if effective_threshold is not None:
                response["effective_threshold"] = effective_threshold

    return response


@app.get("/jobs/{job_id}/transcript")
def get_job_transcript(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})
    transcript = data.get("transcript_json")
    if transcript:
        return {"job_id": job_id, "transcript": json.loads(transcript)}
    transcript_override_raw = data.get("transcript_override_json")
    if transcript_override_raw:
        return {"job_id": job_id, "transcript": json.loads(transcript_override_raw)}
    return {"job_id": job_id, "transcript": None}


@app.get("/jobs/{job_id}/candidates")
def get_job_candidates(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})
    return {
        "job_id": job_id,
        "build_mode": data.get("build_mode", "first_only"),
        "next_rank": int(data.get("next_rank", "1") or "1"),
        "candidate_previews": _load_candidate_previews(data),
        "outputs": _load_outputs(data),
    }


@app.post("/jobs/{job_id}/build-next")
def build_next_candidate(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})
    if data.get("status") == "processing":
        return JSONResponse(status_code=409, content={"detail": "job is currently processing"})
    candidate_previews = _load_candidate_previews(data)
    if not candidate_previews:
        return JSONResponse(status_code=404, content={"detail": "candidate previews not available"})
    outputs = _load_outputs(data)
    next_rank = max(1, int(data.get("next_rank", "1") or "1"))
    built_ranks = {int(item.get("rank", 0)) for item in outputs}
    while next_rank in built_ranks and next_rank <= len(candidate_previews):
        next_rank += 1
    if next_rank > len(candidate_previews):
        return JSONResponse(status_code=409, content={"detail": "all candidate previews have already been built"})
    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "status": "queued",
            "updated_at": str(time.time()),
            "progress_stage": "queued_next_rank",
            "progress_detail": f"queued rank {next_rank} for sequential build",
            "next_rank": str(next_rank),
        },
    )
    redis_client.lpush(JOB_QUEUE, job_id)
    return {
        "job_id": job_id,
        "status": "queued",
        "queued_rank": next_rank,
        "candidate": candidate_previews[next_rank - 1],
        "already_built_ranks": sorted(built_ranks),
    }


@app.get("/jobs/{job_id}/highlight")
def get_job_highlight(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})

    result = _decode_json_field(data, "result_json", {})
    highlight_constraints = result.get("highlight_constraints") if isinstance(result, dict) else None
    selection_debug = result.get("selection_debug") if isinstance(result, dict) else None
    effective_threshold = None
    if isinstance(highlight_constraints, dict):
        effective_threshold = highlight_constraints.get("effective_threshold")

    highlights = _decode_json_field(data, "highlights_json")
    if isinstance(highlights, list):
        return {
            "job_id": job_id,
            "highlights": highlights,
            "selection_debug": selection_debug,
            "highlight_constraints": highlight_constraints,
            "effective_threshold": effective_threshold,
        }

    highlight = _decode_json_field(data, "highlight_json")
    if highlight is None:
        return {
            "job_id": job_id,
            "highlight": None,
            "selection_debug": selection_debug,
            "highlight_constraints": highlight_constraints,
            "effective_threshold": effective_threshold,
        }
    return {
        "job_id": job_id,
        "highlight": highlight,
        "selection_debug": selection_debug,
        "highlight_constraints": highlight_constraints,
        "effective_threshold": effective_threshold,
    }


@app.get("/jobs/{job_id}/subtitles")
def get_job_subtitles(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})
    subtitles = data.get("subtitles_json")
    if not subtitles:
        return {"job_id": job_id, "subtitles": None}
    return {"job_id": job_id, "subtitles": json.loads(subtitles)}


@app.get("/jobs/{job_id}/crop")
def get_job_crop(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})
    crop = data.get("crop_json")
    if not crop:
        return {"job_id": job_id, "crop": None}
    return {"job_id": job_id, "crop": json.loads(crop)}


@app.get("/jobs/{job_id}/artifact/{kind}")
def download_job_artifact(job_id: str, kind: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})

    kind_normalized = kind.strip().lower()
    artifact_path: Path | None = None
    media_type: str | None = None
    filename: str | None = None

    if kind_normalized == "video":
        output_path = data.get("output_path")
        if not output_path:
            return JSONResponse(status_code=404, content={"detail": "video artifact not available"})
        artifact_path = Path(output_path)
        media_type = "video/mp4"
        filename = f"{job_id}.mp4"
    elif kind_normalized == "subtitles":
        subtitles_raw = data.get("subtitles_json")
        if not subtitles_raw:
            return JSONResponse(status_code=404, content={"detail": "subtitle artifact not available"})
        subtitles = json.loads(subtitles_raw)
        subtitle_path = subtitles.get("path")
        if not subtitle_path:
            return JSONResponse(status_code=404, content={"detail": "subtitle artifact not available"})
        artifact_path = Path(str(subtitle_path))
        media_type = TEXT_ARTIFACT_SUFFIXES.get(artifact_path.suffix.lower(), "application/octet-stream")
        filename = f"{job_id}{artifact_path.suffix.lower() or '.txt'}"
    elif kind_normalized == "outputs":
        outputs = _load_outputs(data)
        if not outputs:
            return JSONResponse(status_code=404, content={"detail": "output artifacts not available"})
        return {"job_id": job_id, "outputs": outputs}
    elif kind_normalized == "bundle":
        outputs = _load_outputs(data)
        if not outputs:
            return JSONResponse(status_code=404, content={"detail": "output artifacts not available"})
        artifact_path = _bundle_outputs_zip(job_id, outputs)
        media_type = "application/zip"
        filename = f"{job_id}_outputs.zip"
    else:
        return JSONResponse(status_code=400, content={"detail": "unsupported artifact kind; use video, subtitles, outputs, or bundle"})

    if not artifact_path.exists() or not artifact_path.is_file():
        return JSONResponse(status_code=404, content={"detail": "artifact file missing"})

    return FileResponse(path=artifact_path, media_type=media_type, filename=filename)


@app.get("/jobs/{job_id}/artifact/{kind}/{rank}")
def download_ranked_job_artifact(job_id: str, kind: str, rank: int):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        return JSONResponse(status_code=404, content={"detail": "job not found"})
    
    original_filename = data.get("filename") or data.get("source_ref") or job_id
    if original_filename.startswith("http"):
        original_filename = original_filename.split("v=")[-1] if "v=" in original_filename else original_filename.split("/")[-1]
    import re
    safe_title = re.sub(r'[^a-zA-Z0-9_\-\s]', '', original_filename).strip()
    safe_title = safe_title[:50] 
    
    output = _pick_output_by_rank(data, rank)
    if not output:
        return JSONResponse(status_code=404, content={"detail": "ranked output not found"})

    kind_normalized = kind.strip().lower()
    if kind_normalized == "video":
        artifact_path = Path(str(output.get("output_path", "")))
        media_type = "video/mp4"
        filename = f"{safe_title}_Rank_{rank}.mp4"
    elif kind_normalized == "subtitles":
        subtitle_path = str((output.get("subtitles") or {}).get("path", ""))
        artifact_path = Path(subtitle_path)
        media_type = TEXT_ARTIFACT_SUFFIXES.get(artifact_path.suffix.lower(), "application/octet-stream")
        filename = f"{safe_title}_Rank_{rank}{artifact_path.suffix.lower() or '.txt'}"
    else:
        return JSONResponse(status_code=400, content={"detail": "unsupported artifact kind; use video or subtitles"})

    if not artifact_path.exists() or not artifact_path.is_file():
        return JSONResponse(status_code=404, content={"detail": "artifact file missing"})

    return FileResponse(path=artifact_path, media_type=media_type, filename=filename)


@app.get("/jobs")
def list_jobs(limit: int = 20):
    items = []
    for key in redis_client.scan_iter(match="job:*"):
        items.append(redis_client.hgetall(key))
    items = sorted(items, key=lambda x: x.get("created_at", "0"), reverse=True)
    return {"items": items[:limit]}
