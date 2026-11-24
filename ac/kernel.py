"""NADI Kernel 2.1.0 — persistent functional-state orchestrator."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapters import BaseAdapter, build_adapter
from .appraise_llm import LLMAppraiser
from .config import ACConfig
from .diri import Diri
from .ingat import EternalMemory
from .intero import Interoception
from .kehendak import Kehendak
from .metrics import KernelMetrics
from .mimpi import Dreamer
from .nadi import Nadi
from .neuro import NeuroField
from .panggung import Panggung, WorkspaceItem
from .rasa import AffectState
from .sapa import SapaGate
from .util import atomic_write_text, clamp, monotonic_ms, utc_now_iso


NADI_KERNEL_VERSION = "2.1.0"


class Kernel:
    """Integrates NADI subsystems with durable, private memory scopes and a managed heartbeat.

    One Kernel instance represents one operational identity. Shared affective/state telemetry is
    global to that identity, while conversation memories supplied with ``memory_scope`` are
    stored in separate hash-named ledgers.
    """

    def __init__(self, config: Optional[ACConfig] = None, adapter: Optional[BaseAdapter] = None) -> None:
        self.config = config or ACConfig()
        self.state_dir = self.config.ensure_dirs()
        self._lock = threading.RLock()
        self._process_lock_handle = None
        self._acquire_process_lock()

        self.snapshot_path = self.state_dir / "kernel_state.json"
        self.ledger_path = self.state_dir / "eternal_chain.jsonl"
        self.private_memory_dir = self.state_dir / "private"
        self.private_memory_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.private_memory_dir, 0o700)
        except OSError:
            pass
        self._scope_salt_path = self.state_dir / ".scope-salt"
        try:
            self._scope_salt = self._load_scope_salt()
        except Exception:
            self._release_process_lock()
            raise
        self._scope_memories: "OrderedDict[str, EternalMemory]" = OrderedDict()
        try:
            cache_limit = int(os.getenv("NADI_SCOPE_CACHE_LIMIT", "128"))
        except (TypeError, ValueError):
            cache_limit = 128
        self._scope_cache_limit = max(8, min(512, cache_limit))

        self._heartbeat_lock = threading.RLock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_state: Dict[str, Any] = {
            "running": False, "interval_sec": max(0.25, min(60.0, float(self.config.tick_interval_sec))),
            "ticks": 0, "started_at": None, "last_beat_at": None, "last_error": None,
        }

        try:
            self.adapter = adapter or build_adapter(self.config)
            self.memory = EternalMemory(self.ledger_path, embed_dim=self.config.embed_dim)
        except Exception:
            self._release_process_lock()
            raise
        self.dreamer = Dreamer(embed_dim=self.config.embed_dim)
        self.appraiser = LLMAppraiser(adapter=self.adapter)
        self.gate = SapaGate()
        self.volition = Kehendak()

        self.nadi = Nadi()
        self.intero = Interoception()
        self.neuro = NeuroField()
        self.affect = AffectState()
        self.workspace = Panggung()
        self.diri = Diri(name=self.config.agent_name, role=self.config.persona_role)
        self.metrics = KernelMetrics()

        try:
            self._load_snapshot()
            chain_ok, chain_detail = self.memory.verify_chain()
            if not chain_ok:
                raise RuntimeError(f"NADI global memory integrity check failed: {chain_detail}")
        except Exception:
            self._release_process_lock()
            raise

    def _acquire_process_lock(self) -> None:
        """Prevent concurrent writers from opening the same NADI state directory."""
        lock_path = self.state_dir / ".nadi-runtime.lock"
        handle = open(lock_path, "a+", encoding="utf-8")
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        try:
            try:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:
                import msvcrt
                handle.seek(0)
                if not handle.read(1):
                    handle.seek(0)
                    handle.write(" ")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({"pid": os.getpid(), "started_at": utc_now_iso()}))
            handle.flush()
            os.fsync(handle.fileno())
            self._process_lock_handle = handle
        except (BlockingIOError, OSError) as exc:
            handle.close()
            raise RuntimeError(
                "Another NADI process is already using this state directory. "
                "Use one sidecar instance per data_dir. If the previous process crashed, "
                "the operating system will release its lock automatically."
            ) from exc

    def _release_process_lock(self) -> None:
        handle = getattr(self, "_process_lock_handle", None)
        if handle is None:
            return
        try:
            try:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            handle.close()
        finally:
            self._process_lock_handle = None

    def close(self) -> None:
        """Stop managed background work and release this process' exclusive state lock."""
        thread = self._heartbeat_thread
        if thread and thread.is_alive():
            self.stop_heartbeat()
        self._release_process_lock()

    def _load_scope_salt(self) -> bytes:
        """Load or create the stable secret used to pseudonymize private memory scopes."""
        if self._scope_salt_path.exists():
            raw = self._scope_salt_path.read_bytes()
            if len(raw) != 32:
                raise RuntimeError("NADI scope salt is malformed; preserve it and restore a valid backup")
            try:
                os.chmod(self._scope_salt_path, 0o600)
            except OSError:
                pass
            return raw
        raw = secrets.token_bytes(32)
        fd = os.open(self._scope_salt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        return raw

    def _scope_fingerprint(self, scope: str) -> str:
        clean = str(scope or "").strip()
        if not clean or len(clean) > 512:
            raise ValueError("memory_scope must be a non-empty identifier of at most 512 characters")
        return hashlib.sha256(self._scope_salt + clean.encode("utf-8")).hexdigest()

    def _memory_for_scope(self, scope: Optional[str]) -> EternalMemory:
        if scope is None:
            return self.memory
        fingerprint = self._scope_fingerprint(scope)
        cached = self._scope_memories.pop(fingerprint, None)
        if cached is not None:
            self._scope_memories[fingerprint] = cached
            return cached
        ledger = self.private_memory_dir / fingerprint / "eternal_chain.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(ledger.parent, 0o700)
        except OSError:
            pass
        memory = EternalMemory(ledger, embed_dim=self.config.embed_dim)
        valid, detail = memory.verify_chain()
        if not valid:
            raise RuntimeError(f"Private memory integrity check failed ({fingerprint[:12]}): {detail}")
        self._scope_memories[fingerprint] = memory
        while len(self._scope_memories) > self._scope_cache_limit:
            self._scope_memories.popitem(last=False)
        return memory

    def remember_scoped(
        self, scope: str, content: str, *, kind: str = "episodic",
        salience: float = 0.45, affect_valence: float = 0.0, tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Append a private memory record without exposing the raw scope identifier in paths/tags."""
        clean = str(content or "").strip()
        if not clean:
            raise ValueError("content must not be empty")
        if len(clean) > 20_000:
            raise ValueError("content exceeds 20,000 characters")
        allowed_kinds = {"episodic", "semantic", "insight", "action"}
        if kind not in allowed_kinds:
            raise ValueError(f"kind must be one of: {', '.join(sorted(allowed_kinds))}")
        with self._lock:
            memory = self._memory_for_scope(scope)
            block = memory.append(
                content=clean, kind=kind, salience=salience,
                affect_valence=affect_valence, tags=list(tags or [])[:32],
            )
            self.save_snapshot()
            return {"index": block.index, "block_hash": block.block_hash, "chain_valid": memory.verify_chain()[0]}

    def record_scoped_digest(self, scope: str, event: str, content: str) -> Dict[str, Any]:
        """Record an opaque event digest; raw user/assistant text remains in the host User Vault."""
        import hmac as _hmac

        clean_event = str(event or "event").strip()[:48] or "event"
        raw = str(content or "")
        digest = _hmac.new(
            self._scope_salt,
            (self._scope_fingerprint(scope) + "\0" + raw).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        marker = f"opaque_event:{clean_event}:hmac_sha256={digest}:chars={len(raw)}"
        return self.remember_scoped(
            scope, marker, kind="action", salience=0.20, affect_valence=0.0,
            tags=["opaque_event", clean_event],
        )

    def recall_scoped(self, scope: str, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        clean = str(query or "").strip()
        if not clean:
            return []
        with self._lock:
            memory = self._memory_for_scope(scope)
            return memory.recall(clean, top_k=max(1, min(20, int(top_k or self.config.recall_top_k))))

    def _load_snapshot(self) -> None:
        if not self.snapshot_path.exists():
            self.save_snapshot()
            return
        try:
            data = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            if "nadi" in data:
                self.nadi = Nadi.from_dict(data["nadi"])
            if "intero" in data:
                self.intero = Interoception.from_dict(data["intero"])
            if "neuro" in data:
                self.neuro = NeuroField.from_dict(data["neuro"])
            if "affect" in data:
                self.affect = AffectState.from_dict(data["affect"])
            if "workspace" in data:
                self.workspace = Panggung.from_dict(data["workspace"])
            if "diri" in data:
                self.diri = Diri.from_dict(data["diri"])
            if "metrics" in data:
                m = data["metrics"]
                self.metrics.total_ticks = int(m.get("total_ticks", 0))
                self.metrics.total_percepts = int(m.get("total_percepts", 0))
                self.metrics.total_actions = int(m.get("total_actions", 0))
                self.metrics.total_sleep_cycles = int(m.get("total_sleep_cycles", 0))
                self.metrics.blocked_actions = int(m.get("blocked_actions", 0))
                self.metrics.avg_tick_ms = float(m.get("avg_tick_ms", 0.0))
                self.metrics.integration_phi = float(m.get("integration_phi", 0.5))
        except Exception as exc:
            # Never silently overwrite a damaged snapshot: preserve it for forensic recovery.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            quarantine = self.snapshot_path.with_name(f"kernel_state.corrupt.{stamp}.json")
            try:
                os.replace(self.snapshot_path, quarantine)
            except OSError:
                pass
            raise RuntimeError(
                f"NADI snapshot is corrupt and was preserved at {quarantine.name}; "
                "restore a backup before restarting to avoid silent state loss"
            ) from exc

    def save_snapshot(self) -> Path:
        with self._lock:
            payload = {
                "updated_at": utc_now_iso(),
                "agent_name": self.config.agent_name,
                "kernel_version": NADI_KERNEL_VERSION,
                "nadi": self.nadi.to_dict(),
                "intero": self.intero.to_dict(),
                "neuro": self.neuro.to_dict(),
                "affect": self.affect.to_dict(),
                "workspace": self.workspace.to_dict(),
                "diri": self.diri.to_dict(),
                "metrics": self.metrics.to_dict(),
                "chain_head": self.memory.head_hash,
                "chain_length": len(self.memory.blocks),
            }
            atomic_write_text(
                self.snapshot_path,
                json.dumps(payload, indent=2, ensure_ascii=False),
            )
            return self.snapshot_path

    def tick(
        self,
        stimulus: Optional[str] = None,
        source: str = "user",
        tags: Optional[List[str]] = None,
        consent_granted: bool = True,
        dt: Optional[float] = None,
        memory_scope: Optional[str] = None,
        allow_auto_sleep: bool = True,
        persist_stimulus: bool = True,
        persist_snapshot: bool = True,
        allow_llm_appraisal: bool = True,
    ) -> Dict[str, Any]:
        """Advance the entire functional consciousness loop by one cognitive cycle."""
        with self._lock:
            t0 = monotonic_ms()
            step_dt = dt if dt is not None else self.config.tick_interval_sec
            has_input = bool(stimulus and stimulus.strip())
            active_memory = self._memory_for_scope(memory_scope) if memory_scope is not None else self.memory

            # 1. Consent & Safety Gate on incoming stimulus
            if has_input:
                in_decision = self.gate.evaluate_input(stimulus or "", self.config)
                if not in_decision.allowed:
                    self.metrics.blocked_actions += 1
                    elapsed = monotonic_ms() - t0
                    self.metrics.record_tick(elapsed)
                    if persist_snapshot:
                        self.save_snapshot()
                    return {
                        "status": "blocked",
                        "consent": in_decision.to_dict(),
                        "state": self.status(),
                    }

            # 2. Autonomic Nadi Beat & Interoceptive Homeostasis
            pulse = self.nadi.beat(
                dt=step_dt,
                arousal=self.affect.arousal,
                stress=self.intero.allostatic_load,
            )
            drives = self.intero.update(
                config=self.config,
                dt=step_dt,
                cognitive_effort=0.65 if has_input else 0.15,
                social_interaction=0.8 if (has_input and source == "user") else 0.0,
                memory_count=len(self.memory.blocks),
            )

            # 3. Novelty, OCC Appraisal & Neuromodulation
            novelty = 0.15
            recalled: List[Dict[str, Any]] = []
            committed_block_index: Optional[int] = None

            if has_input:
                clean_text = (stimulus or "").strip()
                self.metrics.total_percepts += 1
                novelty = active_memory.novelty_score(clean_text)

                self.affect, impulses = self.appraiser.appraise(
                    text=clean_text,
                    current_affect=self.affect,
                    novelty=novelty,
                    energy=self.intero.energy,
                    oxytocin=self.neuro.oxytocin,
                    use_llm=self.config.use_llm_appraisal and allow_llm_appraisal,
                )
                self.neuro.apply_appraisal_impulse(
                    valence=impulses["valence"],
                    arousal=impulses["arousal"],
                    novelty=impulses["novelty"],
                    social_warmth=impulses["social_warmth"],
                )

                # Retrieve associative context from EternalMemory
                recalled = active_memory.recall(clean_text, top_k=self.config.recall_top_k)

                # Submit external percept to Global Workspace
                salience = clamp(
                    0.35
                    + 0.30 * novelty
                    + 0.20 * abs(self.affect.valence)
                    + 0.15 * self.neuro.plasticity_gain()
                )
                # The global workspace is shared by the single NADI identity. Never place raw
                # private user text here: scoped text belongs only in that user's private ledger.
                workspace_source = "private_input" if memory_scope is not None else source
                workspace_content = (
                    f"Private interaction received ({len(clean_text)} characters); "
                    "content retained only in the isolated memory scope."
                    if memory_scope is not None else clean_text
                )
                self.workspace.submit(
                    WorkspaceItem(
                        source=workspace_source,
                        content=workspace_content,
                        salience=salience,
                        urgency=self.affect.arousal,
                        emotional_weight=abs(self.affect.valence),
                    )
                )

                # Commit salient episodic trace to SHA-256 hash chain
                if persist_stimulus and salience >= self.config.salience_commit_threshold:
                    if memory_scope is not None:
                        # Never trust arbitrary external tags in a private ledger: only stable
                        # non-identifying labels are retained. Sender IDs are not persisted.
                        merged_tags = ["private_scope", self.affect.dominant_emotion]
                    else:
                        merged_tags = list({*(tags or []), source, self.affect.dominant_emotion})
                    block = active_memory.append(
                        content=clean_text,
                        kind="episodic",
                        salience=salience,
                        affect_valence=self.affect.valence,
                        tags=merged_tags,
                    )
                    committed_block_index = block.index
            else:
                self.affect.decay(0.06)

            self.neuro.step(
                dt=step_dt,
                arousal=self.affect.arousal,
                stress=self.intero.allostatic_load,
            )

            # Submit interoceptive drive if elevated
            max_drive_name, max_drive_val = max(drives.items(), key=lambda kv: kv[1])
            if max_drive_val >= 0.45:
                self.workspace.submit(
                    WorkspaceItem(
                        source="interoception",
                        content=f"Homeostatic drive elevated: {max_drive_name}={max_drive_val:.2f}",
                        salience=max_drive_val,
                        urgency=self.intero.allostatic_load,
                        emotional_weight=0.25,
                    )
                )

            # 4. Global Workspace Competition & Attention Schema Broadcast
            broadcast = self.workspace.compete_and_broadcast(
                attention_precision=self.neuro.acetylcholine
            )

            # 5. Active Inference Deliberation via Expected Free Energy (EFE)
            decision = self.volition.deliberate(
                config=self.config,
                has_external_input=has_input,
                novelty=novelty,
                valence=self.affect.valence,
                drives=drives,
                dopamine=self.neuro.dopamine,
            )

            # 6. Action Consent Gate & Self-Model Update
            action_gate = self.gate.evaluate_action(
                policy=decision.policy,
                external_side_effect=(decision.policy in ("respond_empathetically", "clarify_and_explore")),
                consent_granted=consent_granted,
                config=self.config,
            )
            if action_gate.allowed:
                self.metrics.total_actions += 1
            else:
                self.metrics.blocked_actions += 1

            chain_ok, chain_msg = active_memory.verify_chain()
            self.diri.update(
                prediction_error=decision.ambiguity,
                chain_valid=chain_ok,
                coherence=self.nadi.coherence,
            )

            # 7. Integration Metrics & Atomic Persistence
            self.metrics.update_integration(
                [
                    self.nadi.coherence,
                    self.intero.energy,
                    1.0 - self.intero.allostatic_load,
                    self.neuro.serotonin,
                    self.diri.agency_score,
                ]
            )
            self.metrics.update_entropy(
                [e["epistemic_value"] for e in self.volition.last_evaluations]
            )

            # Auto-trigger background sleep consolidation if autonomous policy selected it
            auto_sleep_report = None
            if allow_auto_sleep and not has_input and decision.policy == "consolidate_sleep_cycle":
                auto_sleep_report = self.sleep(memory_scope=memory_scope)

            elapsed = monotonic_ms() - t0
            self.metrics.record_tick(elapsed)
            if persist_snapshot:
                self.save_snapshot()

            return {
                "status": "ok",
                "tick": self.metrics.total_ticks,
                "pulse": pulse,
                "drives": drives,
                "affect": self.affect.to_dict(),
                "neuro": self.neuro.to_dict(),
                "broadcast": broadcast,
                "volition": {
                    "selected_policy": decision.policy,
                    "expected_free_energy": decision.expected_free_energy,
                    "rationale": decision.rationale,
                    "authorized": action_gate.allowed,
                },
                "recalled_memories": recalled,
                "committed_block_index": committed_block_index,
                "chain_integrity": {"valid": chain_ok, "detail": chain_msg},
                "auto_sleep": auto_sleep_report,
                "metrics": self.metrics.to_dict(),
            }

    def start_heartbeat(self, interval_sec: Optional[float] = None) -> Dict[str, Any]:
        """Start one managed, drift-corrected background heartbeat thread (idempotent)."""
        interval = float(interval_sec if interval_sec is not None else self.config.tick_interval_sec)
        interval = max(0.25, min(60.0, interval))
        with self._heartbeat_lock:
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                return dict(self._heartbeat_state)
            self._heartbeat_stop.clear()
            self._heartbeat_state.update({
                "running": True, "interval_sec": interval,
                "started_at": utc_now_iso(), "last_error": None,
            })

            def _run() -> None:
                last = time.monotonic()
                deadline = last + interval
                while not self._heartbeat_stop.is_set():
                    wait_for = max(0.0, deadline - time.monotonic())
                    if self._heartbeat_stop.wait(wait_for):
                        break
                    now = time.monotonic()
                    elapsed = max(0.05, min(300.0, now - last))
                    last = now
                    try:
                        self.tick(
                            source="heartbeat", dt=elapsed, allow_auto_sleep=False,
                            persist_stimulus=False, persist_snapshot=False,
                        )
                        with self._heartbeat_lock:
                            self._heartbeat_state["ticks"] = int(self._heartbeat_state.get("ticks", 0)) + 1
                            self._heartbeat_state["last_beat_at"] = utc_now_iso()
                            self._heartbeat_state["last_error"] = None
                            should_checkpoint = int(self._heartbeat_state["ticks"]) % 30 == 0
                        # Do not acquire the kernel state lock while holding the heartbeat lock.
                        if should_checkpoint:
                            self.save_snapshot()
                    except Exception as exc:  # keep the service alive but expose health degradation
                        with self._heartbeat_lock:
                            self._heartbeat_state["last_error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
                    deadline += interval
                    if deadline < time.monotonic() - interval:
                        # Coalesce missed beats; never run a catch-up storm after a long pause.
                        deadline = time.monotonic() + interval
                with self._heartbeat_lock:
                    self._heartbeat_state["running"] = False

            self._heartbeat_thread = threading.Thread(
                target=_run, name="nadi-heartbeat", daemon=True
            )
            self._heartbeat_thread.start()
            return dict(self._heartbeat_state)

    def stop_heartbeat(self, timeout_sec: float = 10.0) -> Dict[str, Any]:
        """Stop the heartbeat cleanly and persist the last stable snapshot."""
        timeout = max(0.1, min(30.0, float(timeout_sec)))
        self._heartbeat_stop.set()
        thread = self._heartbeat_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        with self._heartbeat_lock:
            still_running = bool(thread and thread.is_alive())
            self._heartbeat_state["running"] = still_running
        self.save_snapshot()
        return dict(self._heartbeat_state)

    def heartbeat_status(self) -> Dict[str, Any]:
        with self._heartbeat_lock:
            state = dict(self._heartbeat_state)
            state["running"] = bool(self._heartbeat_thread and self._heartbeat_thread.is_alive())
            return state

    def sleep(self, memory_scope: Optional[str] = None) -> Dict[str, Any]:
        """Run an NREM/REM sleep consolidation cycle and restore homeostatic reserves."""
        with self._lock:
            memory = self._memory_for_scope(memory_scope) if memory_scope is not None else self.memory
            report = self.dreamer.sleep_cycle(
                memory=memory,
                batch_size=self.config.dream_replay_batch,
                merge_threshold=self.config.dream_similarity_merge_threshold,
            )
            if report.get("status") == "completed":
                self.intero.recover_during_sleep(quality=float(report.get("sleep_quality", 0.75)))
                self.metrics.total_sleep_cycles += 1
                insights = report.get("insights") or []
                latest_insight = insights[-1]["content"] if insights else ""
                chain_ok, _ = memory.verify_chain()
                # A private user's dream insight must never enter the shared identity narrative.
                if memory_scope is None:
                    self.diri.update(
                        prediction_error=0.1,
                        chain_valid=chain_ok,
                        coherence=self.nadi.coherence,
                        recent_insight=latest_insight,
                    )
            self.save_snapshot()
            return report

    def status(self) -> Dict[str, Any]:
        """Return full inspectable snapshot of the kernel state."""
        with self._lock:
            chain_ok, chain_msg = self.memory.verify_chain()
            return {
                "agent_name": self.config.agent_name,
                "kernel_version": NADI_KERNEL_VERSION,
                "persona_role": self.config.persona_role,
                "nadi": self.nadi.to_dict(),
                "intero": self.intero.to_dict(),
                "neuro": self.neuro.to_dict(),
                "affect": self.affect.to_dict(),
                "workspace": self.workspace.to_dict(),
                "diri": self.diri.to_dict(),
                "volition": self.volition.to_dict(),
                "metrics": self.metrics.to_dict(),
                "heartbeat": self.heartbeat_status(),
                "private_memory_scopes_cached": len(self._scope_memories),
                "memory": {
                    "total_blocks": len(self.memory.blocks),
                    "head_hash": self.memory.head_hash,
                    "chain_valid": chain_ok,
                    "chain_detail": chain_msg,
                },
            }
