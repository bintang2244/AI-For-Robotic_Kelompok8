"""
Ambil contoh frame tanda dari kamera + jalankan recognizer (untuk diagnosis).

PENTING: hentikan dulu aplikasi lain yang memakai kamera (Ctrl+C pada
`python3 src/main.py`), karena kamera hanya bisa dipakai satu proses.

Contoh:
  # berurutan: tampilkan STOP, lalu SLOW, lalu GO
  python3 tools/capture_signs.py

  # hanya satu tanda, 10 frame
  python3 tools/capture_signs.py --labels STOP --frames 10

  # mode bebas: rekam 15 detik sambil menunjukkan tanda bergantian
  python3 tools/capture_signs.py --live 15 --every 0.5

Hasil disimpan di results/captures/ (gambar + summary.json), sehingga bisa
diperiksa untuk kalibrasi.
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2

from src.main import open_camera
from src.sign_recognition import recognize, annotate


def _save(frame, result, path):
    led = {"red": result.sign == "STOP",
           "yellow": result.sign == "SLOW",
           "green": result.sign == "GO"}
    cv2.imwrite(path, annotate(frame, result, led))


def _report(label, frame, path, records):
    result = recognize(frame, min_confidence=0.55)
    _save(frame, result, path)
    ok = result.sign == label
    records.append({
        "label": label,
        "detected": result.sign,
        "confidence": result.confidence,
        "shape": result.shape_name,
        "color": result.color_name,
        "ok": ok,
    })
    print(f"  {os.path.basename(path):24s} -> {result.sign:4s} "
          f"conf={result.confidence:.2f} shape={result.shape_name or '-':9s} "
          f"{'OK' if ok else '<-- SALAH'}")
    return ok


def capture_labeled(cap, labels, frames, out_dir, records):
    total = ok_total = 0
    for label in labels:
        print(f"\n>>> Tunjukkan tanda {label} ke kamera.")
        input("    Tekan Enter jika sudah siap...")
        for i in range(3, 0, -1):
            print(f"    capture dalam {i}...", end="\r", flush=True)
            time.sleep(0.5)
        print("    capturing...          ")
        for i in range(frames):
            got, frame = cap.read()
            if not got or frame is None:
                print("    [CAM] gagal baca frame")
                continue
            path = os.path.join(out_dir, f"{label.lower()}_{i:02d}.jpg")
            ok = _report(label, frame, path, records)
            total += 1
            ok_total += int(ok)
            time.sleep(0.2)
    return ok_total, total


def capture_live(cap, seconds, every, out_dir, records):
    print(f"\n>>> Rekam {seconds:.0f} detik. Tunjukkan tanda bergantian.")
    t0 = time.time()
    i = 0
    while time.time() - t0 < seconds:
        got, frame = cap.read()
        if not got or frame is None:
            continue
        path = os.path.join(out_dir, f"live_{i:03d}.jpg")
        result = recognize(frame, min_confidence=0.55)
        _save(frame, result, path)
        records.append({
            "label": "?", "detected": result.sign,
            "confidence": result.confidence, "shape": result.shape_name,
            "color": result.color_name, "ok": None,
        })
        print(f"  live_{i:03d}: {result.sign:4s} conf={result.confidence:.2f} "
              f"shape={result.shape_name or '-'} color={result.color_name or '-'}")
        i += 1
        time.sleep(every)
    return 0, i


def main():
    ap = argparse.ArgumentParser(description="Capture frame tanda untuk diagnosis")
    ap.add_argument("--labels", nargs="+", default=["STOP", "SLOW", "GO"],
                    choices=["STOP", "SLOW", "GO"])
    ap.add_argument("--frames", type=int, default=8, help="frame per tanda")
    ap.add_argument("--live", type=float, default=0,
                    help="mode rekam bebas selama N detik")
    ap.add_argument("--every", type=float, default=0.5,
                    help="interval simpan pada mode --live")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "captures"))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    print("[CAPTURE] Membuka kamera...")
    print("[CAPTURE] Jika gagal: hentikan dulu `python3 src/main.py` (Ctrl+C).")
    cap = open_camera()
    time.sleep(0.8)
    records = []
    try:
        if args.live > 0:
            capture_live(cap, args.live, args.every, args.out, records)
        else:
            ok, total = capture_labeled(cap, args.labels, args.frames,
                                        args.out, records)
            if total:
                print(f"\nHASIL: {ok}/{total} frame terdeteksi benar "
                      f"({100.0 * ok / total:.0f}%)")
    finally:
        cap.release()
        summary = os.path.join(args.out, "summary.json")
        with open(summary, "w") as f:
            json.dump(records, f, indent=2)
        print(f"[CAPTURE] {len(records)} frame + summary disimpan di {args.out}")


if __name__ == "__main__":
    main()
