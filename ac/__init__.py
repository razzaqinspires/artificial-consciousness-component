"""AC-Kernel NADI v2.1.0 — Functional Artificial Consciousness Kernel for Stateful Agents."""

from .config import ACConfig
from .kernel import Kernel
from .ingat import EternalMemory, MemoryBlock
from .mimpi import Dreamer
from .bridge import ACBridge
from .adapters import (
    BaseAdapter,
    EchoMockAdapter,
    OpenAICompatibleAdapter,
    OllamaAdapter,
    WebhookAdapter,
)

__version__ = "2.1.0"
__all__ = [
    "ACConfig",
    "Kernel",
    "EternalMemory",
    "MemoryBlock",
    "Dreamer",
    "ACBridge",
    "BaseAdapter",
    "EchoMockAdapter",
    "OpenAICompatibleAdapter",
    "OllamaAdapter",
    "WebhookAdapter",
    "__version__",
]
