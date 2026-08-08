# 9Router / OpenAI-compatible provider config

- `config/9router.env.local` is loaded automatically by Docker Compose.
- The app also falls back to values from `.env` for local development.
- If router transcription is not ready, the worker falls back to local `faster-whisper` ASR when available.
- API keys are never printed by the app; `/router/config` only exposes masked readiness state.

## Useful endpoints
- `GET /health`
- `GET /router/config`
- `GET /router/ping` (requires valid 9Router/OpenAI-compatible credentials)
- `POST /jobs` (upload file *atau* `youtube_url`; optional `cookies_from_browser`)
- `GET /jobs/{job_id}/transcript`
- `GET /jobs/{job_id}/highlight`
- `GET /jobs/{job_id}/subtitles`
- `GET /jobs/{job_id}/crop`
