from __future__ import annotations

import json
import multiprocessing
import os
import signal
import time
from pathlib import Path

from redis import Redis

from shared.pipeline import process_video
from shared.router_client import RouterClient
from shared.settings import settings

JOB_QUEUE = "video_jobs"
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
router_client = RouterClient()


class JobTimeoutError(RuntimeError):
    pass


def update_job(job_id: str, **fields) -> None:
    fields["updated_at"] = str(time.time())
    redis_client.hset(f"job:{job_id}", mapping={k: str(v) for k, v in fields.items()})


def _job_paths(job_id: str) -> tuple[Path, Path | None, bool, bool]:
    output_path_raw = redis_client.hget(f"job:{job_id}", "output_path") or ""
    output_path = Path(output_path_raw) if output_path_raw else None
    wav_path = output_path.with_suffix(".wav") if output_path else None
    output_exists = output_path.exists() if output_path else False
    wav_exists = wav_path.exists() if wav_path else False
    return output_path or Path(), wav_path, output_exists, wav_exists


def _run_job_child(job_id: str) -> None:
    job = redis_client.hgetall(f"job:{job_id}")
    if not job:
        return

    input_path = job["input_path"]
    output_path = job["output_path"]
    target_duration = float(job.get("target_duration", settings.target_duration))
    target_duration_min = float(job.get("target_duration_min", settings.min_highlight_duration))
    target_duration_max = float(job.get("target_duration_max", settings.max_highlight_duration))
    highlight_count = int(job.get("highlight_count", settings.highlight_count))
    highlight_score_threshold = float(job.get("highlight_score_threshold", settings.highlight_score_threshold))
    min_output_count = int(job.get("min_output_count", settings.min_output_count))
    threshold_backoff_step = float(job.get("threshold_backoff_step", settings.threshold_backoff_step))
    min_score_threshold_floor = float(job.get("min_score_threshold_floor", settings.min_score_threshold_floor))

    transcript_override = None
    transcript_raw = job.get("transcript_override_json")
    if transcript_raw:
        transcript_override = json.loads(transcript_raw)
        update_job(job_id, progress_stage="transcript_override_loaded", progress_detail="using stored transcript override", progress_updated_at=str(time.time()))
    else:
        update_job(job_id, progress_stage="transcription_expected", progress_detail="pipeline will extract audio and transcribe", progress_updated_at=str(time.time()))

    precomputed_llm_results = None
    candidate_previews = []
    viral_analysis_raw = job.get("viral_analysis_json")
    if viral_analysis_raw:
        try:
            from shared.viral_editorial import editorial_candidate_previews, editorial_candidates_for_selector
            parsed_analysis = json.loads(viral_analysis_raw)
            precomputed_llm_results = editorial_candidates_for_selector(parsed_analysis)
            candidate_previews = editorial_candidate_previews(parsed_analysis)
            update_job(job_id, progress_stage="viral_analysis_loaded", progress_detail=f"using {len(precomputed_llm_results)} persisted Gemini candidates", progress_updated_at=str(time.time()))
        except Exception as exc:
            update_job(job_id, viral_analysis_load_error=str(exc))

    input_file = Path(input_path)
    output_file = Path(output_path)
    wav_path = output_file.with_suffix(".wav")
    if wav_path.exists():
        wav_path.unlink()

    build_mode = str(job.get("build_mode", "first_only") or "first_only").strip().lower()
    next_rank = max(1, int(job.get("next_rank", "1") or "1"))
    if build_mode not in {"first_only", "sequential_all"}:
        build_mode = "first_only"
    requested_highlight_count = highlight_count
    build_all = build_mode == "sequential_all" and next_rank == 1
    previous_outputs_raw = job.get("outputs_json", "")
    try:
        previous_outputs = json.loads(previous_outputs_raw) if previous_outputs_raw else []
    except json.JSONDecodeError:
        previous_outputs = []
    if not isinstance(previous_outputs, list):
        previous_outputs = []

    # Review mode must render exactly one requested Gemini candidate at a time.
    # Do not select the top N again, because that would silently rerender rank 1
    # every time the operator queues rank 2, rank 3, and so on.
    run_llm_results = precomputed_llm_results
    run_output_path = output_path
    if not build_all and precomputed_llm_results:
        candidate_index = next_rank - 1
        if candidate_index >= len(precomputed_llm_results):
            raise JobTimeoutError(f"requested candidate rank {next_rank} is unavailable")
        run_llm_results = [precomputed_llm_results[candidate_index]]
        if next_rank > 1:
            output_suffix = Path(output_path).suffix
            run_output_path = str(Path(output_path).with_name(f"{Path(output_path).stem}_highlight_{next_rank:02d}{output_suffix}"))
    effective_highlight_count = requested_highlight_count if build_all else 1

    update_job(
        job_id,
        progress_detail=f"input_ready:{input_file.name} | build_mode={build_mode} | next_rank={next_rank}",
        progress_updated_at=str(time.time()),
    )

    try:
        result = process_video(
            input_path=input_path,
            output_path=run_output_path,
            target_duration=target_duration,
            min_duration=target_duration_min,
            max_duration=target_duration_max,
            highlight_count=effective_highlight_count,
            score_threshold=highlight_score_threshold,
            min_output_count=min_output_count,
            threshold_backoff_step=threshold_backoff_step,
            min_score_threshold_floor=min_score_threshold_floor,
            target_resolution=settings.output_resolution,
            fps=settings.output_fps,
            router_client=router_client,
            transcript_override=transcript_override,
            precomputed_llm_results=run_llm_results,
        )
        update_job(job_id, progress_stage="artifacts_verification", progress_detail="checking final output files", progress_updated_at=str(time.time()))
        primary_output = result.get("output_path", output_path)
        primary_output_exists = Path(str(primary_output)).exists()
        if not primary_output_exists:
            raise JobTimeoutError(f"pipeline returned without output artifact: {primary_output}")
        new_outputs = result.get("outputs", []) if isinstance(result.get("outputs"), list) else []
        if build_all:
            outputs = new_outputs
        else:
            for item in new_outputs:
                item["rank"] = next_rank
            outputs = [item for item in previous_outputs if int(item.get("rank", 0)) != next_rank] + new_outputs
            outputs.sort(key=lambda item: int(item.get("rank", 0)))
        built_ranks = sorted(int(item.get("rank", 0)) for item in outputs if int(item.get("rank", 0)) > 0)
        next_rank_after = (max(built_ranks) + 1) if built_ranks else (next_rank + 1)
        total_candidates = len(candidate_previews) if candidate_previews else requested_highlight_count
        pending_candidates = max(0, total_candidates - len(outputs))
        progress_detail = "job finished successfully"
        if build_mode == "first_only":
            progress_detail = f"built rank {built_ranks[-1] if built_ranks else 1}; {pending_candidates} candidate(s) still preview-only"
        update_job(
            job_id,
            status="completed",
            result_json=json.dumps(result, ensure_ascii=False),
            transcript_json=json.dumps(result.get("transcript", {}), ensure_ascii=False),
            highlight_json=json.dumps(result.get("highlight", {}), ensure_ascii=False),
            highlights_json=json.dumps(result.get("highlights", []), ensure_ascii=False),
            subtitles_json=json.dumps(result.get("subtitles", {}), ensure_ascii=False),
            outputs_json=json.dumps(outputs, ensure_ascii=False),
            crop_json=json.dumps(result.get("crop", {}), ensure_ascii=False),
            candidate_preview_json=json.dumps(candidate_previews, ensure_ascii=False) if candidate_previews else job.get("candidate_preview_json", ""),
            next_rank=str(next_rank_after),
            built_ranks_json=json.dumps(built_ranks, ensure_ascii=False),
            pending_candidate_count=str(pending_candidates),
            output_exists=primary_output_exists,
            heartbeat_status="completed",
            progress_stage="completed",
            progress_detail=progress_detail,
            progress_updated_at=str(time.time()),
        )
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc), heartbeat_status="failed", progress_stage="failed", progress_detail=str(exc), progress_updated_at=str(time.time()))
        raise


