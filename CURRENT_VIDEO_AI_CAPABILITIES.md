# Current Video AI Capabilities

Audit date: 2026-08-09

Scope: `/home/bismillah/ai-video-clipper-vps`, active Docker services, host media tools, runtime dependencies, API, Redis job state, and sampled real artifacts. No implementation or production configuration changed during this audit.

## Runtime Status

- App: `ai-video-clipper-app`, running six days, host port `8000`.
- Worker: `ai-video-clipper-worker`, running six days.
- Queue: `ai-video-clipper-redis`, Redis-backed `video_jobs` queue.
- API health: `GET /health` returned `{"status":"ok"}`.
- Router: `GET /router/ping` returned HTTP 200 / `ok: true`.
- Editorial model: `ag/gemini-pro-agent`, `xhigh` reasoning, via configured 9Router endpoint.
- Host FFmpeg: 5.1.8. Runtime container FFmpeg: 7.1.5.
- Host GPU devices: Intel HD 620 plus NVIDIA MX150. NVIDIA driver unavailable (`nvidia-smi` cannot communicate); production inference/render is CPU-oriented.
- RAM: 11 GiB total, about 6 GiB available at audit. Swap: 27 GiB. Root free space: 42 GiB.
- Existing changed/untracked files are present in repo before audit. Do not overwrite, reset, or mass-format them.

## Existing Capabilities

### Media

- `READY` — Upload ingest through `POST /jobs`; source written under `/data/work/<job_id>/`.
- `READY` — YouTube ingest: transcript-first then concurrent Gemini analysis and HD download.
- `READY` — HD helper `scripts/download_youtube_hd.py`; docs specify 1440p then 1080p preference.
- `READY` — FFprobe metadata helpers: duration and video dimensions.
- `READY` — Audio extraction to mono 16 kHz WAV.
- `PARTIAL` — Media validation. Supported suffixes are checked for discovery, but no verified ingest-time file hash, MIME validation, corruption check, duplicate/near-duplicate detection, black-frame detection, blur/shake score, or asset index exists.
- `MISSING` — Structured persisted media manifest with codec, FPS, aspect ratio, audio presence/sample rate, file size, and source fingerprint.

### Speech

- `READY` — Existing local ASR: `faster-whisper`, model `base`, CPU, INT8; runtime dependency and host model cache verified.
- `READY` — Existing remote transcription adapter in `shared/router_client.py`.
- `READY` — YouTube transcript retrieval plus persisted `transcript.json` for transcript-first jobs.
- `PARTIAL` — Transcript segment timestamps exist. Word timestamps are supported when source provides them; YouTube captions often have no reliable words, then pipeline synthesizes timing from segments.
- `MISSING` — Speaker diarization.
- `PARTIAL` — Silence detection function exists (`extract_silence_segments`), but audit found no evidence it drives automatic remove-silence EDL edits.
- `PARTIAL` — Transcript reuse is job-local (`transcript.json`, Redis state). No verified hash + ASR model/version cache key for uploaded media.

### Content / Editorial AI

- `READY` — Gemini editorial analysis for YouTube transcript path in `shared/viral_editorial.py`.
- `READY` — Persisted `viral-analysis.json` and candidate previews.
- `READY` — Grounded quote mapping back to transcript segments.
- `READY` — Candidate selection with LLM plus heuristic fallback, score threshold and backoff.
- `READY` — Existing structured editorial fields: `hook_text`, `clipper_style`, `style_reason`, `editing_notes`, `recommended_bgm`.
- `PARTIAL` — Offline/upload LLM route in `shared/pipeline.py` asks only for `highlight_quote`, `hook_text`, `reason`, and `score`; it does not mirror full online editorial schema/style constraints. This creates online/offline behavior drift.
- `PARTIAL` — Current score is editorial/heuristic selection score, not documented six-factor clip score (`hook`, information, visual, emotion, novelty, delivery) persisted per candidate.
- `MISSING` — Explicit planner agent with editable project brief, target platform, audience, narrative roles, and revision decisions.

### Visual Understanding

- `READY` — OpenCV sampling and frame-difference scene-cut count in `analyze_stable_crop`.
- `READY` — MediaPipe face detection; Haar cascade fallback.
- `READY` — Crop decision persisted with face hits, scene-cut count, samples, crop box, aspect ratio, and reason.
- `READY` — H.264 crop proxy fallback for difficult source decoding.
- `PARTIAL` — Scene detection is crop-oriented aggregate data, not a persisted scene/shot list with boundaries and representative frames.
- `PARTIAL` — Face detection supports reframing, but not face tracking across timeline or multi-person identity/speaker association.
- `MISSING` — Vision-language analysis of selected frames: subject, product/object, action, composition, lighting, blur, obstruction, OCR, novelty, visual quality.
- `MISSING` — Cached representative frames or visual-analysis artifact.

### Editing

