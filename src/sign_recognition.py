"""
Modul pengenalan traffic sign (STOP / SLOW / GO).

Metode 1 — color_shape (default, cepat, tanpa dependensi model):
  frame → resize (PROCESS_WIDTH) → HSV → mask per warna → kontur
        → convex hull → klasifikasi bentuk → skor → SignResult

Metode 2 — yolo (opsional):
  model YOLOv8 di models/best.pt (butuh `ultralytics`, Python >= 3.8).
  Jika tidak tersedia, otomatis fallback ke color_shape.

Kunci akurasi color_shape:
  - Bentuk dinilai dari CONVEX HULL, sehingga teks/border/ikon di dalam
    tanda tidak merusak bentuk.
  - Fill-ratio = luas hull / luas lingkaran pembungkus:
        segitiga ≈ 0.43 | persegi ≈ 0.65 | oktagon ≈ 0.90 | lingkaran ≈ 1.00
    Metrik ini jauh lebih stabil daripada jumlah vertex saja.
  - Bentuk WAJIB cocok dengan jenis tanda; jika tidak, skor maksimum 0.40
    (di bawah threshold 0.55) sehingga objek berwarna salah tidak lolos.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

import math
import os
import sys

try:
    import cv2
    _HAS_CV2 = True
except ModuleNotFoundError:
    _HAS_CV2 = False

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    HSV_RANGES, COLOR_TO_SIGN, MIN_CONFIDENCE, PROCESS_WIDTH, MIN_AREA_RATIO,
    MODEL_PATH, MODEL_CLASS_MAP, BLUE_CLOSE_SIZE,
)

# Bobot skor (jumlah 1.0). Bentuk dominan agar warna salah tidak lolos.
W_COLOR, W_SHAPE, W_SIZE = 0.30, 0.60, 0.10
# Coverage warna yang dianggap "penuh"; tanda nyata punya teks/border putih.
COLOR_FULL_COVERAGE = 0.55

# Bentuk yang valid untuk tiap tanda.
EXPECTED_SHAPES = {
    "STOP": {"octagon"},
    "SLOW": {"triangle"},
    "GO": {"circle", "rectangle"},
}

_HAS_MODEL = False
_model = None
_CLASS_NAMES = {}

_KERNEL_CACHE = {}


@dataclass
class SignResult:
    sign: str                 # "STOP" | "SLOW" | "GO" | "NONE"
    confidence: float         # 0.0 - 1.0
    bbox: Optional[Tuple[int, int, int, int]] = None   # x, y, w, h (frame asli)
    color_name: str = ""
    shape_name: str = ""
    raw_score: float = 0.0


# --------------------------------------------------------------------------
# Model YOLO (opsional)
# --------------------------------------------------------------------------
def _init_model():
    """Muat model YOLOv8 sekali (di-cache). Gagal → fallback color_shape."""
    global _HAS_MODEL, _model, _CLASS_NAMES
    if _HAS_MODEL:
        return
    try:
        from ultralytics import YOLO
        _model = YOLO(MODEL_PATH)
        _CLASS_NAMES = getattr(_model, "names", {}) or {}
        print(f"[MODEL] YOLO dimuat: {MODEL_PATH} | classes={_CLASS_NAMES}")
        _HAS_MODEL = True
    except Exception as e:
        print(f"[MODEL] Gagal load YOLO ({e}). Fallback ke color+shape.")


def _map_class_to_sign(class_name: str) -> str:
    """Mapping nama kelas model → STOP / SLOW / GO (atau NONE)."""
    name = str(class_name)
    if name in MODEL_CLASS_MAP:
        return MODEL_CLASS_MAP[name]
    lower = name.lower()
    if "stop" in lower:
        return "STOP"
    if "slow" in lower:
        return "SLOW"
    if lower.strip() == "go" or "green" in lower or "proceed" in lower:
        return "GO"
    return "NONE"


# --------------------------------------------------------------------------
# Utilitas segmentasi
# --------------------------------------------------------------------------
def _morph_kernels(width: int):
    """
    Kernel morfologi: open 3x3 (buang noise) + close lebih besar (rapatkan teks).
    Memakai kernel PERSEGI (rect) karena OpenCV mengoptimalkannya secara
    separable — di Jetson ~4x lebih cepat daripada kernel ellipse.
    """
    close = max(5, int(round((width or 640) / 48.0)) | 1)
    if close not in _KERNEL_CACHE:
        _KERNEL_CACHE[close] = (np.ones((3, 3), np.uint8),
                                np.ones((close, close), np.uint8))
    return _KERNEL_CACHE[close]


def _mask_for_color(hsv: np.ndarray, color_name: str, kernels) -> np.ndarray:
    """Gabungkan semua range HSV satu warna → mask biner bersih."""
    open_k, close_k = kernels
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in HSV_RANGES.get(color_name, []):
        mask = cv2.bitwise_or(mask, cv2.inRange(hsv, np.array(lo, np.uint8),
                                                 np.array(hi, np.uint8)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
    if color_name == "blue":
        # Panah putih besar bisa memotong tanda biru jadi dua kontur.
        # Close ekstra menyatukannya kembali (lihat BLUE_CLOSE_SIZE).
        k = max(15, int(round(BLUE_CLOSE_SIZE * hsv.shape[1] / 320.0)) | 1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    return mask


def _color_coverage(mask: np.ndarray, hull: np.ndarray) -> float:
    """Fraksi piksel warna target di dalam convex hull (0..1)."""
    x, y, w, h = cv2.boundingRect(hull)
    if w <= 0 or h <= 0:
        return 0.0
    fill = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(fill, [hull - (x, y)], -1, 255, -1)
    total = cv2.countNonZero(fill)
    if total == 0:
        return 0.0
    inside = cv2.countNonZero(cv2.bitwise_and(mask[y:y + h, x:x + w], fill))
    return inside / float(total)


def _classify_shape(hull: np.ndarray, expected=None,
                    touching_border: bool = False) -> Tuple[str, float]:
    """
    Klasifikasi bentuk dari convex hull.
    Mengembalikan (nama_bentuk, skor 0..1).

    Fill-ratio (luas hull / luas lingkaran pembungkus) memisahkan bentuk
    dengan jelas: segitiga ≈0.43, persegi ≈0.65, oktagon ≈0.90, lingkaran ≈1.00.
    `expected` = bentuk valid untuk warna tsb; dipakai sebagai fallback toleran.
    `touching_border` = tanda terpotong tepi frame (mis. dipegang sangat dekat).
    """
    peri = cv2.arcLength(hull, True)
    area = cv2.contourArea(hull)
    if peri <= 0 or area <= 0:
        return "unknown", 0.0

    (_, _), radius = cv2.minEnclosingCircle(hull)
    if radius <= 0:
        return "unknown", 0.0
    fill = area / (math.pi * radius * radius)
    circularity = 4.0 * math.pi * area / (peri * peri)

    x, y, w, h = cv2.boundingRect(hull)
    extent = area / float(w * h) if w > 0 and h > 0 else 0.0
    aspect = max(w, h) / float(min(w, h) + 1e-6)

    vc = len(cv2.approxPolyDP(hull, 0.020 * peri, True))   # kasar
    vf = len(cv2.approxPolyDP(hull, 0.008 * peri, True))   # halus

    shape, score = "unknown", 0.0

    # --- Aturan ketat ---
    # extent < 0.75 mencegah persegi panjang (extent≈1.0) terbaca sebagai segitiga.
    if ((vc == 3 and fill < 0.70) or
            (fill < 0.57 and circularity < 0.78 and vc <= 5)) and extent < 0.75:
        shape, score = "triangle", 1.0
    elif vc == 4 and extent > 0.85 and 0.55 <= fill < 0.80 and aspect <= 2.2:
        shape, score = "rectangle", 0.85
    elif fill >= 0.955 and circularity > 0.85:
        shape, score = "circle", 1.0
    elif 0.78 <= fill < 0.955 and 7 <= vc <= 10 and vf <= 12:
        shape, score = "octagon", 1.0
    elif fill >= 0.86 and vf >= 13 and circularity > 0.90:
        shape, score = "circle", 0.95

    if expected is None or shape in expected:
        return shape, score

    # --- Fallback toleran: geometri masih konsisten dengan warna tersebut? ---
    # Catatan: aturan dibuat agar warna salah-bentuk tetap ditolak.
    if "triangle" in expected and fill < 0.66 and circularity < 0.90 and extent < 0.75:
        return "triangle", 0.80
    if "octagon" in expected and 0.74 <= fill < 0.97 and vc >= 5:
        return "octagon", 0.80
    if "circle" in expected and fill >= 0.74 and (touching_border or fill >= 0.93):
        return "circle", 0.80
    if "rectangle" in expected and 0.55 <= fill < 0.88 and vc == 4:
        return "rectangle", 0.80
    return "unknown", 0.0


# --------------------------------------------------------------------------
# API utama
# --------------------------------------------------------------------------
def recognize(frame: np.ndarray, min_confidence: float = MIN_CONFIDENCE,
              process_width: Optional[int] = None) -> SignResult:
    """
    Deteksi satu tanda pada frame.
    process_width: lebar kerja deteksi (default config.PROCESS_WIDTH; 0 = full).
    """
    if frame is None or frame.size == 0:
        return SignResult(sign="NONE", confidence=0.0)

    h0, w0 = frame.shape[:2]
    pw = PROCESS_WIDTH if process_width is None else process_width

    scale = 1.0
    if pw and w0 > pw:
        scale = pw / float(w0)
        small = cv2.resize(frame, (pw, max(1, int(round(h0 * scale)))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = frame

    h, w = small.shape[:2]
    frame_area = float(h * w)
    min_area = max(40.0, MIN_AREA_RATIO * frame_area)

    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    kernels = _morph_kernels(w)

    best = SignResult(sign="NONE", confidence=0.0)

    for color_name, ranges in HSV_RANGES.items():
        if not ranges:
            continue
        mask = _mask_for_color(hsv, color_name, kernels)
        cnts = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = cnts[0] if len(cnts) == 2 else cnts[1]
        if not contours:
            continue

        expected = EXPECTED_SHAPES.get(COLOR_TO_SIGN.get(color_name, ""), set())
        for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
            area = cv2.contourArea(cnt)
            # Izinkan tanda besar (dipegang dekat); tolak hanya hampir seluruh frame
            if area < min_area or area / frame_area > 0.85:
                continue

            hull = cv2.convexHull(cnt)
            bx, by, bw, bh = cv2.boundingRect(hull)
            touching = (bx <= 1 or by <= 1 or
                        bx + bw >= w - 1 or by + bh >= h - 1)
            shape_name, shape_score = _classify_shape(hull, expected, touching)
            if shape_name not in expected:
                continue

            coverage = _color_coverage(mask, hull)
            color_match = min(1.0, coverage / COLOR_FULL_COVERAGE)

            rel = area / frame_area
            if 0.006 <= rel <= 0.50:
                size_match = 1.0
            elif rel < 0.006:
                size_match = 0.70
            else:
                size_match = 0.85

            raw = (W_COLOR * color_match + W_SHAPE * shape_score
                   + W_SIZE * size_match)
            confidence = min(1.0, raw)
            if confidence <= best.confidence:
                continue

            x, y, out_w, out_h = bx, by, bw, bh
            if scale != 1.0:
                inv = 1.0 / scale
                x, y = int(bx * inv), int(by * inv)
                out_w, out_h = int(bw * inv), int(bh * inv)
            best = SignResult(
                sign=COLOR_TO_SIGN[color_name],
                confidence=round(confidence, 3),
                bbox=(x, y, out_w, out_h),
                color_name=color_name,
                shape_name=shape_name,
                raw_score=round(raw, 3),
            )

    if best.confidence < min_confidence:
        return SignResult(sign="NONE", confidence=round(best.confidence, 3),
                          color_name=best.color_name, shape_name=best.shape_name)
    return best


def recognize_dataset(frame: np.ndarray,
                      min_confidence: float = MIN_CONFIDENCE) -> SignResult:
    """Deteksi dengan model YOLOv8; fallback ke color_shape bila tidak tersedia."""
    global _HAS_MODEL, _model
    if not _HAS_MODEL:
        _init_model()
    if not _HAS_MODEL or _model is None:
        print("[RECOG] Model YOLO tidak tersedia, fallback ke color+shape")
        return recognize(frame, min_confidence)

    try:
        res = _model(frame, verbose=False, conf=min_confidence)[0]
        boxes = getattr(res, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return SignResult(sign="NONE", confidence=0.0)

        confs = boxes.conf.cpu().numpy()
        i = int(confs.argmax())
        confidence = float(confs[i])
        cls_id = int(boxes.cls[i].cpu().numpy().item())
        names = getattr(res, "names", {}) or _CLASS_NAMES
        class_name = (names.get(cls_id, str(cls_id))
                      if isinstance(names, dict) else str(cls_id))
        sign = _map_class_to_sign(class_name)

        x1, y1, x2, y2 = [int(v) for v in boxes.xyxy[i].cpu().numpy().tolist()]
        bbox = (x1, y1, x2 - x1, y2 - y1)

        if confidence < min_confidence or sign == "NONE":
            return SignResult(sign="NONE", confidence=round(confidence, 3),
                              bbox=bbox)
        return SignResult(sign=sign, confidence=round(confidence, 3), bbox=bbox,
                          raw_score=round(confidence, 3))
    except Exception as e:
        print(f"[MODEL] Error inferensi: {e}")
        return recognize(frame, min_confidence)


def annotate(frame: np.ndarray, result: SignResult, led_status: dict) -> np.ndarray:
    """Gambar overlay: bbox + label sign + confidence + status LED."""
    out = frame.copy()
    if result.bbox:
        x, y, w, h = result.bbox
        color = (0, 255, 0) if result.sign != "NONE" else (0, 0, 255)
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)

    label = f"{result.sign} ({result.confidence:.2f})"
    if result.sign == "NONE":
        label = f"NONE (conf={result.confidence:.2f}) -> LED OFF"

    cv2.rectangle(out, (0, 0), (out.shape[1], 70), (30, 30, 30), -1)
    cv2.putText(out, f"Sign: {label}", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    led_txt = "  ".join(f"{k.upper()}={'ON' if v else 'OFF'}"
                        for k, v in led_status.items())
    cv2.putText(out, f"LED: {led_txt}", (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    return out
