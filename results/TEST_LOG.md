# Log Pengujian Sistem

> Isi file ini saat pengujian nyata di Jetson Nano. Sertakan foto/screenshot
> di folder ini (`results/`).

## Setup
- Hardware: Jetson Nano 4GB, USB webcam 640×480
- Sistem: JetPack 4.6 / Ubuntu 18.04
-Tanggal: (isi)
- Anggota: (isi)

## 1. Uji Mock (verifikasi pipeline tanpa hardware)
Perintah: `python3 src/main.py --mock`

Output:
```
input=STOP conf=0.92 → decision=STOP safe=False LED={'red': True, 'yellow': False, 'green': False}
input=SLOW conf=0.88 → decision=SLOW safe=False LED={'red': False, 'yellow': True, 'green': False}
input=GO   conf=0.91 → decision=GO   safe=False LED={'red': False, 'yellow': False, 'green': True}
input=NONE conf=0.10 → decision=NONE safe=True  LED={'red': False, 'yellow': False, 'green': False}
input=STOP conf=0.95 → decision=STOP safe=False LED={'red': True, 'yellow': False, 'green': False}
```
Status: **PASS** — LED mengikuti sign; tanpa sign semua LED mati.

## 2. Uji Unit Test
Perintah: `python3 tests/test_pipeline.py`

```
13/13 passed
```
Status: **PASS**

## 3. Uji Recognizer Sintetis (regresi misklasifikasi SLOW→GO)
Perintah: jalankan `recognize()` pada gambar sintetis STOP/SLOW/GO dan kasus jebakan
(warna benar tapi bentuk salah). Hasil:

| Input | Ekspektasi | Aktual | Conf |
|-------|-----------|--------|------|
| merah segi-8 | STOP | STOP | 0.97 |
| kuning segitiga | SLOW | SLOW | 0.97 |
| kuning segitiga sudut membulat | SLOW | SLOW | 0.97 |
| hijau lingkaran | GO | GO | 0.97 |
| hijau persegi (bentuk valid GO) | GO | GO | 0.88 |
| **biru lingkaran + panah putih** | GO | GO | **1.00** |
| **biru persegi + panah putih** | GO | GO | **0.91** |
| **STOP dekat/terpotong (s=270)** | STOP | STOP | 0.98 |
| **SLOW dekat/terpotong (s=270)** | SLOW | SLOW | 1.00 |
| **GO biru dekat/terpotong (s=270)** | GO | GO | 0.86 |
| hijau segitiga | NONE | NONE | 0.40 |
| merah segitiga | NONE | NONE | 0.40 |
| kuning lingkaran | NONE | NONE | 0.40 |
| **biru segitiga** | NONE | NONE | 0.40 |
| **biru oktagon** | NONE | NONE | 0.40 |
| frame kamera ruangan (tanpa sign) | NONE | NONE | 0.00 |

Status: **PASS** — bentuk kini wajib cocok (skor maksimum tanpa bentuk = 0.40 < 0.55),
sehingga objek hijau/biru/merah sembarang tidak lagi terbaca sebagai GO/STOP.
**GO versi biru + panah putih** dikenali karena panah putih (saturasi rendah) tidak
masuk mask; kontur luar tetap lingkaran/persegi.
Bukti: `results/synth_STOP.jpg`, `synth_SLOW.jpg`, `synth_GO.jpg`.

Uji stres bentuk (tanda dengan teks + border): **4 tanda** (STOP, SLOW, GO hijau,
GO biru+panah) × **14 kondisi** (normal, jauh, dekat/terpotong, rotasi ±12°,
perspektif, gelap, terang, noise, blur, pudar, hue ±8, resolusi 320) =
**56/56 benar (100%)**.

## 3b. Uji Kecepatan
Perintah: `python3 tools/benchmark_detection.py --bench` (640×480, Jetson Nano)

| Tahap | Sebelum | Sesudah |
|-------|--------:|--------:|
| Recognizer `color_shape` | ~70 ms (14 FPS) | **~29 ms (34 FPS)** |
| Pipeline penuh (recognize+decision+LED+annotate) | — | **~28 ms (36 FPS)** |

Percepatan dari: downscale deteksi ke 320 px, morphologi kernel persegi
(separable), contour top-3 per warna, dan klasifikasi dari convex hull.
Penambahan warna biru (GO) menambah satu pass warna (~6 ms); end-to-end tetap
dibatasi kamera ±30 FPS.

## 4. Uji Kamera + Sign Nyata @ 3 Jarak
(isi tabel di README §8.1 saat pengujian lapangan)

| Sign | 30 cm | 50 cm | 100 cm | LED |
|------|-------|-------|--------|-----|
| STOP | | | | |
| SLOW | | | | |
| GO   | | | | |

## 5. Uji Pencahayaan
| Sign | Terang | Redup |
|------|--------|-------|
| STOP | | |
| SLOW | | |
| GO   | | |

## 6. Uji Pergantian Sign & No-Sign
| Skenario | Ekspektasi | Aktual | Pass? |
|----------|------------|--------|-------|
| STOP→SLOW | merah→kuning | | ☐ |
| SLOW→GO | kuning→hijau | | ☐ |
| GO→NONE (>0,5 dtk) | hijau→semua mati | | ☐ |
| conf < threshold | semua LED mati | | ☐ |

## Screenshot
- `results/preview_stop.jpg` — STOP terdeteksi, LED merah menyala
- `results/preview_slow.jpg` — SLOW terdeteksi, LED kuning menyala
- `results/preview_go.jpg` — GO hijau terdeteksi, LED hijau menyala
- `results/preview_go_biru_panah.jpg` — GO biru + panah putih, LED hijau menyala
- `results/preview_nosign.jpg` — tanpa sign, semua LED mati
- `results/camera_test.jpg`, `results/live_snapshot_fix.jpg` — frame kamera asli
  (tanpa tanda → tidak ada false positive)