- `READY` — Controlled Python execution layer, not arbitrary LLM shell output.
- `READY` — Highlight trimming from source.
- `READY` — Portrait 9:16 render. Two-person detection can select 16:9 output behavior.
- `READY` — Face-aware/stabilized crop.
- `READY` — ASS subtitle generation, safe-area logic, hook overlay, word/continuous caption modes, deterministic Indonesian currency cleanup.
- `READY` — Audio mastering in render filter graph: high-pass, 3 kHz EQ, loudness normalization, timestamp-safe resampling.
- `READY` — Audio/video window trim and PTS reset in normal renderer (`trim`, `atrim`, `setpts`, `asetpts`).
- `PARTIAL` — Clip reorder exists conceptually through selector/output ranks, not as a general multi-source timeline engine.
- `MISSING` — Persisted structured EDL/timeline. Current state saves selected highlight/output JSON in Redis, but no ordered edit operations, source in/out list, or EDL version artifact.
- `MISSING` — General split/remove/move/reorder/concatenate API tools.
- `MISSING` — B-roll selection/planning, overlays beyond captions/hooks, transitions as first-class timeline operations, music/SFX mixing and ducking.
- `PARTIAL` — Adaptive slide/speaker scripts exist, but are manual scripts outside core API worker path. No verified automatic scene-by-scene layout planner.

### Rendering

- `READY` — FFmpeg H.264/AAC outputs, 1080x1920 default, 30 FPS default.
- `READY` — ASS burn-in using Montserrat; runtime font verified.
- `READY` — Rank-specific render support in worker and artifact endpoints.
- `PARTIAL` — `build_mode=first_only` or `sequential_all`; worker is single consumer and jobs are isolated child processes.
- `PARTIAL` — No explicit draft render tier. Existing pipeline renders final-size output directly.
- `PARTIAL` — Final output existence checked by worker. No post-render ffprobe validation before marking job completed.

### QC / Revision / Resilience

- `READY` — Worker stage heartbeat, timeout guard, isolated child process, terminal job status, Redis-persisted intermediate state.
- `READY` — Job can build later candidate ranks using persisted editorial analysis.
- `PARTIAL` — Resume granularity exists at rank/candidate level; no stage checkpoint contract for failed render-only retry.
- `MISSING` — Technical QC artifact: ffprobe stream checks, black/freeze-frame checks, subtitle presence/position checks, audio presence, A/V sync threshold.
- `MISSING` — Editorial QC agent, quality score, issue list, and bounded automatic revision loop.
- `MISSING` — Automatic EDL patch and rerender limited to detected issue.

### API / Storage / Logging / Security

- `READY` — FastAPI API includes job create/status, transcript, candidates, highlight, subtitles, crop, and artifact routes.
- `READY` — Redis job state and filesystem artifacts in `/data/work`, `/data/videos`, `/data/logs`, `/data/cache`.
- `READY` — Docker bind mounts separate app code from media/work/log/cache paths.
- `READY` — Router configuration endpoint exposes sanitized state, not secret values.
- `PARTIAL` — File upload accepts path-derived filename without an explicit content-type / file magic allowlist. Need validate source media before expensive work.
- `PARTIAL` — Logs are sparse; `docker logs --tail` showed app access logs and no worker processing history. Job state has progress fields, but no structured per-stage audit log artifact.
- `MISSING` — Explicit project/job schema version and EDL/QC versioning.

## Verified Real Artifact

Sampled latest generated MP4:

- Path: `/data/videos/6903d42f30034c02a95e9d0c26edf35e_rank1_hook_no_pov.mp4`
- Size: 9,769,246 bytes.
- Video: H.264, 1080x1920, 30 FPS, duration 40.300 s.
- Audio: AAC, duration 40.292 s.
- Format duration: 40.367 s.
- Problem: video `start_time=0.066016`; audio `start_time=0.056000`. Outputs have an approximately 10 ms nonzero stream-offset mismatch. Small, but this fails strict zero-start A/V QC. Core renderer code resets PTS, yet this manually named recent artifact needs provenance check and final output QC must reject or normalize nonzero offsets.

## What To Reuse

1. Keep FastAPI + Redis + worker architecture. It already separates HTTP ingest, queue, and media execution.
2. Keep `shared/pipeline.py` as controlled execution layer for FFmpeg, ASR, crop, subtitle, selection, and rendering.
3. Keep faster-whisper local fallback and transcript-first YouTube path. Do not replace ASR.
4. Keep Gemini/9Router editorial adapter and persisted `viral-analysis.json`.
5. Keep current face/crop analysis. Extend output into scene-aware planning instead of adding a new clipping service.
6. Keep ASS subtitle renderer and audio mastering chain.
7. Keep job artifacts under existing `/data/work/<job_id>` and `/data/videos`; add structured artifacts there incrementally.

## Gap Analysis

Fundamental P0 gaps:

1. No persistent EDL. Agent cannot reliably explain, reproduce, patch, or rerender an edit without re-running selection logic.
2. No unified editor planner. Existing highlight selection chooses one source window; no structured story/timeline plan.
3. No technical QC gate. Worker marks output complete if path exists, not if valid streams, zero-start sync, expected geometry, audio, captions, and usable frames pass checks.
4. No project stage manifest/checkpoints. Resume is incomplete and diagnostic state is Redis-centric.
5. Upload/offline editorial path diverges from YouTube online path.

P1 gaps:

