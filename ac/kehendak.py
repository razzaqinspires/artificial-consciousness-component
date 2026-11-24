"""Kehendak — Active Inference & Deliberation via Expected Free Energy (EFE)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .config import ACConfig
from .util import clamp


@dataclass
class PolicyEvaluation:
    """Evaluation breakdown for a candidate behavioral policy under Expected Free Energy."""

    policy: str
    risk: float
    ambiguity: float
    epistemic_value: float
    expected_free_energy: float
    rationale: str


class Kehendak:
    """Active deliberation engine minimizing Expected Free Energy G(pi).

    G(pi) = w_risk * Risk(pi) + w_amb * Ambiguity(pi) - w_epi * EpistemicValue(pi)
    Lower G(pi) indicates a more preferred policy.
    """

    def __init__(self) -> None:
        self.last_selected_policy: str = "observe_and_stabilize"
        self.last_evaluations: List[Dict[str, Any]] = []

    def deliberate(
        self,
        config: ACConfig,
        has_external_input: bool,
        novelty: float,
        valence: float,
        drives: Dict[str, float],
        dopamine: float,
    ) -> PolicyEvaluation:
        rest_drive = drives.get("rest_drive", 0.2)
        consolidate_drive = drives.get("consolidate_drive", 0.2)
        engage_drive = drives.get("engage_drive", 0.7)

        candidates: List[tuple[str, float, float, float, str]] = []

        if has_external_input:
            # 1. Direct empathic & informative response
            risk_resp = clamp(0.20 + 0.35 * rest_drive + (0.15 if valence < -0.3 else 0.0))
            amb_resp = clamp(0.25 * (1.0 - novelty))
            epi_resp = clamp(0.45 + 0.35 * dopamine + 0.20 * engage_drive)
            candidates.append((
                "respond_empathetically",
                risk_resp,
                amb_resp,
                epi_resp,
                "Engage user directly with context-grounded empathic response",
            ))

            # 2. Clarify & probe epistemic uncertainty
            risk_clarify = clamp(0.30 + 0.25 * rest_drive)
            amb_clarify = clamp(0.15)
            epi_clarify = clamp(0.35 + 0.55 * novelty)
            candidates.append((
                "clarify_and_explore",
                risk_clarify,
                amb_clarify,
                epi_clarify,
                "Ask targeted follow-up to reduce epistemic ambiguity",
            ))

            # 3. Record silently & conserve energy
            risk_defer = clamp(0.65 - 0.45 * rest_drive)
            amb_defer = clamp(0.50)
            epi_defer = clamp(0.15)
            candidates.append((
                "encode_and_conserve",
                risk_defer,
                amb_defer,
                epi_defer,
                "Commit stimulus to memory while conserving metabolic energy",
            ))
        else:
            # Autonomous background deliberation when idle
            candidates.append((
                "observe_and_stabilize",
                clamp(0.18 + 0.20 * rest_drive),
                clamp(0.20),
                clamp(0.30 * dopamine),
                "Maintain homeostatic equilibrium and monitor environment",
            ))
            candidates.append((
                "consolidate_sleep_cycle",
                clamp(0.45 - 0.40 * max(rest_drive, consolidate_drive)),
                clamp(0.18),
                clamp(0.40 + 0.45 * consolidate_drive),
                "Trigger NREM/REM memory consolidation to reduce allostatic load",
            ))

        evaluated: List[PolicyEvaluation] = []
        for name, risk, amb, epi, rationale in candidates:
            efe = (
                config.efe_risk_weight * risk
                + config.efe_ambiguity_weight * amb
                - config.efe_epistemic_weight * epi
            )
            evaluated.append(
                PolicyEvaluation(
                    policy=name,
                    risk=round(risk, 4),
                    ambiguity=round(amb, 4),
                    epistemic_value=round(epi, 4),
                    expected_free_energy=round(efe, 4),
                    rationale=rationale,
                )
            )

        evaluated.sort(key=lambda item: item.expected_free_energy)
        chosen = evaluated[0]
        self.last_selected_policy = chosen.policy
        self.last_evaluations = [asdict(e) for e in evaluated]
        return chosen

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_policy": self.last_selected_policy,
            "evaluations": self.last_evaluations,
        }
