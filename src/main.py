"""
Main pipeline: Camera → Sign Recognition → Decision Logic → GPIO → LED.

Jalankan:
  python3 src/main.py            # mode kamera nyata
  python3 src/main.py --mock     # mode mock (tanpa kamera/GPIO, untuk demo/CI)
  python3 src/main.py --image assets/signs/stop.jpg  # uji satu gambar
"""

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    CAMERA_INDEX, FRAME_WIDTH, FRAME_HEIGHT, MIN_CONFIDENCE,
    SHOW_PREVIEW, PREVIEW_WINDOW, USE_GSTREAMER_CAMERA, STABLE_FRAMES,
)
from src.decision_logic import DecisionEngine
from src.gpio_control import LEDController
from src.sign_recognition import recognize, recognize_dataset

# cv2 / annotate di-import lazy (hanya butuh mode kamera/image),
# agar mode --mock tetap jalan di environment tanpa OpenCV.
cv2 = None
annotate = None


def _ensure_cv2():
    """Import cv2 + annotate secara lazy."""
    global cv2, annotate
    if annotate is None:
        try:
            import cv2 as _cv2
            from src.sign_recognition import annotate as _ann
        except ImportError as e:
            raise RuntimeError(
                f"OpenCV belum terpasang ({e}). Install: pip install opencv-python "
                "atau gunakan --mock."
            )
        cv2 = _cv2
        annotate = _ann


def open_camera(index=CAMERA_INDEX, width=FRAME_WIDTH, height=FRAME_HEIGHT):
    """Buka kamera. CSI Jetson → GStreamer (nvarguscamerasrc); fallback V4L2."""
    _ensure_cv2()

    if USE_GSTREAMER_CAMERA:
        try:
            from src.camera import GSTCamera
            cap = GSTCamera(sensor_id=index, width=width, height=height, fps=30)
            if cap.isOpened():
                print(f"[CAM] Kamera CSI (nvarguscamerasrc) terbuka: "
                      f"sensor-id={index}, {width}x{height}")
                return cap
        except Exception as e:
            print(f"[CAM] GStreamer gagal ({e}). Coba V4L2/cv2.VideoCapture...")

    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"[CAM] Gagal buka kamera index {index}, mencoba /dev/video0...")
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Kamera tidak ditemukan. Gunakan --mock atau --image.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    # Wrap agar orientasi (flip) konsisten dengan kamera CSI
    try:
        from src.camera import V4L2Capture
        print(f"[CAM] Kamera V4L2 terbuka (index={index}, {width}x{height})")
        return V4L2Capture(cap)
    except Exception:
        print(f"[CAM] Kamera V4L2 terbuka (index={index}, {width}x{height})")
        return cap


def run_pipeline(frame, engine: DecisionEngine, led: LEDController, method: str = "color_shape"):
    """Proses satu frame → (annotated_frame, decision)."""
    _ensure_cv2()
    if method in ("dataset", "yolo"):
        result = recognize_dataset(frame, min_confidence=engine.min_confidence)
    else:
        result = recognize(frame, min_confidence=engine.min_confidence)
    decision = engine.update(result.sign, result.confidence)
    led.apply_decision(decision.sign)
    annotated = annotate(frame, result, led.last_states)
    return annotated, decision, result


def loop_camera(cap, engine, led, show=SHOW_PREVIEW, method: str = "color_shape"):
    _ensure_cv2()
    print("[PIPELINE] Loop kamera aktif. Tekan 'q' untuk keluar.")
    last_log = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[CAM] Frame gagal dibaca, keluar.")
                break
            annotated, decision, result = run_pipeline(frame, engine, led, method=method)

            # Throttle log ~5x/detik: print tiap frame memperlambat loop (terutama via SSH)
            now = time.time()
            if now - last_log >= 0.2:
                last_log = now
                status = "NO SIGN" if decision.is_safe else "ACTIVE"
                print(f"\r[PIPELINE] sign={decision.sign:5s} conf={result.confidence:.2f} "
                      f"LED={led.last_states} [{status}]", end="", flush=True)

            if show:
                cv2.imshow(PREVIEW_WINDOW, annotated)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    except KeyboardInterrupt:
        print("\n[PIPELINE] Dihentikan (Ctrl+C).")
    finally:
        cap.release()
        if show:
            cv2.destroyAllWindows()
        led.cleanup()


