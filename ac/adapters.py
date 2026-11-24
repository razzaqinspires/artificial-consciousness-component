"""Service Adapters for external AI providers using pure Python stdlib."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .config import ACConfig


class BaseAdapter(ABC):
    """Abstract interface for LLM / inference backends."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a text completion given system and user prompts."""


class EchoMockAdapter(BaseAdapter):
    """Offline deterministic adapter for zero-network mobile operation and testing."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        emotion_hint = "calm"
        for line in system_prompt.splitlines():
            if "Dominant Emotion:" in line:
                emotion_hint = line.split("Dominant Emotion:", 1)[1].strip()
                break
        return (
            f"[NADI-Internal | state={emotion_hint}] Stimulus diterima dan diselaraskan: "
            f"{user_prompt.strip()}"
        )


class OpenAICompatibleAdapter(BaseAdapter):
    """Adapter for OpenAI-compatible Chat Completions endpoints via urllib."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_sec: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.65,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return str(body["choices"][0]["message"]["content"]).strip()


class OllamaAdapter(BaseAdapter):
    """Adapter for local/LAN Ollama instances via /api/chat."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2",
        timeout_sec: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return str(body.get("message", {}).get("content", "")).strip()


class WebhookAdapter(BaseAdapter):
    """Generic JSON POST webhook adapter for custom agent routers."""

    def __init__(self, endpoint_url: str, timeout_sec: float = 20.0, extra_headers: Optional[Dict[str, str]] = None) -> None:
        self.endpoint_url = endpoint_url
        self.timeout_sec = timeout_sec
        self.extra_headers = dict(extra_headers or {})

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        payload: Dict[str, Any] = {"system_prompt": system_prompt, "user_prompt": user_prompt}
        req = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
        try:
            data = json.loads(raw)
            return str(data.get("reply") or data.get("content") or raw).strip()
        except json.JSONDecodeError:
            return raw.strip()


def build_adapter(config: ACConfig) -> BaseAdapter:
    """Factory creating the configured inference adapter."""
    kind = config.adapter_type.lower().strip()
    if kind == "openai" and config.llm_api_key:
        return OpenAICompatibleAdapter(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            model=config.llm_model,
            timeout_sec=config.llm_timeout_sec,
        )
    if kind == "ollama":
        return OllamaAdapter(
            base_url=config.llm_base_url,
            model=config.llm_model,
            timeout_sec=config.llm_timeout_sec,
        )
    if kind == "webhook" and config.llm_base_url:
        return WebhookAdapter(
            endpoint_url=config.llm_base_url,
            timeout_sec=config.llm_timeout_sec,
        )
    return EchoMockAdapter()
