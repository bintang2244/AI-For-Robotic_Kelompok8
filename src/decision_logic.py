"""
Decision Logic: mengubah hasil pengenalan sign menjadi keputusan LED.

Aturan:
- sign valid & confidence >= threshold → LED sesuai sign
- tidak ada sign / confidence < threshold → SAFE_STATE
  (default "NONE" = semua LED mati; bisa diubah ke "STOP")
- konfirmasi temporal: sign harus muncul N frame berturut agar diterima
  (menghilangkan flicker/false positive sesaat)
"""

import time
from dataclasses import dataclass
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MIN_CONFIDENCE, SAFE_STATE, SAFE_HOLD_SECONDS


@dataclass
class Decision:
    sign: str           # keputusan akhir yang dipakai
    confidence: float
    is_safe: bool       # True jika dalam mode aman
    raw_sign: str       # sign apa adanya dari recognizer
    reason: str


class DecisionEngine:
    def __init__(self, min_confidence=MIN_CONFIDENCE,
                 stable_frames=3, safe_state=SAFE_STATE,
                 safe_hold_seconds=SAFE_HOLD_SECONDS):
        self.min_confidence = min_confidence
        self.stable_frames = stable_frames
        self.safe_state = safe_state
        self.safe_hold_seconds = safe_hold_seconds

        self._candidate: Optional[str] = None
        self._candidate_count: int = 0
        self._current_sign: str = safe_state
        self._is_safe: bool = True
        self._last_valid_time: float = 0.0

    def update(self, raw_sign: str, confidence: float) -> Decision:
        now = time.time()

        # Kandidat cukup kuat
        if raw_sign != "NONE" and confidence >= self.min_confidence:
            if raw_sign == self._candidate:
                self._candidate_count += 1
            else:
                self._candidate = raw_sign
                self._candidate_count = 1

            # Perlu N frame berturut untuk ganti keputusan
            if self._candidate_count >= self.stable_frames:
                if self._current_sign != raw_sign:
                    self._current_sign = raw_sign
                    print(f"[DECISION] Sign stabil → {raw_sign} (conf={confidence:.2f})")
                self._is_safe = False
                self._last_valid_time = now
                return Decision(
                    sign=raw_sign, confidence=confidence, is_safe=False,
                    raw_sign=raw_sign,
                    reason=f"Sign terdeteksi stabil ({self._candidate_count} frame)",
                )
            # Belum stabil → pertahankan keputusan lama
            return Decision(
                sign=self._current_sign, confidence=confidence, is_safe=self._is_safe,
                raw_sign=raw_sign,
                reason=f"Kandidat {raw_sign} ({self._candidate_count}/{self.stable_frames})",
            )

        # Tidak ada sign valid → masuk / tetap di safe state
        self._candidate = None
        self._candidate_count = 0
        time_since_valid = now - self._last_valid_time if self._last_valid_time else 999

        if self._last_valid_time == 0.0 or time_since_valid >= self.safe_hold_seconds:
            # Langsung safe jika belum pernah deteksi atau sudah lama
            if self._current_sign != self.safe_state or not self._is_safe:
                self._current_sign = self.safe_state
                self._is_safe = True
                if self.safe_state == "NONE":
                    print(f"[DECISION] Tidak ada sign → semua LED OFF (conf={confidence:.2f})")
                else:
                    print(f"[DECISION] → SAFE STATE ({self.safe_state}), conf={confidence:.2f}")
        else:
            # Dalam grace period: tahan sign terakhir
            pass

        return Decision(
            sign=self._current_sign, confidence=confidence, is_safe=self._is_safe,
            raw_sign=raw_sign,
            reason="Tidak ada sign valid → safe state" if self._is_safe
                   else f"Tahan sign terakhir ({self.safe_hold_seconds - time_since_valid:.1f}s lagi)",
        )
