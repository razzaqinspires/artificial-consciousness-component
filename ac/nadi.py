"""Nadi — Autonomic rhythmic pulse and phase oscillator."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict

from .util import clamp


@dataclass
class Nadi:
    """Autonomic heartbeat and phase rhythm governing tick cadence and arousal."""

    bpm: float = 68.0
    phase: float = 0.0
    coherence: float = 0.85
    beat_count: int = 0

    def beat(self, dt: float = 1.0, arousal: float = 0.4, stress: float = 0.2) -> Dict[str, float]:
        """Advance the autonomic pulse oscillator by dt seconds."""
        target_bpm = clamp(60.0 + 45.0 * arousal + 30.0 * stress, 48.0, 165.0)
        self.bpm = round(self.bpm + 0.2 * (target_bpm - self.bpm), 2)

        freq_hz = self.bpm / 60.0
        self.phase = (self.phase + 2.0 * math.pi * freq_hz * dt) % (2.0 * math.pi)
        self.beat_count += 1

        # Sinusoidal pulse wave in [0, 1]
        pulse_wave = 0.5 * (1.0 + math.sin(self.phase))
        self.coherence = round(clamp(0.92 - 0.35 * stress + 0.05 * pulse_wave), 4)

        return {
            "bpm": self.bpm,
            "phase": round(self.phase, 4),
            "pulse_wave": round(pulse_wave, 4),
            "coherence": self.coherence,
            "beat_count": self.beat_count,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Nadi":
        return cls(
            bpm=float(data.get("bpm", 68.0)),
            phase=float(data.get("phase", 0.0)),
            coherence=float(data.get("coherence", 0.85)),
            beat_count=int(data.get("beat_count", 0)),
        )
