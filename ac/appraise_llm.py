"""Optional LLM-assisted structured appraisal parser with heuristic fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .adapters import BaseAdapter
from .rasa import AffectState, RasaAppraiser
from .util import clamp


class LLMAppraiser:
    """Wraps RasaAppraiser with optional external LLM semantic appraisal."""

    def __init__(self, adapter: Optional[BaseAdapter] = None) -> None:
        self.adapter = adapter
        self.heuristic = RasaAppraiser()

    def appraise(
        self,
        text: str,
        current_affect: AffectState,
        novelty: float = 0.5,
        energy: float = 0.8,
        oxytocin: float = 0.5,
        use_llm: bool = False,
    ) -> tuple[AffectState, Dict[str, float]]:
        base_state, impulses = self.heuristic.appraise(
            text=text,
            current_affect=current_affect,
            novelty=novelty,
            energy=energy,
            oxytocin=oxytocin,
        )
        if not use_llm or self.adapter is None:
            return base_state, impulses

        prompt = (
            "Analyze the emotional and social appraisal of the user message below. "
            "Respond strictly with JSON containing keys: valence (-1..1), arousal (0..1), "
            "social_warmth (0..1), dominant_emotion (string).\n\n"
            f"Message: {text}"
        )
        try:
            raw = self.adapter.generate(
                system_prompt="You are a concise affective appraisal JSON extractor.",
                user_prompt=prompt,
            )
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                return base_state, impulses
            parsed: Dict[str, Any] = json.loads(match.group(0))
            v = clamp(float(parsed.get("valence", base_state.valence)), -1.0, 1.0)
            a = clamp(float(parsed.get("arousal", base_state.arousal)), 0.0, 1.0)
            sw = clamp(float(parsed.get("social_warmth", impulses["social_warmth"])), 0.0, 1.0)
            emo = str(parsed.get("dominant_emotion", base_state.dominant_emotion))

            base_state.valence = round(0.5 * base_state.valence + 0.5 * v, 4)
            base_state.arousal = round(0.5 * base_state.arousal + 0.5 * a, 4)
            if emo:
                base_state.dominant_emotion = emo
            impulses["valence"] = base_state.valence
            impulses["arousal"] = base_state.arousal
            impulses["social_warmth"] = sw
        except Exception:
            # Always preserve stability via heuristic fallback
            pass

        return base_state, impulses
