"""Rasa — Refined OCC Cognitive Appraisal System with Empathic Regulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Tuple

from .util import clamp, tokenize

_POSITIVE_LEXICON = {
    "bagus", "hebat", "sukses", "berhasil", "senang", "terima", "kasih", "mantap",
    "aman", "stabil", "indah", "suka", "cinta", "sayang", "solusi", "lancar",
    "good", "great", "success", "happy", "thanks", "thank", "love", "awesome",
    "safe", "stable", "solved", "win", "clear", "helpful", "nice",
}
_NEGATIVE_LEXICON = {
    "gagal", "error", "rusak", "sedih", "marah", "takut", "panik", "bingung",
    "lambat", "crash", "bug", "salah", "kecewa", "capek", "lelah", "stres",
    "fail", "failed", "broken", "sad", "angry", "fear", "panic", "confused",
    "slow", "wrong", "disappointed", "tired", "stress", "hurt", "bad",
}
_URGENCY_LEXICON = {
    "segera", "darurat", "cepat", "tolong", "bantu", "kritis", "penting", "sekarang",
    "urgent", "emergency", "fast", "help", "critical", "important", "now", "asap",
}
_EMPATHIC_LEXICON = {
    "aku", "saya", "kamu", "kita", "perasaan", "maaf", "tolong", "teman", "sahabat",
    "capek", "sedih", "senang", "rindu", "khawatir", "feel", "sorry", "please",
    "friend", "worried", "tired", "care", "empathy", "together",
}


@dataclass
class AffectState:
    """Core dimensional + OCC discrete emotional state with empathic regulation."""

    valence: float = 0.15       # [-1.0, +1.0]
    arousal: float = 0.35       # [0.0, 1.0]
    dominance: float = 0.60     # [0.0, 1.0]
    empathy_resonance: float = 0.50
    dominant_emotion: str = "calm"
    occ_profile: Dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.occ_profile is None:
            self.occ_profile = {
                "joy": 0.25,
                "distress": 0.05,
                "hope": 0.30,
                "fear": 0.05,
                "gratitude": 0.20,
                "anger": 0.02,
                "curiosity": 0.35,
                "compassion": 0.30,
            }

    def decay(self, rate: float = 0.08) -> None:
        """Gradually regulate emotions back toward homeostatic baseline."""
        r = clamp(rate, 0.01, 0.5)
        self.valence = round(self.valence + r * (0.10 - self.valence), 4)
        self.arousal = round(self.arousal + r * (0.35 - self.arousal), 4)
        self.dominance = round(self.dominance + r * (0.60 - self.dominance), 4)
        for k in list(self.occ_profile.keys()):
            base = 0.25 if k in ("joy", "hope", "curiosity", "compassion") else 0.05
            self.occ_profile[k] = round(self.occ_profile[k] + r * (base - self.occ_profile[k]), 4)
        self.dominant_emotion = max(self.occ_profile.items(), key=lambda item: item[1])[0]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["valence"] = round(self.valence, 4)
        data["arousal"] = round(self.arousal, 4)
        data["dominance"] = round(self.dominance, 4)
        data["empathy_resonance"] = round(self.empathy_resonance, 4)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AffectState":
        return cls(
            valence=float(data.get("valence", 0.15)),
            arousal=float(data.get("arousal", 0.35)),
            dominance=float(data.get("dominance", 0.60)),
            empathy_resonance=float(data.get("empathy_resonance", 0.50)),
            dominant_emotion=str(data.get("dominant_emotion", "calm")),
            occ_profile=dict(data.get("occ_profile") or {}),
        )


class RasaAppraiser:
    """Evaluates stimuli along OCC appraisal dimensions with empathic regulation."""

    def appraise(
        self,
        text: str,
        current_affect: AffectState,
        novelty: float = 0.5,
        energy: float = 0.8,
        oxytocin: float = 0.5,
    ) -> Tuple[AffectState, Dict[str, float]]:
        tokens = set(tokenize(text))
        if not tokens:
            current_affect.decay(0.05)
            return current_affect, {"valence": 0.0, "arousal": 0.0, "novelty": 0.0, "social_warmth": 0.0}

        pos_hits = len(tokens & _POSITIVE_LEXICON)
        neg_hits = len(tokens & _NEGATIVE_LEXICON)
        urg_hits = len(tokens & _URGENCY_LEXICON)
        emp_hits = len(tokens & _EMPATHIC_LEXICON)
        is_question = "?" in text or bool(tokens & {"apa", "bagaimana", "kenapa", "mengapa", "what", "how", "why"})

        raw_valence = clamp((pos_hits - neg_hits) * 0.28, -1.0, 1.0)
        raw_arousal = clamp(0.25 + 0.22 * urg_hits + 0.15 * (pos_hits + neg_hits) + 0.15 * novelty, 0.0, 1.0)
        social_warmth = clamp(0.20 + 0.25 * emp_hits + 0.20 * oxytocin, 0.0, 1.0)

        # Empathic regulation: if user expresses distress, damp reactive anger and boost compassion
        empathy_gain = clamp(0.45 + 0.35 * oxytocin + 0.20 * social_warmth)
        if raw_valence < -0.15:
            regulated_anger = clamp(abs(raw_valence) * (1.0 - empathy_gain) * 0.5)
            compassion = clamp(0.35 + abs(raw_valence) * empathy_gain * 0.75)
        else:
            regulated_anger = 0.02
            compassion = clamp(0.25 + 0.35 * social_warmth)

        occ = {
            "joy": round(clamp(max(0.0, raw_valence) * 0.85 + 0.10), 4),
            "distress": round(clamp(max(0.0, -raw_valence) * 0.70), 4),
            "hope": round(clamp(0.25 + 0.40 * max(0.0, raw_valence) + 0.20 * energy), 4),
            "fear": round(clamp(0.20 * urg_hits + 0.35 * max(0.0, -raw_valence) * (1.0 - energy)), 4),
            "gratitude": round(clamp(0.45 if (tokens & {"terima", "kasih", "thanks", "thank"}) else 0.12), 4),
            "anger": round(regulated_anger, 4),
            "curiosity": round(clamp(0.25 + 0.45 * novelty + (0.25 if is_question else 0.0)), 4),
            "compassion": round(compassion, 4),
        }

        # Smooth state transition
        new_valence = round(clamp(0.55 * current_affect.valence + 0.45 * raw_valence, -1.0, 1.0), 4)
        new_arousal = round(clamp(0.50 * current_affect.arousal + 0.50 * raw_arousal, 0.0, 1.0), 4)
        new_dominance = round(clamp(0.60 * energy + 0.25 * (1.0 - occ["fear"]) + 0.15 * new_valence), 4)
        dominant = max(occ.items(), key=lambda kv: kv[1])[0]

        updated = AffectState(
            valence=new_valence,
            arousal=new_arousal,
            dominance=new_dominance,
            empathy_resonance=round(empathy_gain, 4),
            dominant_emotion=dominant,
            occ_profile=occ,
        )

        impulses = {
            "valence": raw_valence,
            "arousal": raw_arousal,
            "novelty": clamp(novelty),
            "social_warmth": social_warmth,
        }
        return updated, impulses
