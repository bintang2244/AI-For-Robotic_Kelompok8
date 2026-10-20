# Wiring & Kalibrasi

## Rangkaian LED (Breadboard → Jetson Nano)

### Tabel koneksi

| LED | Kaki LED | Breadboard | Resistor 220Ω | Jumper ke Jetson |
|-----|----------|------------|---------------|------------------|
| Merah (STOP) | Anode (kaki panjang) | e5 | b5 ↔ b2 | a2 → **pin 11** (GPIO17) |
| Merah (STOP) | Katode (kaki pendek) | f5 | — | f5 → rel GND |
| Kuning (SLOW) | Anode | e10 | b10 ↔ b7 | a7 → **pin 13** (GPIO27) |
| Kuning (SLOW) | Katode | f10 | — | f10 → rel GND |
| Hijau (GO) | Anode | e15 | b15 ↔ b12 | a12 → **pin 16** (GPIO23) |
| Hijau (GO) | Katode | f15 | — | f15 → rel GND |
| GND | — | rel GND (strip −) | — | rel GND → **pin 6** (GND) |

> Nomor baris breadboard hanya contoh. Pola wajibnya: **GPIO → resistor → anode
> (kaki panjang) → katode (kaki pendek) → GND**. Semua katode boleh disatukan ke
> satu rel GND.
>
> **Catatan Jetson ini:** pin 15 (GPIO22) dipakai driver fan/carrier board
> (sysfs gpio194 sibuk), sehingga LED hijau memakai **pin 16 (GPIO23)**.

### Diagram

```
Jetson Nano 40-pin (BOARD)        Breadboard
──────────────────────────        ──────────────────────────────────────────
Pin 11 (GPIO17) ──jumper──► a2 ─[220Ω]─ b2···b5 ─(baris 5)─ e5 ─►|─ f5 ──┐
Pin 13 (GPIO27) ──jumper──► a7 ─[220Ω]─ b7···b10 ─(baris 10)─ e10 ─►|─ f10 ─┤
Pin 16 (GPIO23) ──jumper──► a12 ─[220Ω]─ b12···b15 ─(baris 15)─ e15 ─►|─ f15 ─┤
Pin 6  (GND)    ──jumper──► rel GND (−) ◄──────────────────────────────────┘
```

Legenda:
- `►|` = LED; **kaki panjang (anode)** di kolom e, **kaki pendek (katode)** di f.
- `[220Ω]` = resistor 220Ω (merah-merah-coklat-emas).
- `···` = resistor membentang dari baris b2 ke b5 (jarak 3 lubang ≈ 7,6 mm).
- Satu baris a–e (dan f–j) pada breadboard tersambung internal.

### Langkah pemasangan
1. Tancapkan 3 LED melintang di tengah breadboard: baris **5** (merah), **10**
   (kuning), **15** (hijau). Kaki panjang di kolom **e**, kaki pendek di **f**.
2. Pasang resistor 220Ω: **b5–b2**, **b10–b7**, **b15–b12**.
3. Jumper: **a2 → pin 11**, **a7 → pin 13**, **a12 → pin 16**.
4. Jumper **f5, f10, f15** ke rel **GND (−)** breadboard.
5. Jumper rel GND ke **pin 6** Jetson.
6. Tidak perlu mengambil 5V/3.3V dari Jetson ke breadboard; LED disuplai dari pin GPIO.

### Arus & keamanan
- GPIO Jetson Nano = **3,3V**, arus aman ≤ ±16 mA per pin. Dengan 220Ω:
  merah ≈ (3,3−2,0)/220 ≈ **6 mA**; hijau ≈ (3,3−2,1)/220 ≈ **5,5 mA**.
- **Gunakan 220Ω untuk ketiga LED.** Jika LED redup, cek polaritas, koneksi
  resistor, dan rel GND — jangan melepas resistor (GPIO bisa rusak).
- **Jangan** hubungkan pin 5V ke GPIO. Gunakan **BOARD numbering** (nomor fisik
  header), sesuai `LED_*_PIN` di `config.py`.
