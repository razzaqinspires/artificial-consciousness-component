# AC-Kernel NADI 2.1.0

AC-Kernel NADI adalah komponen Python modular untuk mensimulasikan dan mengelola *operational self-state* agen: heartbeat terjadwal, homeostasis, model-diri prediktif, dinamika afektif sintetis, deliberasi kebijakan, konsolidasi memori, dan ledger integritas SHA-256. Komponen ini dirancang independen dari aplikasi host seperti Ocha Lidya AI.

> **Batas klaim:** nama proyek merujuk pada riset/arsitektur kesadaran buatan. Implementasi ini adalah model komputasional dan tidak membuktikan pengalaman subjektif, sentience, emosi biologis, atau kesadaran fenomenal.

## Perubahan 2.1.0

- Kernel lifecycle dengan OS process lock untuk mencegah dua writer memakai `data_dir` yang sama.
- Heartbeat background terkelola, idempotent, drift-corrected, dan menghindari *catch-up storm*.
- Ledger memori privat per-scope dengan direktori pseudonim berbasis salt; raw sender ID tidak ditulis ke nama direktori.
- Stimulasi privat dapat diproses tanpa menyimpan teks mentah (`persist_stimulus=False`).
- Snapshot korup dikarantina dan startup dihentikan dengan error eksplisit, bukan reset diam-diam.
- HTTP sidecar loopback-first dengan autentikasi Bearer untuk binding non-loopback, rate limit, pembatasan ukuran body, validasi JSON, timeout socket, dan respons tanpa cache.
- API `/v1/*` untuk health, status, heartbeat, perceive, commit digest, recall scope, tick, sleep, checkpoint, dan verifikasi.
- Kalibrasi homeostasis operasional 1 Hz dipertahankan agar cadangan energi dan beban komputasi tidak drift secara agresif selama heartbeat jangka panjang.
- Tetap provider-agnostic; host app tetap memegang satu-satunya rantai provider LLM.

## Struktur

```text
ac/
├── adapters.py          # Adapter LLM opsional (mock/OpenAI-compatible/Ollama/webhook)
├── appraise_llm.py      # Appraisal heuristik/LLM opsional
├── bridge.py            # Alur percakapan standalone
├── config.py            # ACConfig
├── diri.py              # Predictive self-model
├── ingat.py             # EternalMemory + SHA-256 chain
├── intero.py            # Homeostasis/interoception
├── kehendak.py          # Active inference / EFE
├── kernel.py            # Orkestrator dan lifecycle kernel
├── metrics.py           # Telemetri komputasional
├── mimpi.py             # Konsolidasi NREM/REM
├── nadi.py              # Heartbeat oscillator
├── neuro.py             # Neuromodulator state model
├── panggung.py          # Global workspace model
├── rasa.py              # Synthetic appraisal model
├── sapa.py              # Consent gate
├── server.py            # Secured HTTP sidecar
└── util.py              # I/O atomik dan utilitas
```

## Persyaratan dan instalasi

- Python 3.10 atau lebih baru.
- Tidak ada dependency pihak ketiga wajib; implementasi inti menggunakan standard library Python.
- Satu proses NADI per `data_dir`.

```bash
python --version
python selftest.py
python test_prime.py
python -m py_compile ac/*.py
python -m ac --config ac_config.example.json status
```

Buat konfigurasi aktif dari template sebelum menjalankan service:

```bash
cp ac_config.example.json ac_config.json
# Edit data_dir agar menunjuk ke penyimpanan persisten yang kamu inginkan.
python -m ac --config ac_config.json serve --host 127.0.0.1 --port 8765
```

Service memulai heartbeat otomatis saat server mulai. `Ctrl+C` menghentikan service; kernel menyimpan snapshot dan melepaskan process lock saat penutupan normal.

## HTTP API

Semua endpoint API berversi memakai prefix `/v1`.

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | `/v1/health` | Health service, versi, heartbeat, dan validitas ledger |
| GET | `/v1/status` | Snapshot state operasional |
| GET | `/v1/verify` | Verifikasi hash-chain |
| GET | `/v1/heartbeat` | Status heartbeat |
| GET | `/v1/capabilities` | Kapabilitas service |
| POST | `/v1/heartbeat` | `{"action":"start","interval_sec":1}` atau `{"action":"stop"}` |
| POST | `/v1/perceive` | Proses satu input privat dalam scope sender tanpa menyimpan raw message |
| POST | `/v1/commit` | Simpan keyed digest dan jumlah karakter respons, bukan teks mentah |
| POST | `/v1/recall` | Recall ledger pada scope pengirim tertentu |
| POST | `/v1/tick` | Jalankan satu tick manual; stimulus privat harus menyertakan `sender_id` |
| POST | `/v1/sleep` | Konsolidasi memori global atau scope tertentu |
| POST | `/v1/checkpoint` | Simpan snapshot eksplisit |

Contoh request privat:

```json
{
  "sender_id": "opaque-sender-key",
  "message": "Pesan yang ingin diproses secara sementara",
  "private_memory_context": [],
  "consent_granted": false
}
```

`/v1/perceive` memproses input dalam memori kerja scope sender, tetapi menyetel `persist_stimulus=False`. Simpan isi percakapan jangka panjang di vault privat host app. `private_memory_context` adalah data tidak tepercaya dan hanya digunakan untuk menyusun konteks respons pada request itu.

## Keamanan dan privasi

- Default binding `127.0.0.1`; binding non-loopback ditolak tanpa `NADI_API_TOKEN`.
- Jika token disetel, seluruh route memerlukan `Authorization: Bearer <token>`.
- Jangan mengekspos HTTP port secara langsung ke internet. Gunakan jaringan privat atau reverse proxy TLS yang dikonfigurasi dengan benar.
- Hindari mengirim secret, kredensial, atau isi vault ke NADI.
- Satu `data_dir` hanya boleh dibuka satu process. OS file lock mencegah dua writer.
- Backup `data_dir` beserta `.scope-salt`; file salt diperlukan untuk pemetaan scope privat yang stabil.
- Ledger hash-chain mendeteksi perubahan data, tetapi bukan pengganti backup terenkripsi atau kontrol akses filesystem.
- Jangan menafsirkan angka afektif/neuromodulator sebagai emosi manusia nyata.

## Environment opsional

| Variable | Default | Fungsi |
|---|---:|---|
| `NADI_API_TOKEN` | kosong | Wajib untuk binding non-loopback; jika disetel selalu diminta |
| `NADI_MAX_REQUEST_BYTES` | 1 MiB | Batas ukuran body; diklem 16 KiB–4 MiB |
| `NADI_RATE_LIMIT_PER_MINUTE` | 120 | Batas request per IP per menit |
| `NADI_SCOPE_CACHE_LIMIT` | 128 | Cache ledger scope di memori |
| `NADI_DEFAULT_RECALL_TOP_K` | dari config | Default jumlah hasil recall |

## Validasi lokal

```bash
python -m py_compile ac/*.py
python selftest.py
python test_prime.py
```

Suite dasar menguji genesis/hash-chain, recall/konsolidasi, bridge/consent, dan HTTP sidecar. Suite tambahan menguji isolasi scope, non-persistensi pesan privat, lifecycle heartbeat, API perceive/commit, penolakan binding publik tanpa token, process lock, karantina snapshot korup, dan autentikasi Bearer.