def run_image(path, engine, led, show=SHOW_PREVIEW, method: str = "color_shape",
              save_path=None):
    _ensure_cv2()
    frame = cv2.imread(path)
    if frame is None:
        raise FileNotFoundError(f"Gambar tidak ditemukan: {path}")
    # Ulangi beberapa frame agar konfirmasi temporal terpenuhi (satu gambar = statis)
    for _ in range(max(1, engine.stable_frames)):
        annotated, decision, result = run_pipeline(frame, engine, led, method=method)
    print(f"[IMAGE] {os.path.basename(path)} → sign={decision.sign} "
          f"conf={result.confidence:.2f} shape={result.shape_name or '-'} "
          f"color={result.color_name or '-'} safe={decision.is_safe} "
          f"LED={led.last_states}")
    if save_path:
        cv2.imwrite(save_path, annotated)
        print(f"[IMAGE] hasil disimpan: {save_path}")
    if show:
        cv2.imshow(PREVIEW_WINDOW, annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    led.cleanup()
    return decision


def run_mock_sequence(engine, led, show=False):
    """Urutan mock sign untuk demo tanpa hardware: STOP→SLOW→GO→NONE."""
    sequence = [
        ("STOP", 0.92), ("SLOW", 0.88), ("GO", 0.91),
        ("NONE", 0.10), ("STOP", 0.95),
    ]
    print("[MOCK] Menjalankan simulasi urutan sign...")
    for sign, conf in sequence:
        # Simulasi beberapa frame agar konfirmasi temporal terpenuhi.
        # NONE diberi durasi lebih lama agar melewati SAFE_HOLD_SECONDS.
        frames = 20 if sign == "NONE" else 5
        for _ in range(frames):
            decision = engine.update(sign, conf)
            led.apply_decision(decision.sign)
            time.sleep(0.05)
        print(f"  input={sign:4s} conf={conf:.2f} → decision={decision.sign:4s} "
              f"safe={decision.is_safe} LED={led.last_states}")
    led.cleanup()


def main():
    ap = argparse.ArgumentParser(description="Traffic Sign Recognition → LED (Jetson Nano)")
    ap.add_argument("--mock", action="store_true", help="Mode mock (tanpa kamera/GPIO)")
    ap.add_argument("--image", type=str, help="Jalankan pada satu gambar statis")
    ap.add_argument("--save", type=str, help="Simpan hasil anotasi gambar ke path ini")
    ap.add_argument("--method", type=str, choices=["color_shape", "yolo", "dataset"], default="color_shape",
                    help="Metode: color_shape (default), yolo (models/best.pt), atau alias dataset")
    ap.add_argument("--no-preview", action="store_true", help="Nonaktifkan jendela OpenCV")
    ap.add_argument("--min-conf", type=float, default=MIN_CONFIDENCE,
                    help=f"Threshold confidence (default {MIN_CONFIDENCE})")
    args = ap.parse_args()

    engine = DecisionEngine(min_confidence=args.min_conf,
                            stable_frames=STABLE_FRAMES)
    led = LEDController(use_mock=args.mock)
    show = SHOW_PREVIEW and not args.no_preview

    if args.mock:
        run_mock_sequence(engine, led)
        return

    if args.image:
        run_image(args.image, engine, led, show=show, method=args.method,
                  save_path=args.save)
        return

    cap = open_camera()
    loop_camera(cap, engine, led, show=show, method=args.method)


if __name__ == "__main__":
    main()
