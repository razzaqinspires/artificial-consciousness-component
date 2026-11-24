"""Utility functions and Hybrid Lexical-Morphological Embedder (pure Python)."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Sequence

# Lightweight Indonesian + English morphological prefixes & suffixes
_ID_PREFIXES = (
    "meng", "meny", "mem", "men", "me",
    "peng", "peny", "pem", "pen", "pe",
    "ber", "ter", "per", "di", "ke", "se",
)
_ID_SUFFIXES = ("kannya", "lah", "kah", "pun", "nya", "kan", "an", "i")
_EN_SUFFIXES = ("ingly", "edly", "ation", "ments", "ness", "ing", "ed", "ly", "es", "s")


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def monotonic_ms() -> float:
    """Return monotonic clock in milliseconds."""
    return time.perf_counter() * 1000.0


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp float value into [low, high]."""
    return max(low, min(high, float(value)))


def canonical_json(obj: Any) -> str:
    """Serialize any JSON-compatible object deterministically for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    """Compute hex SHA-256 digest of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: str | Path, content: str) -> None:
    """Write text atomically to prevent state corruption on mobile interruptions."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def tokenize(text: str) -> List[str]:
    """Extract lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9_]+", text.lower())


def morph_stem(token: str) -> str:
    """Apply lightweight bilingual (ID/EN) morphological stemming."""
    w = token.lower().strip()
    if len(w) <= 3:
        return w

    # Indonesian affixes
    for suf in _ID_SUFFIXES:
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    for pref in _ID_PREFIXES:
        if len(w) > len(pref) + 3 and w.startswith(pref):
            w = w[len(pref) :]
            break

    # English suffixes
    for suf in _EN_SUFFIXES:
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)]
            break

    return w


def char_ngrams(token: str, n: int = 3) -> List[str]:
    """Generate boundary-padded character n-grams for subword resilience."""
    padded = f"<{token}>"
    if len(padded) <= n:
        return [padded]
    return [padded[i : i + n] for i in range(len(padded) - n + 1)]


class HybridMorphEmbedder:
    """Zero-dependency Hybrid Lexical-Morphological Feature Hashing Embedder.

    Combines exact surface tokens, bilingual morphological stems, and character
    trigrams into an L2-normalized dense vector for fast mobile semantic recall.
    """

    def __init__(self, dim: int = 128) -> None:
        self.dim = max(32, int(dim))

    def _project(self, feature: str, weight: float, vec: List[float]) -> None:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        raw_int = int.from_bytes(digest, "big", signed=False)
        idx = raw_int % self.dim
        sign = 1.0 if ((raw_int >> 63) & 1) == 0 else -1.0
        vec[idx] += sign * weight

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        tokens = tokenize(text)
        if not tokens:
            return vec

        for tok in tokens:
            # 1. Exact lexical feature
            self._project(f"lex:{tok}", 1.0, vec)
            # 2. Morphological root feature
            stem = morph_stem(tok)
            self._project(f"stem:{stem}", 1.25, vec)
            # 3. Subword morphological n-grams
            for ng in char_ngrams(stem, 3):
                self._project(f"ng:{ng}", 0.35, vec)

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-12:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na <= 1e-12 or nb <= 1e-12:
            return 0.0
        return clamp(dot / (na * nb), -1.0, 1.0)
