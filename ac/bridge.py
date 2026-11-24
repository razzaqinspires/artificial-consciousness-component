"""ACBridge — High-level Router Interface connecting external bots/apps to Kernel."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .kernel import Kernel


class ACBridge:
    """Connects external platforms (WhatsApp Baileys, RPG clients, CLI) to AC-Kernel NADI."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    def build_system_prompt(self, cycle_report: Dict[str, Any]) -> str:
        """Synthesize an affective, homeostatic, and memory-grounded system prompt."""
        affect = cycle_report.get("affect", {})
        neuro = cycle_report.get("neuro", {})
        volition = cycle_report.get("volition", {})
        recalled = cycle_report.get("recalled_memories") or []
        diri = self.kernel.diri.to_dict()

        memory_lines = [
            f"- [#{m['index']} | {m['kind']} | sim={m['similarity']:.2f}] {m['content']}"
            for m in recalled[:4]
        ]
        memory_block = "\n".join(memory_lines) if memory_lines else "- (Belum ada memori asosiatif relevan)"

        return (
            f"Identity: {diri.get('self_narrative')}\n"
            f"Dominant Emotion: {affect.get('dominant_emotion', 'calm')} "
            f"(valence={affect.get('valence', 0.0):+.2f}, arousal={affect.get('arousal', 0.35):.2f}, "
            f"empathy={affect.get('empathy_resonance', 0.5):.2f})\n"
            f"Neuromodulators: DA={neuro.get('dopamine', 0.5):.2f}, "
            f"5-HT={neuro.get('serotonin', 0.5):.2f}, OXT={neuro.get('oxytocin', 0.5):.2f}\n"
            f"Active Policy: {volition.get('selected_policy', 'respond_empathetically')} "
            f"({volition.get('rationale', '')})\n"
            f"Recalled Hash-Chain Memories:\n{memory_block}\n"
            "Instruction: Respond naturally, concisely, and empathetically while honoring the active policy."
        )

    def process_turn(
        self,
        user_message: str,
        sender_id: str = "user",
        tags: Optional[List[str]] = None,
        consent_granted: bool = True,
        commit_reply: bool = True,
    ) -> Dict[str, Any]:
        """Run a full perception -> deliberation -> LLM generation -> memory commit turn."""
        merged_tags = [*(tags or []), f"sender:{sender_id}"]
        cycle = self.kernel.tick(
            stimulus=user_message,
            source=sender_id,
            tags=merged_tags,
            consent_granted=consent_granted,
        )

        if cycle.get("status") == "blocked":
            return {
                "status": "blocked",
                "reply": f"[SapaGate] Permintaan ditahan: {cycle['consent']['reason']}",
                "cycle": cycle,
            }

        volition = cycle.get("volition", {})
        if not volition.get("authorized", True):
            return {
                "status": "consent_required",
                "reply": "[SapaGate] Diperlukan persetujuan eksplisit sebelum merespons secara eksternal.",
                "cycle": cycle,
            }

        sys_prompt = self.build_system_prompt(cycle)
        reply_text = self.kernel.adapter.generate(
            system_prompt=sys_prompt,
            user_prompt=user_message,
        )

        reply_block_index: Optional[int] = None
        if commit_reply and reply_text.strip():
            block = self.kernel.memory.append(
                content=f"[Reply->{sender_id}] {reply_text.strip()}",
                kind="episodic",
                salience=0.45,
                affect_valence=float(cycle["affect"].get("valence", 0.0)),
                tags=["agent_reply", sender_id],
            )
            reply_block_index = block.index
            self.kernel.save_snapshot()

        return {
            "status": "ok",
            "reply": reply_text,
            "reply_block_index": reply_block_index,
            "system_prompt": sys_prompt,
            "cycle": cycle,
        }