1. Scene list + cached representative frames.
2. Lightweight visual quality signals: black frame, freeze, blur, decode corruption, audio availability.
3. Filler/silence decisions materialized as EDL operations.
4. Draft render and automatic revision loop.
5. Semantic visual analysis only on representative frames, using existing/local capability if available; otherwise stay heuristic until an approved model exists.

P2 gaps:

1. Multi-source reorder/concat, B-roll matching, music ducking.
2. Automatic adaptive speaker/presentation layout integrated into worker.
3. Face/object tracking and richer transitions.

P3 not started:

- Generated B-roll, image/video generation, voice cloning, complex VFX.

## Implementation Plan

### P0.1 — Artifact Manifest and EDL Foundation

Add to current job directory without moving architecture:

```text
/data/work/<job_id>/
  media.json
  transcript.json
  analysis/scene-summary.json
  edl/edl-v1.json
  qc/draft-01.json
  renders/draft-01.mp4
```

- `media.json`: ffprobe-derived source facts and source SHA-256.
- `edl-v1.json`: source path, ordered clips, in/out, role, reason, crop/subtitle/audio options, target spec, version.
- Generate EDL after selection. Render strictly from EDL, not from a loose selection object.
- Preserve existing Redis fields/API response for backward compatibility. Add EDL metadata; do not rename current routes.

Acceptance:

- One existing upload job produces `media.json` and `edl-v1.json`.
- Re-render same EDL without calling ASR or Gemini.
- Unit-style stdlib test validates EDL bounds, ordered clips, supported source path, positive durations.

### P0.2 — Planner Adapter

- Convert existing `HighlightSelection` / persisted Gemini candidate into initial single-clip EDL.
- Use existing structured online fields end-to-end.
- Mirror full editorial fields and strict hook fallback into offline `_llm_highlights` path.
- Keep context-complete boundaries. Do not cap at target duration when thought is unfinished.

Acceptance:

- Both upload and YouTube jobs yield same required planner/EDL fields.
- Existing first-only rank behavior remains valid.

### P0.3 — Technical QC Gate

Add deterministic QC using FFprobe + sampled FFmpeg frames; no new Python package:

- output file exists/nonempty;
- H.264/AAC streams exist;
- expected resolution/FPS/duration;
- both streams start near zero and offset within defined tolerance;
- audio duration close to video duration;
- opening/middle/end sampled frames decode and are not mostly black;
- ASS sidecar exists and has caption events when captions enabled.

Write `qc/draft-01.json`. Worker completes only after passing QC. If failed, retain artifact, mark reason, and allow render-only retry from EDL.

Acceptance:

- QC passes a known good generated artifact.
- QC detects a deliberately invalid/missing stream or black sample.
- Current 10 ms offset policy explicitly defined and tested; prefer output normalization to zero starts.

### P0.4 — Stage Checkpoints

- Persist stage status in job directory as well as Redis.
- Reuse `transcript.json`, `viral-analysis.json`, media manifest, EDL, and subtitle sidecar on rerender.
- Add explicit `render` retry action/API only after current job route behavior is understood and tested.

### P1.1 — Scene / Visual Summary

- Extend existing OpenCV + MediaPipe sampling to output `analysis/scene-summary.json`.
- Store scene candidate boundaries, representative-frame paths, face counts, motion score, black/blur score, and crop recommendation.
- Do not add a vision model until this deterministic data is working and cached.

### P1.2 — EDL Cleanup Operations

- Transform silence/filler/repetition detection into explicit EDL `remove_segment` operations.
- Apply only high-confidence removals. Preserve word boundaries and natural speech.
- Use current ASS generator after final EDL timings, not before.

### P1.3 — Draft, Editorial QC, Bounded Revision

- Draft at 540x960 or 720x1280 only if current final render runtime needs it.
- Run deterministic QC first; then editor review scores hook, clarity, pacing, continuity, captions, and audio.
- Max 3 automatic revisions. Patch EDL only. Do not re-run ASR/Gemini unless required input changed.

### P2 — Multi-Source and Adaptive Layout

- Add EDL operations for concat/reorder and source-aware B-roll.
- Promote existing manual speaker/slide scripts into a tested worker adapter only after one P0 EDL render path is stable.
- Classify every scene interval, not one dominant mode per ranked clip.

## Explicit Non-Goals Now

- No microservice rewrite.
- No Whisper replacement.
- No clipping-engine replacement.
- No new paid external vision API.
- No generated B-roll, voice cloning, or VFX before P0/P1 passes real jobs.

## First Implementation Target

P0.1: `media.json` + `edl/edl-v1.json` generated from existing selection, then renderer consumes EDL. This gives reproducible edits and makes QC/revision possible without disrupting live ingest, ASR, clipping, captions, or rendering.

## Verification Commands Used

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/router/config
curl -fsS http://127.0.0.1:8000/router/ping
docker ps
docker exec ai-video-clipper-worker ...
ffprobe -v error -show_entries ... /data/videos/<artifact>.mp4
```

`pytest` is not installed on host (`No module named pytest`). Existing lightweight tests are standalone Python files, not a discovered test suite.