- Pastikan GND Jetson dan GND breadboard tersambung (**common ground**).

### Tabel Pin

| Fungsi | BOARD pin | BCM/GPIO | Warna LED |
|--------|-----------|----------|-----------|
| STOP  | 11 | GPIO17 | Merah |
| SLOW  | 13 | GPIO27 | Kuning |
| GO    | 16 | GPIO23 | Hijau |
| GND   | 6  | —      | — |

Ubah pin di `config.py`:
```python
LED_RED_PIN = 11
LED_YELLOW_PIN = 13
LED_GREEN_PIN = 16
LED_ACTIVE_HIGH = True   # False jika rangkaian aktif-LOW
```

## Kamera

- **USB**: cukup colok ke port USB; `CAMERA_INDEX = 0`,
  dan set `USE_GSTREAMER_CAMERA = False` di `config.py`.
- **CSI (Raspberry Pi Camera / imx219)**:
  Kamera CSI **tidak bisa** dibaca dengan `cv2.VideoCapture()` biasa
  (hasilnya frame hijau) karena OpenCV bawaan JetPack sering dibuild tanpa
  GStreamer. Sistem ini memakai `src/camera.py` (nvarguscamerasrc → appsink).

  Pastikan paket ini terpasang:
  ```bash
  sudo apt-get install -y python3-gi gir1.2-gstreamer-1.0
  ```

  `config.py`:
  ```python
  USE_GSTREAMER_CAMERA = True   # True untuk kamera CSI
  CAMERA_INDEX = 0              # sensor-id CSI (0 atau 1)
  ```

  Cek feed CSI langsung dari terminal:
  ```bash
  gst-launch-1.0 nvarguscamerasrc sensor-id=0 ! \
    'video/x-raw(memory:NVMM),width=640,height=480,framerate=30/1' ! \
    nvvidconv ! 'video/x-raw,format=BGRx' ! videoconvert ! \
    'video/x-raw,format=BGR' ! xvimagesink
  ```

## Kalibrasi HSV

Warna sign terlihat berbeda tergantung pencahayaan. Kalibrasi:
1. Ambil frame: `cap.read()`, simpan ROI sign.
2. Buka trackbar HSV (contoh skrip di bawah) dan geser sampai mask sign penuh.
3. Salin nilai `lo` & `hi` ke `HSV_RANGES` di `config.py`.

```python
# tools/hsv_calibration.py (contoh)
import cv2, numpy as np
def nothing(_): pass
cv2.namedWindow("track")
for i, n in enumerate(["HL","HH","SL","SH","VL","VH"]):
    cv2.createTrackbar(n, "track", 0, 180 if i<2 else 255, nothing)
cap = cv2.VideoCapture(0)
while True:
    _, f = cap.read()
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    hl,hh,sl,sh,vl,vh = [cv2.getTrackbarPos(n,"track") for n in ["HL","HH","SL","SH","VL","VH"]]
    mask = cv2.inRange(hsv, (hl,sl,vl), (hh,sh,vh))
    cv2.imshow("mask", mask)
    if cv2.waitKey(1)&0xFF==27: break
```

### Range default (indoor)
| Warna | H range | S range | V range |
|-------|---------|---------|---------|
| Merah | 0–10 & 170–180 | 120–255 | 70–255 |
| Kuning | 20–35 | 100–255 | 100–255 |
| Hijau | 40–85 | 70–255 | 70–255 |

> Untuk outdoor / cahaya fluorescent, rentang S & V perlu diturunkan.

## Fail-safe
Perilaku software default: tanpa sign → **semua LED mati** (`SAFE_STATE = "NONE"`).
Jika ingin kondisi aman kendaraan (merah menyala), ubah `SAFE_STATE = "STOP"`.

Untuk fail-safe keras (LED merah menyala saat MCU/Jetson hang), gunakan transistor
MOSFET antara VCC→LED merah dengan gate di-DEFAULT-HIGH via pull-up, sehingga saat
GPIO tidak aktif (reset/hang) LED merah tetap menyala. Konfigurasi ini di luar scope
software default tapi disarankan untuk implementasi kendaraan nyata.
