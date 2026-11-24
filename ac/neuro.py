"""Neuromodulatory field dynamics for AC-Kernel NADI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from .util import clamp


@dataclass
class NeuroField:
    """Continuous neuromodulator concentrations regulating global cognitive tone."""

    dopamine: float = 0.55       # Reward prediction, curiosity, exploratory drive
    serotonin: float = 0.60      # Mood stability, impulse inhibition, calm
    norepinephrine: float = 0.40 # Alertness, vigilance, arousal gain
    acetylcholine: float = 0.55  # Attentional precision, memory encoding rate
    cortisol: float = 0.25       # Stress response, allostatic strain
    oxytocin: float = 0.50       # Social bonding, empathic resonance

    def step(self, dt: float = 1.0, arousal: float = 0.4, stress: float = 0.2) -> None:
        """Relax neuromodulators toward baseline setpoints and apply couplings."""
        rate = clamp(0.08 * dt, 0.01, 0.5)

        target_da = clamp(0.55 + 0.15 * (arousal - 0.4) - 0.20 * stress)
        target_5ht = clamp(0.62 - 0.25 * stress + 0.10 * self.oxytocin)
        target_ne = clamp(0.35 + 0.45 * arousal + 0.20 * stress)
        target_ach = clamp(0.50 + 0.30 * arousal - 0.15 * stress)
        target_cort = clamp(0.20 + 0.65 * stress - 0.15 * self.serotonin)
        target_oxy = clamp(0.50 - 0.20 * stress)

        self.dopamine = clamp(self.dopamine + rate * (target_da - self.dopamine))
        self.serotonin = clamp(self.serotonin + rate * (target_5ht - self.serotonin))
        self.norepinephrine = clamp(self.norepinephrine + rate * (target_ne - self.norepinephrine))
        self.acetylcholine = clamp(self.acetylcholine + rate * (target_ach - self.acetylcholine))
        self.cortisol = clamp(self.cortisol + rate * (target_cort - self.cortisol))
        self.oxytocin = clamp(self.oxytocin + rate * (target_oxy - self.oxytocin))

    def apply_appraisal_impulse(
        self,
        valence: float,
        arousal: float,
        novelty: float,
        social_warmth: float,
    ) -> None:
        """Modulate neuromodulators directly from cognitive/empathic appraisal."""
        self.dopamine = clamp(self.dopamine + 0.18 * valence + 0.14 * novelty)
        self.serotonin = clamp(self.serotonin + 0.15 * valence - 0.10 * max(0.0, -valence))
        self.norepinephrine = clamp(self.norepinephrine + 0.22 * arousal)
        self.acetylcholine = clamp(self.acetylcholine + 0.20 * novelty)
        if valence < 0:
            self.cortisol = clamp(self.cortisol + 0.22 * abs(valence))
        else:
            self.cortisol = clamp(self.cortisol - 0.08 * valence)
        self.oxytocin = clamp(self.oxytocin + 0.20 * social_warmth)

    def plasticity_gain(self) -> float:
        """Compute memory encoding gain driven by Acetylcholine, Dopamine, and Norepinephrine."""
        return round(
            clamp(0.4 * self.acetylcholine + 0.35 * self.dopamine + 0.25 * self.norepinephrine),
            4,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {k: round(v, 4) for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NeuroField":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: float(v) for k, v in data.items() if k in valid})
