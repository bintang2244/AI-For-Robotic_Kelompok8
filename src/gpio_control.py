"""
Modul kontrol LED via GPIO Jetson Nano.

Menggunakan library Jetson.GPIO (header-based). Jika dijalankan di
mesin non-Jetson (development/CI), otomatis fallback ke MockGPIO
sehingga pipeline tetap bisa diuji tanpa hardware.
"""

import time
from typing import Dict

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    LED_RED_PIN, LED_YELLOW_PIN, LED_GREEN_PIN, LED_ACTIVE_HIGH
)

# Coba import Jetson.GPIO; fallback ke mock.
# Import bisa sukses tapi board detection gagal (carrier board non-resmi),
# jadi kita verifikasi board info sebelum menganggap ini Jetson asli.
try:
    import Jetson.GPIO as GPIO
    # get_model() ada di sebagian versi; di Jetson.GPIO 2.x gunakan .model
    _board = None
    if hasattr(GPIO, "get_model"):
        _board = GPIO.get_model()
    elif hasattr(GPIO, "model"):
        _board = GPIO.model
    _IS_JETSON = str(_board).upper() not in ("NONE", "UNKNOWN", "")
except Exception:
    GPIO = None
    _IS_JETSON = False


class LEDController:
    """Kontrol 3 LED: merah (STOP), kuning (SLOW), hijau (GO)."""

    def __init__(self, red_pin=LED_RED_PIN, yellow_pin=LED_YELLOW_PIN,
                 green_pin=LED_GREEN_PIN, active_high=LED_ACTIVE_HIGH,
                 use_mock=None):
        self.pins = {"red": red_pin, "yellow": yellow_pin, "green": green_pin}
        self.active_high = active_high
        self.use_mock = (not _IS_JETSON) if use_mock is None else use_mock
        self._initialized = False

        if self.use_mock:
            print("[GPIO] Mode MOCK (bukan Jetson / --mock). LED hanya dicetak.")
        else:
            try:
                GPIO.setmode(GPIO.BOARD)
                for p in self.pins.values():
                    GPIO.setup(p, GPIO.OUT)
                    GPIO.output(p, GPIO.LOW if active_high else GPIO.HIGH)
                self._initialized = True
                print(f"[GPIO] Inisialisasi Jetson GPIO: red={red_pin}, yellow={yellow_pin}, green={green_pin}")
            except Exception as e:
                # Board tidak cocok / akses gagal → fallback mock agar pipeline tetap jalan
                print(f"[GPIO] Gagal inisialisasi GPIO ({e}). Fallback ke MOCK.")
                self.use_mock = True

    def set_leds(self, red=False, yellow=False, green=False):
        """Set status ketiga LED sekaligus."""
        states = {"red": red, "yellow": yellow, "green": green}
        if self.use_mock:
            line = " | ".join(f"{k.upper()}={'ON ' if v else 'OFF'}" for k, v in states.items())
            print(f"[LED] {line}")
        else:
            for name, on in states.items():
                level = GPIO.HIGH if (on == self.active_high) else GPIO.LOW
                GPIO.output(self.pins[name], level)
        self._last = states

    def apply_decision(self, sign: str):
        """Map sign → LED yang menyala. Hanya satu LED nyala pada satu waktu."""
        self.set_leds(
            red=(sign == "STOP"),
            yellow=(sign == "SLOW"),
            green=(sign == "GO"),
        )

    def all_off(self):
        self.set_leds(False, False, False)

    @property
    def last_states(self) -> Dict[str, bool]:
        return getattr(self, "_last", {"red": False, "yellow": False, "green": False})

    def cleanup(self):
        if self._initialized and GPIO:
            self.all_off()
            GPIO.cleanup()
            print("[GPIO] Cleanup selesai.")
