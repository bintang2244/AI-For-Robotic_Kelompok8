"""
Unit test pipeline sign recognition + decision logic.

Jalankan: python3 -m pytest tests/ -v
Atau:     python3 tests/test_pipeline.py

Catatan: test yang butuh OpenCV (cv2) akan di-skip otomatis jika
OpenCV belum terpasang (mis. di CI/dev box tanpa JetPack).
Test decision logic + GPIO mock berjalan penuh tanpa cv2.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import numpy as np
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

from src.decision_logic import DecisionEngine
from src.gpio_control import LEDController


# ---------- Test pure-Python (tanpa cv2) ----------

def test_decision_engine_stable():
    eng = DecisionEngine(min_confidence=0.5, stable_frames=3)
    for _ in range(3):
        d = eng.update("STOP", 0.9)
    assert d.sign == "STOP"
    assert not d.is_safe


def test_decision_engine_no_sign_all_off():
    eng = DecisionEngine(min_confidence=0.5, stable_frames=3, safe_hold_seconds=0)
    for _ in range(3):
        d = eng.update("STOP", 0.9)
    assert d.sign == "STOP"
    d = eng.update("NONE", 0.1)
    assert d.sign == "NONE"      # default SAFE_STATE="NONE" -> semua LED mati
    assert d.is_safe


def test_decision_engine_safe_state_stop_optional():
    eng = DecisionEngine(min_confidence=0.5, stable_frames=3, safe_state="STOP",
                         safe_hold_seconds=0)
    for _ in range(3):
        eng.update("GO", 0.9)
    d = eng.update("NONE", 0.1)
    assert d.sign == "STOP"      # jika SAFE_STATE diubah ke "STOP"
    assert d.is_safe


def test_decision_engine_low_confidence_safe():
    eng = DecisionEngine(min_confidence=0.55, stable_frames=1, safe_hold_seconds=0)
    d = eng.update("GO", 0.40)   # di bawah threshold
    assert d.sign == "NONE"      # tidak valid -> semua LED mati
    assert d.is_safe


def test_decision_engine_switch_sign():
    eng = DecisionEngine(min_confidence=0.5, stable_frames=2, safe_hold_seconds=0)
    for _ in range(2):
        eng.update("STOP", 0.9)
    for _ in range(2):
        d = eng.update("GO", 0.9)
    assert d.sign == "GO"


def test_led_mapping():
    led = LEDController(use_mock=True)
    led.apply_decision("STOP")
    assert led.last_states == {"red": True, "yellow": False, "green": False}
    led.apply_decision("SLOW")
    assert led.last_states == {"red": False, "yellow": True, "green": False}
    led.apply_decision("GO")
    assert led.last_states == {"red": False, "yellow": False, "green": True}
    led.all_off()
    assert led.last_states == {"red": False, "yellow": False, "green": False}


# ---------- Test butuh cv2 (skip jika tak tersedia) ----------

def _make_sign_frame(color_bgr, shape="octagon", size=180, border=True, text=""):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (60, 60, 60)
    cx, cy = 320, 240
    import math
    if shape == "octagon":
        pts = []
        for i in range(8):
            ang = math.pi / 8 + i * math.pi / 4
            pts.append([int(cx + size * math.cos(ang)), int(cy + size * math.sin(ang))])
        pts = np.array(pts, np.int32)
        cv2.fillPoly(frame, [pts], color_bgr)
        if border:
            cv2.polylines(frame, [pts], True, (255, 255, 255), 6)
    elif shape == "triangle":
        pts = np.array([[cx, cy - size], [cx - size, cy + size], [cx + size, cy + size]], np.int32)
        cv2.fillPoly(frame, [pts], color_bgr)
        if border:
            cv2.polylines(frame, [pts], True, (0, 0, 0), 6)
    elif shape == "circle":
        cv2.circle(frame, (cx, cy), size, color_bgr, -1)
        if border:
            cv2.circle(frame, (cx, cy), size, (255, 255, 255), 6)
    if text:
        ink = (0, 0, 0) if color_bgr == (0, 255, 255) else (255, 255, 255)
        cv2.putText(frame, text, (cx - size // 2, cy + size // 4),
                    cv2.FONT_HERSHEY_SIMPLEX, size / 150.0, ink, 3)
    return frame


def test_recognize_stop():
    if not HAS_CV2:
        print("  (skip: cv2 tidak tersedia)")
        return
    from src.sign_recognition import recognize
    frame = _make_sign_frame((0, 0, 255), "octagon", text="STOP")
    r = recognize(frame, min_confidence=0.55)
    assert r.sign == "STOP", f"Expected STOP, got {r.sign} conf={r.confidence}"
    assert r.confidence >= 0.7


def test_recognize_slow():
    if not HAS_CV2:
        print("  (skip: cv2 tidak tersedia)")
        return
    from src.sign_recognition import recognize
    frame = _make_sign_frame((0, 255, 255), "triangle", text="SLOW")
    r = recognize(frame, min_confidence=0.55)
    assert r.sign == "SLOW", f"Expected SLOW, got {r.sign} conf={r.confidence}"
    assert r.confidence >= 0.7


def test_recognize_go():
    if not HAS_CV2:
        print("  (skip: cv2 tidak tersedia)")
        return
    from src.sign_recognition import recognize
    frame = _make_sign_frame((0, 255, 0), "circle", text="GO")
    r = recognize(frame, min_confidence=0.55)
    assert r.sign == "GO", f"Expected GO, got {r.sign} conf={r.confidence}"
    assert r.confidence >= 0.7


def test_recognize_go_biru_panah():
    """GO versi biru + panah putih (tanda perintah)."""
    if not HAS_CV2:
        print("  (skip: cv2 tidak tersedia)")
        return
    from src.sign_recognition import recognize
    frame = _make_sign_frame((200, 80, 0), "circle", size=150)  # BGR biru
    cx, cy, s = 320, 240, 150
    cv2.rectangle(frame, (cx - 12, cy - 20), (cx + 12, cy + int(s * 0.65)),
                  (255, 255, 255), -1)
    cv2.fillPoly(frame, [np.array([[cx, cy - int(s * 0.75)],
                                   [cx - int(s * 0.32), cy - 5],
                                   [cx + int(s * 0.32), cy - 5]], np.int32)],
                 (255, 255, 255))
    r = recognize(frame, min_confidence=0.55)
    assert r.sign == "GO", f"Expected GO (biru+panah), got {r.sign} conf={r.confidence}"
    assert r.confidence >= 0.7


def test_reject_wrong_shape():
    """Warna benar tapi bentuk salah tidak boleh lolos (mis. SLOW→GO)."""
    if not HAS_CV2:
        print("  (skip: cv2 tidak tersedia)")
        return
    from src.sign_recognition import recognize
    cases = [
        ((0, 255, 0), "triangle"),     # hijau segitiga, bukan GO
        ((0, 255, 0), "octagon"),      # hijau oktagon, bukan GO
        ((200, 80, 0), "triangle"),    # biru segitiga, bukan GO
        ((200, 80, 0), "octagon"),     # biru oktagon, bukan GO
        ((0, 0, 255), "triangle"),     # merah segitiga, bukan STOP
        ((0, 0, 255), "circle"),       # merah lingkaran, bukan STOP
        ((0, 255, 255), "circle"),     # kuning lingkaran, bukan SLOW
    ]
    for color, shape in cases:
        r = recognize(_make_sign_frame(color, shape), min_confidence=0.55)
        assert r.sign == "NONE", f"{color}/{shape} harus NONE, dapat {r.sign}"


def test_bbox_diskalakan_ke_frame_asli():
    """Deteksi di PROCESS_WIDTH=320 harus mengembalikan bbox skala frame asli."""
    if not HAS_CV2:
        print("  (skip: cv2 tidak tersedia)")
        return
    from src.sign_recognition import recognize
    frame = _make_sign_frame((0, 0, 255), "octagon", size=150, border=False)
    r = recognize(frame, min_confidence=0.55, process_width=320)
    assert r.sign == "STOP" and r.bbox is not None
    x, y, w, h = r.bbox
    assert 80 < x < 260 and 80 < y < 260, f"bbox tidak wajar: {r.bbox}"
    assert 200 < w < 400 and 200 < h < 400, f"bbox tidak wajar: {r.bbox}"


def test_no_sign_safe():
    if not HAS_CV2:
        print("  (skip: cv2 tidak tersedia)")
        return
    from src.sign_recognition import recognize
    frame = np.full((480, 640, 3), 60, dtype=np.uint8)
    r = recognize(frame, min_confidence=0.5)
    assert r.sign == "NONE"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
