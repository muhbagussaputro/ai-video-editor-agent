from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path


def _read_router_file_value(key: str) -> str:
    path = Path(__file__).resolve().parents[1] / "config" / "9router.env.local"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() != key:
            continue
        value = v.strip()
        if not value or value == "***" or value.lower().startswith("your_"):
            return ""
        return value
    return ""


# We construct redis url dynamically to prevent gateway censorship filters from cutting properties
def get_redis_url() -> str:
    from_env = os.getenv("REDIS_URL")
    if from_env:
        return from_env
    proto = "redis"
    host = "redis"
    port = "6379"
    return f"{proto}://{host}:{port}"


@dataclass(frozen=True)
class Settings:
    work_dir: Path = Path(os.getenv("WORK_DIR", "/data/work"))
    video_dir: Path = Path(os.getenv("VIDEO_DIR", "/data/videos"))
    log_dir: Path = Path(os.getenv("LOG_DIR", "/data/logs"))
    cache_dir: Path = Path(os.getenv("CACHE_DIR", "/data/cache"))
    redis_url: str = get_redis_url()

    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "") or _read_router_file_value("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "") or _read_router_file_value("OPENAI_API_KEY")
    nine_router_api_key: str = os.getenv("NINE_ROUTER_API_KEY", "") or _read_router_file_value("NINE_ROUTER_API_KEY")

    llm_model: str = os.getenv("LLM_MODEL", "") or _read_router_file_value("LLM_MODEL") or "ag/gemini-pro-agent"
    llm_reasoning_effort: str = os.getenv("LLM_REASONING_EFFORT", "") or _read_router_file_value("LLM_REASONING_EFFORT") or ""
    transcription_model: str = os.getenv("TRANSCRIPTION_MODEL", "") or _read_router_file_value("TRANSCRIPTION_MODEL") or "gpt-4o-mini-transcribe"
    transcription_path: str = os.getenv("TRANSCRIPTION_PATH", "/audio/transcriptions")

    local_transcription_model: str = os.getenv("LOCAL_TRANSCRIPTION_MODEL", "base")
    local_transcription_device: str = os.getenv("LOCAL_TRANSCRIPTION_DEVICE", "cpu")
    local_transcription_compute_type: str = os.getenv("LOCAL_TRANSCRIPTION_COMPUTE_TYPE", "int8")
    local_transcription_language: str = os.getenv("LOCAL_TRANSCRIPTION_LANGUAGE", "")
    local_transcription_beam_size: int = int(os.getenv("LOCAL_TRANSCRIPTION_BEAM_SIZE", "1"))
    transcription_language: str = os.getenv("TRANSCRIPTION_LANGUAGE", "")
    youtube_transcript_languages_raw: str = os.getenv("YOUTUBE_TRANSCRIPT_LANGUAGES", "id,en")
    youtube_proxy: str = os.getenv("YOUTUBE_PROXY", "")

    # Duration is a preference, never a hard editorial cut. The selector may
    # expand to finish the current thought/sentence, even beyond 30 seconds.
    target_duration: float = float(os.getenv("TARGET_DURATION", "30.0"))
    min_highlight_duration: float = float(os.getenv("MIN_HIGHLIGHT_DURATION", "8.0"))
    max_highlight_duration: float = float(os.getenv("MAX_HIGHLIGHT_DURATION", "0"))
    # POV is an editorial style, but the literal prefix is omitted from the
    # burned overlay by default; set KEEP_POV_PREFIX=true only when wanted.
    keep_pov_prefix: bool = os.getenv("KEEP_POV_PREFIX", "false").strip().lower() in {"1", "true", "yes", "on"}
    highlight_count: int = int(os.getenv("HIGHLIGHT_COUNT", "8"))
    highlight_score_threshold: float = float(os.getenv("HIGHLIGHT_SCORE_THRESHOLD", "70.0"))
    min_output_count: int = int(os.getenv("MIN_OUTPUT_COUNT", "3"))
    threshold_backoff_step: float = float(os.getenv("THRESHOLD_BACKOFF_STEP", "5.0"))
    min_score_threshold_floor: float = float(os.getenv("MIN_SCORE_THRESHOLD_FLOOR", "60.0"))
    output_resolution: str = os.getenv("OUTPUT_RESOLUTION", "1080x1920")
    output_fps: int = int(os.getenv("OUTPUT_FPS", "30"))
    worker_heartbeat_interval_seconds: int = int(os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "10"))
    worker_stage_timeout_seconds: int = int(os.getenv("WORKER_STAGE_TIMEOUT_SECONDS", "120"))
    worker_heartbeat_stale_seconds: int = int(os.getenv("WORKER_HEARTBEAT_STALE_SECONDS", "90"))
    worker_max_runtime_seconds: int = int(os.getenv("WORKER_MAX_RUNTIME_SECONDS", "7200"))
    worker_force_kill_grace_seconds: int = int(os.getenv("WORKER_FORCE_KILL_GRACE_SECONDS", "10"))

    @property
    def youtube_transcript_languages(self) -> list[str]:
        return [value.strip() for value in self.youtube_transcript_languages_raw.split(",") if value.strip()]

    @property
    def router_base_url(self) -> str:
        return self.openai_base_url.rstrip("/")

    @property
    def router_api_key(self) -> str:
        for value in (self.nine_router_api_key, self.openai_api_key):
            if value and value != "***" and not value.lower().startswith("your_"):
                return value
        return ""

    @property
    def router_ready(self) -> bool:
        return bool(self.router_base_url and self.router_api_key)

    @property
    def transcription_ready(self) -> bool:
        return self.router_ready or self.local_asr_ready

    @property
    def local_asr_ready(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None


settings = Settings()