def _terminate_process_tree(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + settings.worker_force_kill_grace_seconds
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def process_job(job_id: str) -> None:
    job = redis_client.hgetall(f"job:{job_id}")
    if not job:
        return

    now = time.time()
    update_job(
        job_id,
        status="processing",
        heartbeat_at=str(now),
        progress_stage="starting",
        progress_detail="spawning isolated job child",
        progress_started_at=str(now),
        progress_updated_at=str(now),
        guard_timeout_seconds=str(settings.worker_stage_timeout_seconds),
        guard_max_runtime_seconds=str(settings.worker_max_runtime_seconds),
        heartbeat_status="running",
        worker_pid=str(os.getpid()),
    )

    child = multiprocessing.Process(target=_run_job_child, args=(job_id,), daemon=False)
    child.start()
    child_pid = child.pid or 0
    started_at = time.time()
    stage_started_at = started_at
    last_stage = redis_client.hget(f"job:{job_id}", "progress_stage") or "starting"
    update_job(job_id, child_pid=str(child_pid), progress_stage=last_stage)

    timed_out = False
    timeout_reason = ""

    while child.is_alive():
        time.sleep(settings.worker_heartbeat_interval_seconds)
        if not child.is_alive():
            break
        current = redis_client.hgetall(f"job:{job_id}")
        stage = current.get("progress_stage") or last_stage
        if stage != last_stage:
            last_stage = stage
            stage_started_at = time.time()
        now = time.time()
        runtime_age = now - started_at
        stage_age = now - stage_started_at
        _, _, output_exists, wav_exists = _job_paths(job_id)
        update_job(
            job_id,
            heartbeat_at=str(now),
            heartbeat_status="running",
            progress_stage=stage,
            progress_stage_age_seconds=f"{stage_age:.1f}",
            runtime_age_seconds=f"{runtime_age:.1f}",
            worker_alive="True",
            child_pid=str(child_pid),
            child_alive="True",
            wav_exists=str(wav_exists),
            output_exists=str(output_exists),
        )
        if stage_age > settings.worker_stage_timeout_seconds or runtime_age > settings.worker_max_runtime_seconds:
            timed_out = True
            timeout_reason = f"job guard timeout: stage='{stage}' age={stage_age:.1f}s runtime={runtime_age:.1f}s output_exists={output_exists} wav_exists={wav_exists}"
            update_job(job_id, status="failing", heartbeat_status="timeout", error=timeout_reason, progress_detail="terminating stuck child process")
            _terminate_process_tree(child_pid)
            child.join(timeout=15)
            break

    child.join(timeout=1)
    current = redis_client.hgetall(f"job:{job_id}")
    _, _, output_exists, wav_exists = _job_paths(job_id)

    if timed_out:
        update_job(
            job_id,
            status="failed",
            error=timeout_reason,
            heartbeat_status="timeout",
            child_alive="False",
            wav_exists=str(wav_exists),
            output_exists=str(output_exists),
            progress_stage="timeout",
            progress_detail="stuck child process terminated",
        )
        return

    if child.exitcode not in (0, None) and current.get("status") not in {"failed", "completed"}:
        update_job(
            job_id,
            status="failed",
            error=f"job child exited with code {child.exitcode}",
            heartbeat_status="failed",
            child_alive="False",
            wav_exists=str(wav_exists),
            output_exists=str(output_exists),
        )
        return

    if current.get("status") == "processing":
        update_job(
            job_id,
            status="failed",
            error="job child exited without terminal status",
            heartbeat_status="failed",
            child_alive="False",
            wav_exists=str(wav_exists),
            output_exists=str(output_exists),
        )
        return

    update_job(job_id, child_alive="False", worker_alive="True", wav_exists=str(wav_exists), output_exists=str(output_exists))


def main() -> None:
    for directory in (settings.video_dir, settings.work_dir, settings.log_dir, settings.cache_dir):
        directory.mkdir(parents=True, exist_ok=True)
    while True:
        item = redis_client.brpop(JOB_QUEUE, timeout=5)
        if not item:
            continue
        _, job_id = item
        process_job(job_id)


if __name__ == "__main__":
    main()
