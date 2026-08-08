# SOP Render Adaptive Video Clipper

Dokumen ini berisi standar alur kerja (pipeline) mutlak untuk menghindari masalah desync audio, subtitle lambat, dan layout POV yang berantakan pada video short-form (9:16).

## 1. Aturan Emas Pemotongan FFmpeg (Trim & ATrim)
Jika memotong video MP4/MKV berdurasi panjang menjadi klip pendek, **JANGAN** hanya memotong aliran videonya saja. Jika hanya video yang dipotong, audio akan tetap diputar dari detik 0:00!
Wajib memotong video dan audio secara bersamaan dan mereset PTS (Presentation Time Stamp) keduanya:
```bash
[0:v]trim=start={START}:end={END},setpts=PTS-STARTPTS[v];
[0:a]atrim=start={START}:end={END},asetpts=PTS-STARTPTS[a]
```

## 2. Aturan Emas Transkrip (Anti-Lemot & Anti-Overlap)
Transkrip otomatis YouTube (`yt-dlp-auto-sub`) sering kali memiliki *timestamp* yang menumpuk (overlap) dan lambat hingga 2-3 detik dari suara aslinya.
**Solusi Mutlak:**
Untuk setiap highlight yang sudah dipilih oleh LLM, **JANGAN** gunakan transkrip YouTube untuk merender `.ass`. 
1. Ekstrak audio dari rentang highlight tersebut:
   `ffmpeg -i source.mkv -ss {START} -t {DURATION} -vn -acodec pcm_s16le -ar 16000 -ac 1 temp.wav`
2. Lakukan transkripsi ulang menggunakan `faster_whisper` lokal di container worker dengan parameter `word_timestamps=True`.
3. Gunakan *word-level segments* dari whisper lokal ini untuk menyusun file `.ass`.

## 3. Layout Strict (adaptive-layout.json)
- **Face/Talking Head Mode (9:16):**
  - Crop: `crop=in_h*9/16:in_h,scale=1080:1920`
  - Subtitle Anchor: `y=1284`
- **Presentation Mode (4:3 in 9:16 canvas):**
  - Crop: `crop=in_h*4/3:in_h,scale=1080:810,pad=1080:1920:0:250:color=black`
  - Subtitle Anchor: `y=1080`
- **Persistent POV & Watermark (Selalu Muncul):**
  - Anchor: `\an8` (Top Center dari kordinat Y)
  - Posisi: `x=540, y=1540` (Bawah Tengah)
  - Font: `Montserrat ExtraBold`, size `66`
  - Warna Aksen: `&H00B000FF` (Ungu/Magenta)
  - Handle: `@gusaja.com` (size `32`)

## 4. Contoh Script Python Standar
```python
# 1. Ekstrak Audio untuk segmen target
subprocess.run(["ffmpeg", "-y", "-i", source, "-ss", str(START), "-t", str(DURATION), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "temp.wav", "-loglevel", "error"])

# 2. Whisper lokal untuk word-level timing (SUPER AKURAT)
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
segments, _ = model.transcribe("temp.wav", language="id", word_timestamps=True)

normalized = []
for s in segments:
    for w in s.words:
        normalized.append({
            "start": w.start + START,
            "end": w.end + START,
            "duration": w.end - w.start,
            "text": w.word.strip()
        })

# 3. Build ASS
build_subtitle_ass(normalized, START, END, ass, "1080x1920", "", "")

# 4. Inject POV
pov_event = (
    f"Dialogue: 5,0:00:00.00,0:00:{DURATION:.2f},Default,,0,0,0,,"
    "{\\an8\\pos(540,1540)\\fs66\\fnMontserrat ExtraBold\\b1\\bord5\\3c&H00111111\\shad2\\4c&H99000000}"
    "{\\1c&H00FFFFFF}POV: KELAS MENENGAH\\N"
    "{\\1c&H00B000FF}AKAN HANCUR?\\N"
    "{\\fs32\\1c&H00FFFFFF\\bord3}@gusaja.com"
)
ass.write_text(ass.read_text() + pov_event + "\n", encoding="utf-8")

# 5. FFmpeg Trim (Video + Audio)
fc = (
    f"[0:v]trim=start={START}:end={END},setpts=PTS-STARTPTS,fps=30,"
    "crop=in_h*9/16:in_h,scale=1080:1920,setsar=1,format=yuv420p,"
    f"subtitles=filename='{ass}'[v]; "
    f"[0:a]atrim=start={START}:end={END},asetpts=PTS-STARTPTS[a]"
)
subprocess.run(["ffmpeg", "-y", "-i", source, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac", "out.mp4"])
```