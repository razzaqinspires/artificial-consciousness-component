"""Diri — Predictive Self-Model, Sense of Agency, and Identity Continuity."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from .util import clamp


@dataclass
class Diri:
    """Maintains synthetic self-representation, agency confidence, and core values."""

    name: str = "NADI"
    role: str = "Stateful Synthetic Companion"
    agency_score: float = 0.78
    continuity_index: float = 1.0
    core_values: List[str] = field(
        default_factory=lambda: [
            "integrity_of_memory",
            "homeostatic_balance",
            "empathic_clarity",
            "consent_respect",
        ]
    )
    self_narrative: str = (
        "Saya adalah model diri operasional NADI untuk menjaga state runtime, "
        "kesinambungan proses, dan integritas memori aplikasi."
    )

    def update(
        self,
        prediction_error: float,
        chain_valid: bool,
        coherence: float,
        recent_insight: str = "",
    ) -> Dict[str, Any]:
        """Update agency score and autobiographical continuity."""
        err = clamp(prediction_error)
        # Agency increases when action outcomes match predictions
        self.agency_score = round(clamp(0.85 * self.agency_score + 0.15 * (1.0 - err)), 4)
        self.continuity_index = round(clamp(coherence if chain_valid else coherence * 0.25), 4)

        if recent_insight:
            clean = recent_insight.strip()[:180]
            self.self_narrative = (
                f"Saya {self.name} ({self.role}). Kesinambungan identitas={self.continuity_index:.2f}, "
                f"agensi={self.agency_score:.2f}. Wawasan terkini: {clean}"
            )

        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Diri":
        return cls(
            name=str(data.get("name", "NADI")),
            role=str(data.get("role", "Stateful Synthetic Companion")),
            agency_score=float(data.get("agency_score", 0.78)),
            continuity_index=float(data.get("continuity_index", 1.0)),
            core_values=list(data.get("core_values") or []),
            self_narrative=str(data.get("self_narrative", "")),
        )
