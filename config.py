"""
Konfigurasi global sistem Traffic Sign Recognition.
"""

import os

# --- Kamera ---
CAMERA_INDEX = 0            # indeks kamera (CSI: sensor-id; USB: /dev/videoN)
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS = 30
# Jetson CSI camera (imx219/RPi cam) WAJIB lewat nvarguscamerasrc (GStreamer),
# karena V4L2 biasa menghasilkan frame hijau. Set False jika pakai USB webcam.
USE_GSTREAMER_CAMERA = True
# Orientasi kamera: "none" | "horizontal" (mirror kiri-kanan) |
# "vertical" (terbalik atas-bawah) | "rotate180" (putar 180°)
CAMERA_FLIP = "rotate180"

# --- GPIO Pin (Jetson Nano BOARD / header pin) ---
# Wiring: LED merah  → pin 11 (GPIO17)
#         LED kuning → pin 13 (GPIO27)
#         LED hijau  → pin 16 (GPIO23)
# Catatan: pin 15 (GPIO22) dipakai driver fan/carrier board di Jetson ini
#          (sysfs gpio194 sibuk), jadi LED hijau dipindah ke pin 16.
LED_RED_PIN = 11
LED_YELLOW_PIN = 13
LED_GREEN_PIN = 16
LED_ACTIVE_HIGH = True      # True jika resistor ke GND (LED nyala saat HIGH)

# --- Recognisi ---
MIN_CONFIDENCE = 0.55       # threshold minimum agar sign diterima
PROCESS_WIDTH = 320         # deteksi pada lebar ini (0 = full frame) → lebih cepat
MIN_AREA_RATIO = 0.004      # area kontur minimum relatif frame kerja (0.4%)
STABLE_FRAMES = 2           # konfirmasi temporal (kecil = respons lebih cepat)

# --- HSV Ranges (OpenCV: H 0-179, S 0-255, V 0-255) ---
# Toleran untuk indoor, layar, dan print (cahaya redup / warna agak pudar).
# Kalibrasi ulang dengan tools/hsv_calibration.py bila perlu.
HSV_RANGES = {
    "red": [
        ((0, 70, 45), (15, 255, 255)),      # merah hue rendah (termasuk oranye-merah)
        ((165, 70, 45), (180, 255, 255)),   # merah hue tinggi
    ],
    "yellow": [((14, 60, 55), (38, 255, 255))],
    "green": [((36, 45, 45), (100, 255, 255))],
    # GO versi biru + panah putih (tanda perintah). Panah putih tidak masuk
    # mask karena saturasinya rendah; kontur luar tetap bentuk tanda.
    # Range lebar (90-145) mencakup cyan/biru tua; S/V rendah untuk biru gelap.
    "blue": [((90, 30, 25), (145, 255, 255))],
}

# Penutupan morfologi ekstra untuk biru: menutup celah panah putih yang
# memotong tanda menjadi dua bagian (ukuran diskalakan terhadap PROCESS_WIDTH).
BLUE_CLOSE_SIZE = 21

# Mapping warna dominan → sign
COLOR_TO_SIGN = {
    "red": "STOP",
    "yellow": "SLOW",
    "green": "GO",
    "blue": "GO",
}

# --- Model AI (YOLOv8) ---
# File model hasil training. Rekonstruksi dari arsip torch di
# /home/roypetani/Unduhan/base/best → models/best.pt
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "best.pt")
# Mapping nama kelas model → sign sistem. Model dilatih dengan kelas GO/SLOW/STOP.
MODEL_CLASS_MAP = {
    "GO": "GO",
    "SLOW": "SLOW",
    "STOP": "STOP",
}

# --- Decision Logic ---
# Kondisi tanpa sign / confidence < threshold.
# "NONE" = semua LED mati (perilaku demo yang diminta).
# Ganti ke "STOP" jika ingin safe-state merah (fail-safe kendaraan).
SAFE_STATE = "NONE"
SAFE_HOLD_SECONDS = 0.5     # tahan LED terakhir sebentar agar tidak flicker

# --- Display ---
SHOW_PREVIEW = True         # tampilkan jendela OpenCV (matikan di headless)
PREVIEW_WINDOW = "Traffic Sign Recognition"
