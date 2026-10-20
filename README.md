# Pengenalan Rambu Lalu Lintas dengan LED — Jetson Nano

Tugas kelompok ini membuat sistem yang membaca rambu lalu lintas dari kamera,
lalu menyalakan LED sesuai rambu yang sedang ditampilkan:

| Rambu | Warna & Bentuk | LED yang menyala |
|-------|----------------|------------------|
| STOP | merah, oktagon | merah |
| SLOW | kuning, segitiga | kuning |
| GO | hijau, atau biru dengan panah putih | hijau |
| tidak ada rambu | — | semua mati |

Programnya berjalan di Jetson Nano. Kamera mengambil frame terus-menerus, setiap
frame dianalisis untuk mencari rambu, lalu keputusannya dikirim ke GPIO untuk
menyalakan LED.

---

## 📹 Video Demo

[![Tonton Video Demo](https://drive.google.com/thumbnail?id=19MTVb-Pvqy-t6Fzr_xwGn6ziKQ6XT9tx)](https://drive.google.com/file/d/19MTVb-Pvqy-t6Fzr_xwGn6ziKQ6XT9tx/view)

## 🏗️ Arsitektur Sistem

Berikut adalah diagram alur sistem Traffic Sign Recognition pada Jetson Nano:

```mermaid
graph TD
    A[Kamera / Sensor] -->|Input Gambar| B(Jetson Nano)
    B -->|Proses AI| C{Model Deteksi Rambu}
    C -->|Rambu Terdeteksi| D[Kontrol Aktuator: LED]
    C -->|Tidak Ada Rambu| E[Lanjut / Abaikan]
    D -->|Sinyal| F[LED Menyala]

## 1. Latar Belakang dan Tujuan

Rambu STOP, SLOW, dan GO adalah tanda yang paling sering muncul di jalan kota.
Biasanya tanda seperti ini dibaca manusia untuk memutuskan berhenti, melambat,
atau jalan. Ide proyek kami adalah membuat simulasi lampu lalu lintas: kamera
sebagai "mata", komputer sebagai otak, dan tiga LED sebagai lampu.

Tujuan proyek kami:
1. Mendeteksi minimal tiga jenis rambu dari kamera.
2. Menyalakan LED yang berbeda untuk setiap rambu.
3. Menampilkan nama rambu, tingkat keyakinan, dan status LED di layar.
4. Memastikan kondisi aman: kalau tidak ada rambu yang terbaca, semua LED mati.

---

## 2. Alat dan Bahan

| No | Alat | Keterangan |
|----|------|------------|
| 1 | NVIDIA Jetson Nano 4GB | sebagai pemroses utama |
| 2 | Kamera CSI Raspberry Pi v2 (imx219) | 2 buah di board, dipakai sensor 0 |
| 3 | LED 5 mm: merah, kuning, hijau | 1 buah untuk masing-masing warna |
| 4 | Resistor 220 ohm | 3 buah, seri dengan tiap LED |
| 5 | Breadboard + jumper male-male | 1 set |
| 6 | Monitor + keyboard | opsional, untuk preview dan debugging |

Belanja komponen hanya perlu 3 LED, 3 resistor, 1 breadboard, dan beberapa
kabel jumper.

---

## 3. Software

| Software | Versi / Catatan |
|----------|-----------------|
| OS | Ubuntu 18.04, JetPack 4.x |
| Python | 3.6.9 (bawaan Jetson Nano) |
| OpenCV | 3.2.0 (bawaan JetPack, `python3-opencv`) |
| NumPy | 1.19 |
| Jetson.GPIO | 2.0.17, untuk menyalakan LED |
| GStreamer | untuk membaca kamera CSI |

Kamera CSI di Jetson tidak bisa dibaca dengan `cv2.VideoCapture()` biasa, hasilnya
frame hijau. Jadi program memakai `nvarguscamerasrc` lewat GStreamer
(`src/camera.py`). Paket yang perlu dipasang:

```bash
sudo apt-get install -y python3-gi gir1.2-gstreamer-1.0
```

---

## 4. Cara Kerja Sistem

```
┌─────────┐   frame    ┌──────────────────┐   hasil    ┌─────────────────┐
│ Kamera  │ ─────────► │ Sign Recognition │ ─────────► │ Decision Logic  │
└─────────┘            │  (warna + bentuk) │  sign, conf│ (konfirmasi N   │
                         └──────────────────┘            │  frame)         │
                                                          └────────┬────────┘
                                                                   │ sign
                                                                   ▼
┌─────────┐   GPIO     ┌──────────────────┐                  ┌──────────────┐
│   LED   │ ◄───────── │  GPIO Controller │ ◄────────────────│   Decision   │
│ R/Y/G   │            │  (Jetson.GPIO)   │                  └──────────────┘
└─────────┘            └──────────────────┘
```

Langkah per frame:

1. Kamera mengambil frame 640x480.
2. Frame dikecilkan ke lebar 320 px supaya lebih cepat di Jetson.
3. Frame diubah ke HSV, lalu dibuat mask untuk tiap warna (merah, kuning, hijau, biru).
4. Dari tiap mask dicari kontur, lalu bentuknya diklasifikasi dari *convex hull*:
   oktagon berarti STOP, segitiga berarti SLOW, lingkaran atau persegi berarti GO.
5. Bentuk yang tidak cocok dengan warnanya langsung dibuang, jadi benda hijau
   sembarangan tidak akan terbaca sebagai GO.
6. Confidence dihitung dari gabungan warna, bentuk, dan ukuran. Kalau nilainya
   di bawah 0,55, rambu dianggap tidak terbaca.
7. Rambu baru dipakai kalau terlihat stabil di 2 frame berturut-turut, supaya tidak
   berkedip karena gangguan sesaat.
8. Keputusan dikirim ke GPIO, LED dinyalakan, lalu hasilnya digambar di layar
   (kotak pembatas, nama rambu, keyakinan, dan status LED).

Kalau rambu hilang, LED terakhir ditahan 0,5 detik lalu dimatikan semua.

### Perhitungan confidence

```
confidence = 0,30 × warna + 0,60 × bentuk + 0,10 × ukuran
```

Bentuk paling berat bobotnya karena bentuk inilah yang membedakan STOP, SLOW, dan GO.
Kalau bentuknya tidak sesuai, nilai confidence paling tinggi hanya 0,40, masih di bawah
ambang 0,55, jadi kandidatnya ditolak.

### Rambu GO versi biru

Rambu GO yang kami pakai berwarna biru dengan panah putih. Panah putih tidak masuk
ke mask warna karena saturasinya rendah, jadi kontur luar yang terbaca tetap bentuk
rambunya. Karena itu ada dua mask yang sama-sama dipetakan ke GO: hijau dan biru.

### Tuning

Semua angka tunable ada di `config.py`:

| Variabel | Default | Keterangan |
|----------|---------|------------|
| `MIN_CONFIDENCE` | 0.55 | ambang minimum rambu dianggap sah |
| `PROCESS_WIDTH` | 320 | lebar frame saat deteksi |
| `STABLE_FRAMES` | 2 | jumlah frame konfirmasi |
| `SAFE_STATE` | "NONE" | kondisi tanpa rambu (semua LED mati) |
| `SAFE_HOLD_SECONDS` | 0.5 | lama LED terakhir ditahan |
| `HSV_RANGES` | — | rentang warna tiap tanda |

Kalau warna rambu tidak cocok dengan rentang di `config.py`, pakai
`tools/hsv_calibration.py` untuk melihat HSV di layar dan menyalin nilainya.

---

## 5. Rangkaian LED

```
Jetson Nano 40-pin                 Breadboard
──────────────────                 ──────────────────────────────
Pin 11 (GPIO17) ──[220Ω]──►|◄──┐   LED merah   (STOP)
Pin 13 (GPIO27) ──[220Ω]──►|◄──┤   LED kuning  (SLOW)
Pin 16 (GPIO23) ──[220Ω]──►|◄──┤   LED hijau   (GO)
                              │
GND (Pin 6) ───────────────────┘
```

Aturan pemasangannya: kaki panjang LED (anode) disambung ke resistor, kaki
pendek (katode) ke GND. Resistor 220 ohm menjaga arus, jadi tiap LED menerima
sekitar 5 sampai 6 mA, aman untuk pin GPIO Jetson.

| Fungsi | Pin header | BCM | Warna LED |
|--------|-----------|-----|-----------|
| STOP | 11 | GPIO17 | merah |
| SLOW | 13 | GPIO27 | kuning |
| GO | 16 | GPIO23 | hijau |
| GND | 6 | — | — |

Detail letak lubang breadboard dan urutan pemasangannya ada di
[`docs/WIRING.md`](docs/WIRING.md).

---

## 6. Instalasi dan Menjalankan

### 6.1 Di Jetson Nano

```bash
git clone https://github.com/raisfadillahh/AI-For-Robotic_Kelompok8.git
cd AI-For-Robotic_Kelompok8

sudo apt-get install -y python3-opencv python3-numpy python3-gi gir1.2-gstreamer-1.0
pip3 install -r requirements.txt

python3 src/main.py
```

Tambahkan `--no-preview` kalau dijalankan lewat SSH atau tanpa monitor.
Program berhenti dengan tombol `q` di jendela preview, atau `Ctrl+C` di terminal.

### 6.2 Mode mock

Untuk mencoba logika tanpa kamera dan tanpa LED:

```bash
python3 src/main.py --mock
```

Program menjalankan urutan STOP, SLOW, GO, tanpa rambu, lalu STOP, sambil mencetak
status LED tiap tahap.

### 6.3 Menguji satu gambar

```bash
python3 src/main.py --image assets/signs/stop.jpg --no-preview --save results/out.jpg
```

### 6.4 Unit test

```bash
python3 tests/test_pipeline.py
# atau
python3 -m pytest tests/ -v
```

### 6.5 Alat bantu

```bash
python3 tools/benchmark_detection.py --bench      # mengukur FPS
python3 tools/benchmark_detection.py --dir fotoku  # menguji folder gambar
python3 tools/capture_signs.py --labels GO         # mengambil contoh frame nyata
```

### Opsi baris perintah

| Opsi | Fungsi |
|------|--------|
| `--mock` | simulasi tanpa hardware |
| `--image PATH` | proses satu gambar |
| `--save PATH` | simpan hasil gambar berannotasi |
| `--method color_shape\|yolo` | metode pengenalan, default `color_shape` |
| `--no-preview` | matikan jendela preview |
| `--min-conf FLOAT` | ubah ambang confidence |

### 6.6 Model YOLO (opsional)

Di `models/best.pt` ada model YOLOv8 hasil training dengan 3 kelas (GO, SLOW, STOP).
Cara pakainya:

```bash
python3 src/main.py --method yolo
```

sayangnya model ini belum bisa dipakai di Jetson kami karena `ultralytics`
membutuhkan Python 3.8 ke atas, sedangkan Jetson memakai Python 3.6.9. Jadi kalau
`--method yolo` dipanggil, program otomatis turun ke metode `color_shape` dan
mencetak pesan peringatan. Metode `color_shape` sudah cukup untuk demo tugas ini.

---

## 7. Struktur Folder

```
AI-For-Robotic_Kelompok8/
├── README.md
├── config.py                 konfigurasi pin, HSV, ambang, dll
├── requirements.txt
├── src/
│   ├── main.py               pipeline utama
│   ├── camera.py             kamera CSI (GStreamer) dan USB (V4L2)
│   ├── sign_recognition.py   deteksi warna + bentuk, juga loader YOLO
│   ├── decision_logic.py     konfirmasi temporal dan kondisi aman
│   └── gpio_control.py       nyala/mati LED lewat Jetson.GPIO
├── tests/
│   └── test_pipeline.py      unit test
├── tools/
│   ├── hsv_calibration.py    kalibrasi warna
│   ├── capture_signs.py      ambil contoh frame + diagnosis
│   └── benchmark_detection.py
├── docs/
│   ├── ARCHITECTURE.md       detail arsitektur
│   └── WIRING.md             diagram rangkaian & langkah pemasangan
├── models/
│   └── best.pt               model YOLOv8 (opsional)
├── assets/signs/             gambar contoh rambu
└── results/                  screenshot dan log pengujian
```

Kalau mau mengganti metode pengenalan ke model AI lain, cukup ganti isi fungsi
`recognize()` di `src/sign_recognition.py` supaya mengembalikan objek `SignResult`.
Bagian decision logic dan GPIO tidak perlu disentuh.

---

## 8. Hasil Pengujian

Rincian pengujian ada di [`results/TEST_LOG.md`](results/TEST_LOG.md).

### 8.1 Unit test

`python3 tests/test_pipeline.py` → **13/13 lulus**. Menguji decision logic, pemetaan
LED, pengenalan ketiga rambu, dan penolakan rambu dengan bentuk yang salah.

### 8.2 Uji ketahanan

Empat jenis rambu (STOP, SLOW, GO hijau, GO biru) diuji dengan 14 kondisi berbeda:
normal, jauh, dekat sampai terpotong, rotasi, perspektif, gelap, terang, derau,
blur, warna pudar, pergeseran hue, dan resolusi turun. Hasilnya **56/56 benar**.

Rambu dengan warna benar tapi bentuk salah (misalnya segitiga merah atau oktagon
biru) semuanya ditolak, tidak salah terbaca.

### 8.3 Kecepatan

| Tahap | Sebelum | Sesudah |
|-------|--------:|--------:|
| Pengenalan | 70 ms (14 FPS) | 29 ms (34 FPS) |
| Pipeline penuh | — | 28 ms (36 FPS) |

Yang bikin cepat: deteksi dilakukan pada lebar 320 px, operasi morfologi memakai
kernel persegi, dan bentuk dihitung dari convex hull.

### 8.4 Pergantian rambu dan tanpa rambu

| Skenario | Hasil yang diharapkan |
|----------|----------------------|
| STOP → SLOW | LED merah → kuning |
| SLOW → GO | LED kuning → hijau |
| GO → tanpa rambu | LED hijau → semua mati |
| Keyakinan di bawah ambang | semua LED mati |

### 8.5 Screenshot

| STOP | SLOW | GO (biru + panah putih) |
|---|---|---|
| ![preview stop](results/preview_stop.jpg) | ![preview slow](results/preview_slow.jpg) | ![preview go biru](results/preview_go_biru_panah.jpg) |

| GO (hijau) | Tanpa rambu |
|---|---|
| ![preview go](results/preview_go.jpg) | ![preview nosign](results/preview_nosign.jpg) |

Gambar di atas dibuat secara sintetis untuk dokumentasi. Foto rambu dan LED fisik
asli ditambahkan di `results/` setelah uji lapangan.

### 8.6 Uji lapangan

| Rambu | 30 cm | 50 cm | 100 cm | LED sesuai? |
|-------|-------|-------|--------|-------------|
| STOP | | | | |
| SLOW | | | | |
| GO | | | | |

| Rambu | Terang | Redup |
|-------|--------|-------|
| STOP | | |
| SLOW | | |
| GO | | |

---

## 9. Catatan dan Kendala

- **Pin 15 tidak bisa dipakai.** GPIO22 (pin 15) dipakai driver fan di board ini,
  jadi `gpiochip` menolak kalau kita menulis ke sana. LED hijau sekarang di pin 16
  (GPIO23). Kalau butuh pin lain, tinggal ganti `LED_GREEN_PIN` di `config.py`.
- **OpenCV bawaan JetPack tidak punya GStreamer.** Kamera CSI hanya bisa dibaca
  lewat `nvarguscamerasrc`, itu yang dipakai `src/camera.py`.
- **`ultralytics` belum bisa dipasang** di Python 3.6.9, jadi model YOLO belum aktif.
- **Deteksi warna sensitif pada pencahayaan.** Kalau di tempat gelap rambu tidak
  terbaca, rentang HSV di `config.py` perlu disesuaikan.
- Angka desimal di dokumen ini ditulis dengan koma (0,55) sesuai kebiasaan bahasa
  Indonesia, sedangkan di `config.py` tetap memakai titik (0.55) karena itu format
  Python.

---

## 10. Anggota Kelompok

| Nama | NIM |
|------|-----|
| Bintang Ahmad | 2023071073 |
| Rais Fadillah | 2023071043 |
| Muhammad dapa | 2023071036 |
| Jehan padillah | 2023071052 |
---

Lisensi MIT.
