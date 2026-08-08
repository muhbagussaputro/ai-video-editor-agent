# Plan Implementasi AI Video Clipper di VPS

## Tujuan
Membangun pipeline AI video clipper self-hosted di VPS dengan penyimpanan video di HDD, sementara proses eksekusi/pemrosesan dilakukan di folder kerja terpisah.

## Keputusan Arsitektur
- **Storage video final / arsip**: HDD
- **Working directory eksekusi**: folder terpisah di VPS
- **Orkestrasi**: Docker / Docker Compose
- **Mode model**: API-based untuk beban berat agar VPS tetap ringan

## Struktur Folder yang Disarankan
- `/data/videos/` → input dan output video yang sudah jadi
- `/data/work/` → folder eksekusi sementara
- `/data/logs/` → log proses
- `/data/cache/` → cache sementara

## Alur Proses
1. Upload atau download video masuk ke folder input.
2. Video diproses di folder work.
3. Audio diekstrak dan ditranskrip.
4. Highlight dipilih via LLM/API.
5. Auto-crop dan render klip final.
6. Output disimpan ke HDD di folder video final.
7. File sementara di work dibersihkan setelah selesai.

## Tahapan Implementasi
### Tahap 1 - Persiapan Server
- Siapkan VPS
- Mount HDD sebagai storage utama video
- Buat folder kerja dan folder output
- Pastikan permission benar

### Tahap 2 - Setup Runtime
- Install Docker dan Docker Compose
- Siapkan `.env`
- Set API key untuk transkripsi dan LLM
- Tentukan path folder input/output/work

### Tahap 3 - Pipeline Media
- Download / ingest video
- Ekstrak audio dengan FFmpeg
- Transkripsi audio
- Ranking highlight
- Render final vertical clip

### Tahap 4 - Quality Control
- Cek hasil subtitle
- Cek crop wajah / framing
- Cek stabilitas render
- Cek ukuran file output

### Tahap 5 - Operasional
- Tambahkan cleanup job untuk file sementara
- Tambahkan logging
- Tambahkan retry untuk API failure
- Tambahkan queue jika batch besar

## Spesifikasi Minimum yang Disarankan
- **CPU-only**: 4 vCPU / 8 GB RAM
- **Nyaman**: 8 vCPU / 16 GB RAM
- **Storage**: HDD untuk arsip, idealnya NVMe untuk work/cache jika tersedia

## Risiko dan Mitigasi
- **HDD lambat** → gunakan hanya untuk storage hasil akhir, bukan kerja berat
- **RAM spike** → batasi concurrency
- **API rate limit** → queue + retry
- **File sementara menumpuk** → cleanup otomatis

## Next Action
- Finalisasi struktur folder
- Siapkan docker-compose
- Siapkan `.env`
- Implementasi pipeline tahap awal
