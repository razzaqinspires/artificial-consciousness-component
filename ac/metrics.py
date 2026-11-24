"""Telemetry, coherence metrics, and runtime diagnostics for AC-Kernel NADI."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Sequence

from .util import clamp


@dataclass
class KernelMetrics:
    """Tracks runtime execution and synthetic consciousness indicators."""

    total_ticks: int = 0
    total_percepts: int = 0
    total_actions: int = 0
    total_sleep_cycles: int = 0
    blocked_actions: int = 0
    avg_tick_ms: float = 0.0
    last_tick_ms: float = 0.0
    integration_phi: float = 0.5
    workspace_entropy: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def record_tick(self, elapsed_ms: float) -> None:
        self.total_ticks += 1
        self.last_tick_ms = round(elapsed_ms, 4)
        if self.total_ticks == 1:
            self.avg_tick_ms = self.last_tick_ms
        else:
            alpha = 0.15
            self.avg_tick_ms = round((1.0 - alpha) * self.avg_tick_ms + alpha * self.last_tick_ms, 4)

    def update_integration(self, subsystem_signals: Sequence[float]) -> float:
        """Estimate functional integration (Phi proxy) across active subsystems."""
        vals = [clamp(v) for v in subsystem_signals]
        if len(vals) < 2:
            self.integration_phi = vals[0] if vals else 0.0
            return self.integration_phi

        mean_val = sum(vals) / len(vals)
        variance = sum((v - mean_val) ** 2 for v in vals) / len(vals)
        # High mean activation paired with balanced variance yields high integration
        coherence = 1.0 - min(1.0, math.sqrt(variance) * 1.5)
        self.integration_phi = round(clamp(mean_val * 0.6 + coherence * 0.4), 4)
        return self.integration_phi

    def update_entropy(self, weights: Sequence[float]) -> float:
        """Compute normalized Shannon entropy over workspace candidate saliences."""
        positives = [max(0.0, w) for w in weights if w > 0.0]
        total = sum(positives)
        if total <= 1e-12 or len(positives) <= 1:
            self.workspace_entropy = 0.0
            return 0.0
        probs = [p / total for p in positives]
        raw_h = -sum(p * math.log2(p) for p in probs if p > 0.0)
        max_h = math.log2(len(probs))
        self.workspace_entropy = round(clamp(raw_h / max_h if max_h > 0 else 0.0), 4)
        return self.workspace_entropy

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
