# AI Video Clipper VPS Scaffold

Scaffold awal untuk pipeline AI video clipper self-hosted di VPS.

## Isi
- `docker-compose.yml` untuk stack dasar
- `.env.example` untuk variabel lingkungan
- `README-plan.md` untuk rencana implementasi
- `config/README.md` untuk setup 9Router

## Alur fitur yang sudah di-wire
- Upload video ke API
- Worker queue via Redis
- Untuk sumber YouTube: coba ambil transcript/CC dulu via `youtube-transcript-api`
- Fallback ke local ASR (`faster-whisper`) kalau transcript YouTube tidak tersedia
- Highlight selection via LLM router yang aktif
- Burn-in subtitle ASS dengan word-level karaoke bila timestamp tersedia
- Render clip vertikal 9:16

## Cara pakai
1. Copy env template:
   ```bash
   cp .env.example .env
   ```
2. Isi `OPENAI_API_KEY` atau `NINE_ROUTER_API_KEY` di `.env` dengan *key* asli.
3. Jalankan stack:
   ```bash
   docker compose up -d --build
   ```
4. Cek status provider:
   ```bash
   python3 scripts/check_router_env.py
   curl http://127.0.0.1:8000/router/config
   curl http://127.0.0.1:8000/router/ping
   ```

## Endpoint penting
- `GET /health`
- `GET /router/config`
- `GET /router/ping`
- `POST /jobs` (upload file *atau* `youtube_url`, optional `prefer_youtube_transcript=true|false`, optional `cookies_from_browser`)
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/transcript`
- `GET /jobs/{job_id}/highlight`
- `GET /jobs/{job_id}/subtitles`
- `GET /jobs/{job_id}/crop`

## Catatan
- `OPENAI_BASE_URL` bisa diambil dari `config/9router.env.local` jika tidak ada di `.env`.
- Jika provider router belum siap, pipeline otomatis fallback ke local heuristic/ASR sesuai data yang tersedia.
- Placeholder seperti `***` atau `your_*` otomatis diabaikan.
- Saat ini service masih berupa scaffold, tapi pipeline transcript-first + highlight sudah terhubung.
- Untuk sumber YouTube, `POST /jobs` default-nya mencoba ambil transcript/CC dulu via `youtube-transcript-api` dengan prioritas bahasa dari `YOUTUBE_TRANSCRIPT_LANGUAGES` (default: `id,en`).
- Jika transcript YouTube gagal / tidak ada, job tetap lanjut ke jalur lama: download video HD lalu local ASR `faster-whisper`.
- Ingest video YouTube tetap mengutamakan HD: helper `scripts/download_youtube_hd.py` auto-coba **1440p** lalu **1080p**.
- Helper ini paling stabil kalau yt-dlp modern tersedia sebagai modul Python dan runtime JS `node` ada di mesin.
- Kalau source butuh akses akun/browser, isi field `cookies_from_browser` saat upload job (mis. `firefox`).
