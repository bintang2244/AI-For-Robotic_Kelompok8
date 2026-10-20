# Contoh Gambar Sign

Letakkan gambar contoh sign di sini untuk pengujian `--image`:

- `stop.jpg` — rambu STOP (merah, segi-8)
- `slow.jpg` — rambu SLOW (kuning, segi-3)
- `go.jpg` — rambu GO (hijau, lingkaran/persegi)
- `go_biru_panah.jpg` — rambu GO biru dengan panah putih (contoh sintetis)

Contoh penggunaan:
```bash
python3 src/main.py --image assets/signs/stop.jpg
```

Anda juga bisa membuat gambar sintetis (lihat `tests/test_pipeline.py` → `_make_sign_frame`)
untuk pengujian cepat tanpa rambu fisik.
