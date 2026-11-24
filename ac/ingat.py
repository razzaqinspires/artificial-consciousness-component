"""Ingat — Tamper-Evident SHA-256 Hash-Chain Episodic & Semantic Memory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .util import (
    HybridMorphEmbedder,
    atomic_write_text,
    canonical_json,
    clamp,
    sha256_text,
    utc_now_iso,
)

GENESIS_PREV_HASH = "0" * 64


@dataclass
class MemoryBlock:
    """Single immutable record in the SHA-256 hash-chain memory ledger."""

    index: int
    timestamp: str
    kind: str  # genesis | episodic | semantic | insight | action
    content: str
    salience: float
    affect_valence: float
    tags: List[str]
    prev_hash: str
    embedding: List[float] = field(default_factory=list)
    block_hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "index": self.index,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "content": self.content,
            "salience": round(float(self.salience), 6),
            "affect_valence": round(float(self.affect_valence), 6),
            "tags": list(self.tags),
            "prev_hash": self.prev_hash,
            "embedding": [round(float(x), 6) for x in self.embedding],
        }
        return sha256_text(canonical_json(payload))

    def seal(self) -> "MemoryBlock":
        self.block_hash = self.compute_hash()
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryBlock":
        return cls(
            index=int(data["index"]),
            timestamp=str(data["timestamp"]),
            kind=str(data["kind"]),
            content=str(data["content"]),
            salience=float(data.get("salience", 0.5)),
            affect_valence=float(data.get("affect_valence", 0.0)),
            tags=list(data.get("tags") or []),
            prev_hash=str(data["prev_hash"]),
            embedding=list(data.get("embedding") or []),
            block_hash=str(data.get("block_hash", "")),
        )


class EternalMemory:
    """Append-only cryptographic hash-chain memory with hybrid semantic recall."""

    def __init__(self, ledger_path: str | Path, embed_dim: int = 128) -> None:
        self.ledger_path = Path(ledger_path)
        self.embedder = HybridMorphEmbedder(dim=embed_dim)
        self.blocks: List[MemoryBlock] = []
        self._load_or_init()

    def _load_or_init(self) -> None:
        if self.ledger_path.exists():
            raw_lines = self.ledger_path.read_text(encoding="utf-8").splitlines()
            loaded: List[MemoryBlock] = []
            for line in raw_lines:
                line = line.strip()
                if not line:
                    continue
                loaded.append(MemoryBlock.from_dict(json.loads(line)))
            if loaded:
                self.blocks = loaded
                return

        genesis = MemoryBlock(
            index=0,
            timestamp=utc_now_iso(),
            kind="genesis",
            content="AC-Kernel NADI v2.1.0 Genesis Block — Eternal Hash-Chain Initialized",
            salience=1.0,
            affect_valence=0.2,
            tags=["genesis", "nadi", "v2"],
            prev_hash=GENESIS_PREV_HASH,
            embedding=self.embedder.embed("AC-Kernel NADI v2.1.0 Genesis Block"),
        ).seal()
        self.blocks = [genesis]
        self._flush()

    def _flush(self) -> None:
        serialized = "\n".join(canonical_json(b.to_dict()) for b in self.blocks) + "\n"
        atomic_write_text(self.ledger_path, serialized)

    @property
    def head_hash(self) -> str:
        return self.blocks[-1].block_hash if self.blocks else GENESIS_PREV_HASH

    def append(
        self,
        content: str,
        kind: str = "episodic",
        salience: float = 0.5,
        affect_valence: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> MemoryBlock:
        """Append and seal a new block linked to the previous block's SHA-256 hash."""
        clean_content = content.strip()
        vec = [round(x, 6) for x in self.embedder.embed(clean_content)]
        block = MemoryBlock(
            index=len(self.blocks),
            timestamp=utc_now_iso(),
            kind=kind,
            content=clean_content,
            salience=round(clamp(salience), 6),
            affect_valence=round(clamp(affect_valence, -1.0, 1.0), 6),
            tags=list(tags or []),
            prev_hash=self.head_hash,
            embedding=vec,
        ).seal()
        self.blocks.append(block)
        self._flush()
        return block

    def verify_chain(self) -> Tuple[bool, str]:
        """Verify cryptographic integrity of every block from genesis to head."""
        if not self.blocks:
            return False, "Empty ledger: missing genesis block"

        for idx, block in enumerate(self.blocks):
            if block.index != idx:
                return False, f"Index mismatch at position {idx}: found {block.index}"
            expected_prev = GENESIS_PREV_HASH if idx == 0 else self.blocks[idx - 1].block_hash
            if block.prev_hash != expected_prev:
                return False, f"Broken prev_hash link at block #{idx}"
            recomputed = block.compute_hash()
            if block.block_hash != recomputed:
                return False, f"Tampered payload detected at block #{idx}: hash mismatch"

        return True, f"Verified {len(self.blocks)} blocks intact (head={self.head_hash[:16]}...)"

    def novelty_score(self, text: str) -> float:
        """Compute novelty in [0, 1] relative to recent memory blocks."""
        if len(self.blocks) <= 1:
            return 0.85
        q_vec = self.embedder.embed(text)
        recent = self.blocks[-25:]
        max_sim = max(
            (self.embedder.cosine_similarity(q_vec, b.embedding) for b in recent if b.kind != "genesis"),
            default=0.0,
        )
        return round(clamp(1.0 - max(0.0, max_sim)), 4)

    def recall(
        self,
        query: str,
        top_k: int = 5,
        include_kinds: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k memories ranked by hybrid semantic similarity, salience, and recency."""
        q_vec = self.embedder.embed(query)
        total = max(1, len(self.blocks))
        scored: List[Tuple[float, MemoryBlock, float]] = []

        for block in self.blocks:
            if block.kind == "genesis":
                continue
            if include_kinds and block.kind not in include_kinds:
                continue

            sim = max(0.0, self.embedder.cosine_similarity(q_vec, block.embedding))
            recency = (block.index + 1) / total
            kind_bonus = 0.08 if block.kind in ("semantic", "insight") else 0.0
            rank_score = 0.62 * sim + 0.22 * block.salience + 0.16 * recency + kind_bonus
            scored.append((rank_score, block, sim))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: List[Dict[str, Any]] = []
        for rank_score, block, sim in scored[: max(1, top_k)]:
            results.append(
                {
                    "index": block.index,
                    "timestamp": block.timestamp,
                    "kind": block.kind,
                    "content": block.content,
                    "salience": block.salience,
                    "affect_valence": block.affect_valence,
                    "tags": block.tags,
                    "similarity": round(sim, 4),
                    "score": round(rank_score, 4),
                    "block_hash": block.block_hash,
                }
            )
        return results
