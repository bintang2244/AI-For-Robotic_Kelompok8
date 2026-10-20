"""
Benchmark & batch-test deteksi color_shape.

Contoh:
  # ukur FPS pada gambar (default: gambar sintetis STOP)
  python3 tools/benchmark_detection.py --bench

  # uji semua gambar di folder, simpan hasil anotasi
  python3 tools/benchmark_detection.py --dir assets/signs --save-dir results/eval

  # pastikan semua gambar di folder memang STOP
  python3 tools/benchmark_detection.py --dir fotos_stop --expect STOP

  # uji satu/beberapa file
  python3 tools/benchmark_detection.py a.jpg b.png
"""

import argparse
import glob
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2
import numpy as np

from src.sign_recognition import recognize, annotate

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def _synthetic(kind="STOP", w=640, h=480, size=150):
    frame = np.full((h, w, 3), 70, np.uint8)
    cx, cy = w // 2, h // 2
    if kind == "STOP":
        pts = [[int(cx + size * np.cos(np.pi / 8 + i * np.pi / 4)),
                int(cy + size * np.sin(np.pi / 8 + i * np.pi / 4))] for i in range(8)]
        cv2.fillPoly(frame, [np.array(pts, np.int32)], (0, 0, 220))
        cv2.polylines(frame, [np.array(pts, np.int32)], True, (255, 255, 255), 6)
        cv2.putText(frame, "STOP", (cx - 70, cy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3)
    elif kind == "SLOW":
        pts = np.array([[cx, cy - size], [cx - size, cy + size],
                        [cx + size, cy + size]], np.int32)
        cv2.fillPoly(frame, [pts], (0, 220, 220))
        cv2.polylines(frame, [pts], True, (0, 0, 0), 6)
    else:
        cv2.circle(frame, (cx, cy), size, (0, 200, 0), -1)
        cv2.circle(frame, (cx, cy), size, (255, 255, 255), 6)
    return frame


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for ext in IMG_EXT:
                files.extend(glob.glob(os.path.join(p, "*" + ext)))
                files.extend(glob.glob(os.path.join(p, "*" + ext.upper())))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print(f"[SKIP] tidak ditemukan: {p}")
    return sorted(set(files))


def run_batch(files, save_dir=None, expect=None, min_conf=0.55):
    if not files:
        print("Tidak ada gambar. Pakai --dir FOLDER atau daftar file.")
        return 1
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    ok = 0
    for path in files:
        frame = cv2.imread(path)
        if frame is None:
            print(f"[SKIP] gagal baca: {path}")
            continue
        t0 = time.time()
        result = recognize(frame, min_confidence=min_conf)
        ms = (time.time() - t0) * 1000.0
        good = expect is None or result.sign == expect
        ok += int(good)
        status = "" if good else "  <-- SALAH"
        print(f"{os.path.basename(path):28s} -> {result.sign:4s} "
              f"conf={result.confidence:.2f} shape={result.shape_name or '-':9s} "
              f"{ms:5.1f} ms{status}")
        if save_dir:
            led = {"red": result.sign == "STOP",
                   "yellow": result.sign == "SLOW",
                   "green": result.sign == "GO"}
            cv2.imwrite(os.path.join(save_dir, os.path.basename(path)),
                        annotate(frame, result, led))

    if expect is not None:
        print(f"\nAkurasi: {ok}/{len(files)} ({100.0 * ok / len(files):.0f}%) "
              f"diharapkan {expect}")
    return 0 if (expect is None or ok == len(files)) else 2


def run_bench(kind="STOP", n=150):
    frame = _synthetic(kind)
    recognize(frame)  # warm-up
    t0 = time.time()
    for _ in range(n):
        recognize(frame)
    ms = (time.time() - t0) / n * 1000.0
    print(f"Benchmark {kind}: {ms:.1f} ms/frame -> {1000.0 / ms:.1f} FPS "
          f"({n} frame, 640x480)")


def main():
    ap = argparse.ArgumentParser(description="Benchmark / batch-test deteksi tanda")
    ap.add_argument("files", nargs="*", help="file gambar atau folder")
    ap.add_argument("--dir", action="append", default=[], help="folder gambar (bisa diulang)")
    ap.add_argument("--save-dir", help="simpan hasil anotasi ke folder ini")
    ap.add_argument("--expect", choices=["STOP", "SLOW", "GO"], help="label yang diharapkan")
    ap.add_argument("--bench", action="store_true", help="ukur FPS pada gambar sintetis")
    ap.add_argument("--bench-kind", choices=["STOP", "SLOW", "GO"], default="STOP")
    ap.add_argument("--min-conf", type=float, default=0.55)
    args = ap.parse_args()

    if args.bench:
        run_bench(args.bench_kind)
        return 0
    return run_batch(collect(args.files + args.dir), args.save_dir,
                     args.expect, args.min_conf)


if __name__ == "__main__":
    sys.exit(main())
