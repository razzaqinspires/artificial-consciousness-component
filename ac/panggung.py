"""Panggung — Global Workspace Theory (GWT) & Attention Schema (AST)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .util import clamp, utc_now_iso


@dataclass
class WorkspaceItem:
    """Candidate coalitional representation competing for conscious broadcast."""

    source: str
    content: str
    salience: float
    urgency: float = 0.3
    emotional_weight: float = 0.2
    timestamp: str = field(default_factory=utc_now_iso)

    def score(self, attention_precision: float = 0.6) -> float:
        w = (
            0.45 * clamp(self.salience)
            + 0.30 * clamp(self.urgency)
            + 0.25 * clamp(self.emotional_weight)
        )
        return round(clamp(w * (0.75 + 0.5 * clamp(attention_precision))), 4)


@dataclass
class AttentionSchema:
    """Internal model of what the system is currently attending to and why."""

    current_focus: str = "idle_monitoring"
    focus_source: str = "autonomic"
    focus_strength: float = 0.4
    stability_ticks: int = 0
    reason: str = "Baseline homeostatic monitoring"


class Panggung:
    """Global Workspace where sensory, memory, and interoceptive signals compete."""

    def __init__(self) -> None:
        self.candidates: List[WorkspaceItem] = []
        self.broadcast_history: List[Dict[str, Any]] = []
        self.schema = AttentionSchema()

    def submit(self, item: WorkspaceItem) -> None:
        self.candidates.append(item)

    def compete_and_broadcast(self, attention_precision: float = 0.6) -> Optional[Dict[str, Any]]:
        """Select highest-salience coalition, update Attention Schema, and broadcast."""
        if not self.candidates:
            self.schema.stability_ticks += 1
            return None

        ranked = sorted(
            self.candidates,
            key=lambda c: c.score(attention_precision),
            reverse=True,
        )
        winner = ranked[0]
        win_score = winner.score(attention_precision)

        if self.schema.focus_source == winner.source and self.schema.current_focus == winner.content[:80]:
            self.schema.stability_ticks += 1
        else:
            self.schema.stability_ticks = 1

        self.schema.current_focus = winner.content[:80]
        self.schema.focus_source = winner.source
        self.schema.focus_strength = win_score
        self.schema.reason = (
            f"Selected '{winner.source}' coalition (score={win_score:.2f}, "
            f"precision={attention_precision:.2f})"
        )

        packet = {
            "timestamp": utc_now_iso(),
            "source": winner.source,
            "content": winner.content,
            "broadcast_score": win_score,
            "competing_count": len(ranked),
            "attention_schema": asdict(self.schema),
        }
        self.broadcast_history.append(packet)
        if len(self.broadcast_history) > 32:
            self.broadcast_history = self.broadcast_history[-32:]

        # Clear transient workspace buffer after ignition
        self.candidates.clear()
        return packet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attention_schema": asdict(self.schema),
            "recent_broadcasts": self.broadcast_history[-5:],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Panggung":
        obj = cls()
        schema_raw = data.get("attention_schema") or {}
        if schema_raw:
            obj.schema = AttentionSchema(
                current_focus=str(schema_raw.get("current_focus", "idle_monitoring")),
                focus_source=str(schema_raw.get("focus_source", "autonomic")),
                focus_strength=float(schema_raw.get("focus_strength", 0.4)),
                stability_ticks=int(schema_raw.get("stability_ticks", 0)),
                reason=str(schema_raw.get("reason", "Baseline homeostatic monitoring")),
            )
        obj.broadcast_history = list(data.get("recent_broadcasts") or [])
        return obj
