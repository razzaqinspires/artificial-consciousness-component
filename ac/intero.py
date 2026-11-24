"""Interoception — Homeostasis and Allostatic Load regulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from .config import ACConfig
from .util import clamp


@dataclass
class Interoception:
    """Tracks internal physiological/computational variables and allostatic strain."""

    energy: float = 0.85
    thermal_load: float = 0.20
    memory_pressure: float = 0.15
    social_battery: float = 0.70
    allostatic_load: float = 0.15

    def update(
        self,
        config: ACConfig,
        dt: float = 1.0,
        cognitive_effort: float = 0.2,
        social_interaction: float = 0.0,
        memory_count: int = 0,
    ) -> Dict[str, float]:
        """Integrate homeostatic drift, metabolic cost, and allostatic error."""
        # Time-normalized homeostasis. The original coefficients assumed a
        # fast simulation step; a real 1 Hz heartbeat would otherwise drain
        # the virtual energy reserve and overheat within minutes. Energy now
        # relaxes toward its setpoint, with a small effort-dependent cost.
        effort = clamp(cognitive_effort)
        self.energy = clamp(
            self.energy
            + (config.energy_setpoint - self.energy) * 0.005 * dt
            - 0.00015 * effort * dt
        )

        # Thermal load relaxes slowly toward its setpoint and rises modestly
        # under work. It is a computational-load proxy, not a body temperature.
        self.thermal_load = clamp(
            self.thermal_load
            + 0.003 * effort * dt
            - 0.04 * (self.thermal_load - config.thermal_setpoint) * dt
        )

        # Memory pressure scales gently with chain size (calibrated for mobile storage)
        self.memory_pressure = clamp(min(1.0, memory_count / 2500.0))

        # Social battery shifts with interaction
        self.social_battery = clamp(
            self.social_battery
            + 0.03 * social_interaction
            - 0.005 * (self.social_battery - config.social_setpoint) * dt
        )

        # Compute homeostatic drive errors
        e_err = abs(config.energy_setpoint - self.energy)
        t_err = max(0.0, self.thermal_load - config.thermal_setpoint)
        m_err = max(0.0, self.memory_pressure - 0.65)
        instant_strain = clamp(0.45 * e_err + 0.35 * t_err + 0.20 * m_err)

        # Allostatic load accumulates chronic strain and recovers slowly when strain is low
        self.allostatic_load = clamp(
            self.allostatic_load + 0.10 * (instant_strain - self.allostatic_load) * dt
        )

        return self.drives(config)

    def drives(self, config: ACConfig) -> Dict[str, float]:
        """Return normalized homeostatic motivational drives."""
        return {
            "rest_drive": round(clamp((1.0 - self.energy) * 0.7 + self.allostatic_load * 0.3), 4),
            "cool_drive": round(clamp(max(0.0, self.thermal_load - config.thermal_setpoint) * 1.4), 4),
            "consolidate_drive": round(clamp(self.memory_pressure * 0.8 + self.allostatic_load * 0.2), 4),
            "engage_drive": round(clamp(self.energy * 0.6 + (1.0 - self.allostatic_load) * 0.4), 4),
        }

    def recover_during_sleep(self, quality: float = 0.8) -> None:
        """Restore energy and reduce allostatic load after NREM/REM sleep consolidation."""
        q = clamp(quality)
        self.energy = clamp(self.energy + 0.28 * q)
        self.thermal_load = clamp(self.thermal_load * (1.0 - 0.35 * q))
        self.allostatic_load = clamp(self.allostatic_load * (1.0 - 0.45 * q))

    def to_dict(self) -> Dict[str, Any]:
        return {k: round(v, 4) for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Interoception":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: float(v) for k, v in data.items() if k in valid})
