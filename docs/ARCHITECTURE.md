# Arsitektur Sistem

## Diagram Alir Besar

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Jetson Nano (SBC)                            │
│                                                                      │
│  ┌────────┐   frame   ┌────────────────────┐   SignResult            │
│  │ Camera │──────────►│  Sign Recognition  │───────────┐            │
│  │ (USB/  │  640×480  │  src/sign_         │ sign,conf │            │
│  │  CSI)  │  @30fps   │  recognition.py    │ bbox      │            │
│  └────────┘           └────────────────────┘           ▼            │
│                                              ┌──────────────────┐   │
│                                              │  Decision Logic  │   │
│                                              │  src/decision_   │   │
│                                              │  logic.py        │   │
│                                              │  • temporal N-fr │   │
│                                              │  • threshold     │   │
│                                              │  • safe-state    │   │
│                                              └────────┬─────────┘   │
│                                                       │ sign        │
│                        ┌──────────────────────────────▼──────────┐  │
│                        │           GPIO Controller               │  │
│                        │  src/gpio_control.py (Jetson.GPIO)      │  │
│                        └───────┬──────────┬──────────┬───────────┘  │
│                                │          │          │              │
└────────────────────────────────┼──────────┼──────────┼──────────────┘
                                 ▼          ▼          ▼
                              ┌─────┐   ┌─────┐   ┌─────┐
                              │ LED │   │ LED │   │ LED │
                              │Merah│   │Kuning│  │Hijau│
                              │STOP │   │SLOW │   │ GO  │
                              └─────┘   └─────┘   └─────┘
```

> Tanda GO dapat berupa **lingkaran hijau** atau **tanda biru dengan panah putih**;
> LED yang menyala untuk GO tetap **hijau** (pin 16 / GPIO23).

## Modul & Tanggung Jawab

| Modul | Input | Output | Tanggung jawab |
|-------|-------|--------|----------------|
| `sign_recognition.py` | frame BGR (numpy) | `SignResult` | HSV mask, kontur, klasifikasi bentuk, skor confidence |
| `decision_logic.py` | `raw_sign`, `confidence` | `Decision` | konfirmasi temporal, threshold, safe-state, grace period |
| `gpio_control.py` | `sign` str | (GPIO pin) | mapping sign→LED, Jetson.GPIO / mock |
| `main.py` | CLI args | (loop) | orkestrasi pipeline, kamera, preview, logging |

## Diagram Keadaan Decision Engine

```
              ┌─────────────────────────────────────────┐
              │                                         │
              ▼                                         │
        ┌──────────┐   sign valid & conf≥thr    ┌──────────────┐
        │  IDLE /  │ ─────────────────────────► │ KANDIDAT     │
        │ LED OFF  │                            │ (count++)    │
        │          │                            └──────┬───────┘
        └────▲─────┘                                   │ count ≥ N
             │                                         ▼
             │                             ┌───────────────────────┐
             │  conf < thr / NONE         │  AKTIF (sign stabil)  │
             │  & hold time habis         │  → LED sesuai sign    │
             └─────────────────────────────  └───────────────────────┘
```

- **IDLE (LED OFF)** — kondisi awal & fallback. Semua LED mati
  (`SAFE_STATE = "NONE"`; ubah ke `"STOP"` jika ingin safe-state merah).
- **KANDIDAT** — sign terekam tapi belum stabil (counter < N frame).
- **AKTIF** — sign stabil N frame → LED mengikuti sign (STOP/SLOW/GO).
- Kembali ke IDLE jika `confidence < threshold` atau `NONE` selama `SAFE_HOLD_SECONDS`.

## Confidence Score

```
confidence = 0.30 · color_match
           + 0.60 · shape_score
           + 0.10 · size_match
```

| Komponen | Skor | Keterangan |
|----------|------|------------|
| `color_match` | 0–1 | rasio piksel warna di dalam hull ÷ 0.55 (coverage), dibatasi 1.0 |
| `shape_score` | 0.70–1.0 | keyakinan klasifikasi bentuk; bentuk **wajib** sesuai expected, jika tidak kandidat dibuang |
| `size_match` | 1.0 / 0.85 / 0.70 | area 0.6–50% / >50% / <0.6% frame |

Expected shape:
- STOP → octagon (hull fill-ratio ≈0.90, 8 vertex)
- SLOW → triangle (fill-ratio ≈0.43, 3 vertex)
- GO → circle (fill-ratio ≈1.00) atau rectangle (fill-ratio ≈0.65);
  berlaku untuk GO **hijau** maupun **biru + panah putih**

## Ekstensi ke AI / CNN

`SignResult` adalah interface stabil. Untuk mengganti dengan CNN:

```python
# contoh: ganti isi recognize() di sign_recognition.py
def recognize(frame, min_confidence=MIN_CONFIDENCE):
    blob = cv2.dnn.blobFromImage(frame, 1/255, (224,224))
    model.setInput(blob)
    preds = model.forward()
    idx = np.argmax(preds[0])
    conf = float(preds[0][idx])
    sign = CLASSES[idx] if conf >= min_confidence else "NONE"
    return SignResult(sign=sign, confidence=conf)
```

Decision logic, GPIO, dan main pipeline tidak perlu diubah.
