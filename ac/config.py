"""Configuration management for AC-Kernel NADI v2.1.0."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class ACConfig:
    """Central runtime configuration for AC-Kernel NADI v2.1.0."""

    agent_name: str = "NADI"
    persona_role: str = "Stateful Synthetic Companion"
    data_dir: str = "./nadi_state"
    tick_interval_sec: float = 1.0
    embed_dim: int = 128

    # Homeostatic setpoints (0.0 - 1.0)
    energy_setpoint: float = 0.80
    thermal_setpoint: float = 0.25
    coherence_setpoint: float = 0.75
    social_setpoint: float = 0.60

    # Memory & Dreaming thresholds
    recall_top_k: int = 5
    salience_commit_threshold: float = 0.25
    dream_replay_batch: int = 12
    dream_similarity_merge_threshold: float = 0.82

    # Expected Free Energy weights
    efe_risk_weight: float = 1.0
    efe_ambiguity_weight: float = 0.75
    efe_epistemic_weight: float = 0.85

    # HTTP Sidecar Server
    server_host: str = "127.0.0.1"
    server_port: int = 8765

    # External LLM / Adapter config
    adapter_type: str = "mock"  # mock | openai | ollama | webhook
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_sec: float = 20.0
    use_llm_appraisal: bool = False

    # Consent & Safety policy
    require_consent_for_external_actions: bool = True
    blocked_topics: list[str] = field(
        default_factory=lambda: ["self-harm", "malware-exploit", "credential-theft"]
    )

    def ensure_dirs(self) -> Path:
        root = Path(self.data_dir)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ACConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in raw.items() if k in valid_keys}
        return cls(**filtered)

    @classmethod
    def load(cls, path: str | Path) -> "ACConfig":
        target = Path(path)
        if not target.exists():
            return cls()
        data = json.loads(target.read_text(encoding="utf-8"))
        return cls.from_dict(data)
