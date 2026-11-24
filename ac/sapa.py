"""Sapa — Consent Gate, Relational Boundary & Safety Filter."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from .config import ACConfig
from .util import tokenize


@dataclass
class ConsentDecision:
    """Result of evaluating an input or planned action against consent & safety rules."""

    allowed: bool
    reason: str
    matched_rule: str = "ok"
    requires_explicit_consent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SapaGate:
    """Enforces consent boundaries and prevents harmful or unauthorized actions."""

    def evaluate_input(self, text: str, config: ACConfig) -> ConsentDecision:
        lower = text.lower()
        tokens = set(tokenize(lower))

        for blocked in config.blocked_topics:
            key = blocked.lower().strip()
            if key and (key in lower or key.replace("-", " ") in lower):
                return ConsentDecision(
                    allowed=False,
                    reason=f"Input matched restricted safety boundary: '{blocked}'",
                    matched_rule=blocked,
                )

        if tokens & {"hapus_semua", "wipe_memory", "reset_chain"}:
            return ConsentDecision(
                allowed=False,
                reason="Destructive memory wipe requires explicit out-of-band confirmation",
                matched_rule="immutable_chain_protection",
                requires_explicit_consent=True,
            )

        return ConsentDecision(allowed=True, reason="Input passed consent and safety gate")

    def evaluate_action(
        self,
        policy: str,
        external_side_effect: bool,
        consent_granted: bool,
        config: ACConfig,
    ) -> ConsentDecision:
        if external_side_effect and config.require_consent_for_external_actions and not consent_granted:
            return ConsentDecision(
                allowed=False,
                reason=f"Policy '{policy}' triggers external side-effect without user consent",
                matched_rule="external_action_consent_required",
                requires_explicit_consent=True,
            )
        return ConsentDecision(allowed=True, reason=f"Policy '{policy}' authorized")
