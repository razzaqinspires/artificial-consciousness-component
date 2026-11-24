"""Mimpi — NREM/REM Offline Memory Consolidation & Insight Synthesis."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from .ingat import EternalMemory, MemoryBlock
from .util import HybridMorphEmbedder, clamp, morph_stem, tokenize

_STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "untuk", "dengan", "pada",
    "adalah", "saya", "aku", "kamu", "dia", "kita", "mereka", "atau", "juga",
    "the", "and", "is", "in", "to", "of", "a", "for", "with", "on", "that", "this",
}


class Dreamer:
    """Executes offline NREM replay/pruning and REM cross-episode insight synthesis."""

    def __init__(self, embed_dim: int = 128) -> None:
        self.embedder = HybridMorphEmbedder(dim=embed_dim)

    def sleep_cycle(
        self,
        memory: EternalMemory,
        batch_size: int = 12,
        merge_threshold: float = 0.82,
    ) -> Dict[str, Any]:
        """Run a full NREM + REM consolidation pass without mutating past hash blocks."""
        episodic = [b for b in memory.blocks if b.kind == "episodic"]
        if not episodic:
            return {
                "status": "skipped",
                "reason": "No episodic memories available for consolidation",
                "nrem_replayed": 0,
                "rem_insights_created": 0,
            }

        window = episodic[-max(2, batch_size) :]

        # --- Stage 1: NREM Replay & Redundancy Clustering ---
        clusters: List[List[MemoryBlock]] = []
        for item in window:
            placed = False
            for cluster in clusters:
                sim = self.embedder.cosine_similarity(item.embedding, cluster[0].embedding)
                if sim >= merge_threshold:
                    cluster.append(item)
                    placed = True
                    break
            if not placed:
                clusters.append([item])

        # --- Stage 2: REM Associative Synthesis ---
        stem_counts: Counter[str] = Counter()
        total_valence = 0.0
        for item in window:
            total_valence += item.affect_valence
            for tok in tokenize(item.content):
                if tok not in _STOPWORDS and len(tok) > 2:
                    stem_counts[morph_stem(tok)] += 1

        top_motifs = [word for word, _ in stem_counts.most_common(5)]
        mean_valence = round(total_valence / len(window), 4)

        insights_created: List[Dict[str, Any]] = []
        # Synthesize cluster-level semantic summaries for recurring clusters
        for cluster in clusters:
            if len(cluster) >= 2:
                representative = max(cluster, key=lambda b: b.salience)
                summary = (
                    f"[NREM-Consolidated x{len(cluster)}] Tema berulang: {representative.content}"
                )
                block = memory.append(
                    content=summary,
                    kind="semantic",
                    salience=clamp(representative.salience + 0.12),
                    affect_valence=mean_valence,
                    tags=["nrem", "consolidated", *top_motifs[:2]],
                )
                insights_created.append({"index": block.index, "kind": block.kind, "content": block.content})

        # Synthesize cross-episode REM associative insight
        if top_motifs:
            motif_str = ", ".join(top_motifs)
            rem_text = (
                f"[REM-Synthesis] Pola lintas-episodik terdeteksi pada motif ({motif_str}) "
                f"dari {len(window)} episode dengan valensi rata-rata {mean_valence:+.2f}."
            )
            rem_block = memory.append(
                content=rem_text,
                kind="insight",
                salience=clamp(0.68 + 0.04 * len(top_motifs)),
                affect_valence=mean_valence,
                tags=["rem", "insight", *top_motifs[:3]],
            )
            insights_created.append({"index": rem_block.index, "kind": rem_block.kind, "content": rem_block.content})

        quality = clamp(0.55 + 0.08 * len(insights_created) + 0.02 * len(window))
        return {
            "status": "completed",
            "nrem_replayed": len(window),
            "nrem_clusters": len(clusters),
            "rem_motifs": top_motifs,
            "rem_insights_created": len(insights_created),
            "insights": insights_created,
            "sleep_quality": round(quality, 4),
        }
