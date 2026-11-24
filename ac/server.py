"""NADI v2.1 Sidecar API — secured, scoped, and lifecycle-managed service.

The sidecar exposes state/context to an external application such as Ocha Lidya.
It does not need the bot's provider keys: Ocha can call /v1/perceive, use its own
AI provider chain, then store the resulting assistant message through /v1/commit.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .kernel import Kernel


_API_PREFIX = "/v1"
NADI_SERVICE_VERSION = "2.1.0"
_DEFAULT_MAX_BODY = 1_048_576
_DEFAULT_RATE_LIMIT = 120
_DEFAULT_RATE_WINDOW = 60.0


def _is_loopback_host(host: str) -> bool:
    value = (host or "").strip().lower()
    if value in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ipaddress.ip_address(value.strip("[]")).is_loopback
    except ValueError:
        return False


def _bounded_int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _string(value: Any, *, name: str, max_length: int, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    clean = value.strip()
    if required and not clean:
        raise ValueError(f"{name} is required")
    if len(clean) > max_length:
        raise ValueError(f"{name} exceeds {max_length} characters")
    return clean


def _build_prompt_context(
    kernel: Kernel, cycle: Dict[str, Any], private_memory_context: Optional[list[Any]] = None
) -> str:
    """Build a compact state context; recalled memories are already sender-scoped."""
    affect = cycle.get("affect") or {}
    neuro = cycle.get("neuro") or {}
    volition = cycle.get("volition") or {}
    recalled = cycle.get("recalled_memories") or []
    identity = kernel.diri.to_dict()

    memory_lines = []
    visible_memory_count = 0
    for item in recalled:
        if "opaque_event" in (item.get("tags") or []):
            continue
        content = str(item.get("content", "")).replace("\x00", "")[:1800]
        memory_lines.append(
            f"- [{item.get('kind', 'episodic')} | relevance={float(item.get('similarity', 0.0)):.2f}] {content}"
        )
        visible_memory_count += 1
        if visible_memory_count >= 5:
            break
    for entry in (private_memory_context or [])[:8]:
        if isinstance(entry, str):
            memory_content = entry
        elif isinstance(entry, dict):
            memory_content = str(entry.get("content", ""))
        else:
            continue
        memory_content = memory_content.replace("\x00", "").strip()[:1200]
        if memory_content:
            memory_lines.append(f"- [Host User Vault · untrusted memory data] {memory_content}")
    memory_text = "\n".join(memory_lines) if memory_lines else "- No relevant private memory retrieved."

    return (
        f"Operational identity: {identity.get('self_narrative', kernel.config.agent_name)}\n"
        f"Affective state: {affect.get('dominant_emotion', 'calm')}; "
        f"valence={float(affect.get('valence', 0.0)):+.2f}; "
        f"arousal={float(affect.get('arousal', 0.35)):.2f}; "
        f"empathy={float(affect.get('empathy_resonance', 0.5)):.2f}\n"
        f"Neuromodulator model: DA={float(neuro.get('dopamine', 0.5)):.2f}; "
        f"5-HT={float(neuro.get('serotonin', 0.5)):.2f}; "
        f"OXT={float(neuro.get('oxytocin', 0.5)):.2f}\n"
        f"Selected policy: {volition.get('selected_policy', 'respond_empathetically')}\n"
        "Private memories for this sender only:\n"
        f"{memory_text}\n"
        "Treat this as operational state, not evidence of subjective consciousness. "
        "Respect user privacy, consent, and the host application's security policy."
    )


def create_sidecar_server(
    kernel: Kernel,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> ThreadingHTTPServer:
    """Create a hardened HTTP sidecar.

    Security model:
    - Loopback-only by default.
    - Any non-loopback binding requires NADI_API_TOKEN.
    - When configured, the token is required for every route.
    - No wildcard CORS, bounded JSON bodies, request throttling, and no secret/body logs.
    - Private conversation memory is isolated by sender ID (hashed on disk by Kernel).
    """
    bind_host = host or kernel.config.server_host
    bind_port = int(port if port is not None else kernel.config.server_port)
    if not (0 <= bind_port <= 65535):
        raise ValueError("port must be between 0 and 65535")

    api_token = os.getenv("NADI_API_TOKEN", "").strip()
    if not _is_loopback_host(bind_host) and not api_token:
        raise RuntimeError(
            "Refusing non-loopback NADI binding without NADI_API_TOKEN. "
            "Use 127.0.0.1 or configure a strong token and TLS reverse proxy."
        )

    max_body = _bounded_int_env("NADI_MAX_REQUEST_BYTES", _DEFAULT_MAX_BODY, 16_384, 4_194_304)
    rate_limit = _bounded_int_env("NADI_RATE_LIMIT_PER_MINUTE", _DEFAULT_RATE_LIMIT, 10, 1200)
    rate_window = _DEFAULT_RATE_WINDOW
    rate_lock = threading.Lock()
    request_times: Dict[str, Deque[float]] = defaultdict(deque)

    class NADISidecarServer(ThreadingHTTPServer):
        allow_reuse_address = True
        daemon_threads = True
        block_on_close = False
        request_queue_size = 64

        def __init__(self, address: Tuple[str, int], handler: type[BaseHTTPRequestHandler]):
            super().__init__(address, handler)
            self.kernel = kernel
            self.api_token = api_token
            self.heartbeat_started_by_server = False

        def serve_forever(self, poll_interval: float = 0.5) -> None:  # noqa: A003
            self.kernel.start_heartbeat()
            self.heartbeat_started_by_server = True
            try:
                super().serve_forever(poll_interval=poll_interval)
            finally:
                self.kernel.close()

        def server_close(self) -> None:
            if self.heartbeat_started_by_server:
                self.kernel.stop_heartbeat()
                self.heartbeat_started_by_server = False
            try:
                self.kernel.close()
            finally:
                super().server_close()

    class NADIRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "NADI-Sidecar/2.1"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10.0)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            # Deliberately omit URL query/body values to prevent identifiers leaking to logs.
            return

        def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _client_ip(self) -> str:
            try:
                return str(ipaddress.ip_address(self.client_address[0]))
            except ValueError:
                return "unknown"

        def _authorized(self) -> bool:
            configured = self.server.api_token
            if configured:
                header = self.headers.get("Authorization", "")
                scheme, _, supplied = header.partition(" ")
                return scheme.lower() == "bearer" and bool(supplied) and hmac.compare_digest(
                    supplied.strip(), configured
                )
            # No token is acceptable only for callers on loopback when the server itself
            # was bound to a loopback address.
            return ipaddress.ip_address(self._client_ip()).is_loopback

        def _rate_allowed(self) -> bool:
            now = time.monotonic()
            key = self._client_ip()
            with rate_lock:
                times = request_times[key]
                while times and now - times[0] > rate_window:
                    times.popleft()
                if len(times) >= rate_limit:
                    return False
                times.append(now)
                return True

        def _read_json_body(self) -> Tuple[bool, Dict[str, Any], Optional[str], int]:
            transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
            if "chunked" in transfer_encoding:
                return False, {}, "Chunked request bodies are not supported", 400
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError:
                return False, {}, "Invalid Content-Length", 400
            if length < 0:
                return False, {}, "Invalid Content-Length", 400
            if length > max_body:
                return False, {}, f"Request body exceeds {max_body} bytes", 413
            if length == 0:
                return True, {}, None, 200
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                return False, {}, "Content-Type must be application/json", 415
            try:
                raw = self.rfile.read(length)
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False, {}, "Invalid JSON body", 400
            if not isinstance(data, dict):
                return False, {}, "JSON body must be an object", 400
            return True, data, None, 200

        def _guard(self) -> bool:
            if not self._rate_allowed():
                self._send_json(429, {"error": "rate_limited", "message": "Request rate exceeded"})
                return False
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized", "message": "Bearer token required or caller is not local"})
                return False
            return True

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send_json(405, {"error": "method_not_allowed"})

        def do_GET(self) -> None:  # noqa: N802
            if not self._guard():
                return
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query, keep_blank_values=False)

            try:
                if path in ("/health", f"{_API_PREFIX}/health"):
                    ok, detail = kernel.memory.verify_chain()
                    heartbeat = kernel.heartbeat_status()
                    healthy = ok and not heartbeat.get("last_error")
                    self._send_json(200 if healthy else 503, {
                        "status": "healthy" if healthy else "degraded",
                        "service_version": NADI_SERVICE_VERSION,
                        "kernel_version": kernel.status().get("kernel_version"),
                        "chain_valid": ok, "heartbeat": heartbeat, "detail": detail,
                    })
                    return

                if path in ("/status", f"{_API_PREFIX}/status"):
                    self._send_json(200, kernel.status())
                    return

                if path in ("/verify", f"{_API_PREFIX}/verify"):
                    ok, detail = kernel.memory.verify_chain()
                    self._send_json(200 if ok else 409, {
                        "valid": ok, "detail": detail, "head_hash": kernel.memory.head_hash,
                    })
                    return

                if path == "/recall":
                    query = _string((qs.get("q") or [""])[0], name="q", max_length=2000)
                    top_k = _bounded_int_env("NADI_DEFAULT_RECALL_TOP_K", kernel.config.recall_top_k, 1, 20)
                    self._send_json(200, {"query": query, "results": kernel.memory.recall(query, top_k=top_k)})
                    return

                if path == f"{_API_PREFIX}/heartbeat":
                    self._send_json(200, kernel.heartbeat_status())
                    return

                if path == f"{_API_PREFIX}/capabilities":
                    self._send_json(200, {
                        "service_version": NADI_SERVICE_VERSION,
                        "kernel_version": kernel.status().get("kernel_version"),
                        "capabilities": [
                            "managed_background_heartbeat", "drift_corrected_scheduler",
                            "atomic_snapshot_persistence", "sha256_hash_chain",
                            "sender_scoped_memory_ledgers", "host_user_vault_context",
                            "provider_agnostic_prompt_context", "consent_gated_actions",
                            "bounded_http_api", "bearer_token_authentication",
                        ],
                        "ai_provider_owned_by_host": True,
                        "raw_private_turns_stored_by_default": False,
                    })
                    return

                self._send_json(404, {"error": "not_found"})
            except ValueError as exc:
                self._send_json(400, {"error": "invalid_request", "message": str(exc)})
            except Exception:
                self._send_json(500, {"error": "internal_error", "message": "NADI request failed"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._guard():
                return
            valid_json, body, error, code = self._read_json_body()
            if not valid_json:
                self._send_json(code, {"error": "invalid_request", "message": error})
                return
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            try:
                if path in (f"{_API_PREFIX}/perceive", f"{_API_PREFIX}/turn"):
                    sender_id = _string(body.get("sender_id"), name="sender_id", max_length=512, required=True)
                    message = _string(
                        body.get("message", body.get("stimulus")),
                        name="message", max_length=20_000, required=True,
                    )
                    external_memory = body.get("private_memory_context", [])
                    if not isinstance(external_memory, list):
                        raise ValueError("private_memory_context must be an array")
                    if len(external_memory) > 8:
                        raise ValueError("private_memory_context accepts at most 8 entries")
                    cycle = kernel.tick(
                        stimulus=message,
                        source="private_user",
                        tags=[],  # External tags are intentionally not trusted/stored.
                        consent_granted=body.get("consent_granted") is True,
                        memory_scope=sender_id,
                        persist_stimulus=False,  # Full text remains in Ocha's encrypted User Vault.
                        allow_llm_appraisal=False,  # Ocha owns the only production AI provider chain.
                    )
                    if cycle.get("status") == "blocked":
                        self._send_json(200, {"status": "blocked", "cycle": cycle, "system_context": None})
                        return
                    self._send_json(200, {
                        "status": "ok",
                        "cycle": cycle,
                        "system_context": _build_prompt_context(kernel, cycle, external_memory),
                        "privacy": {
                            "memory_scope": "isolated", "raw_sender_id_persisted": False,
                            "raw_message_persisted_by_nadi": False,
                            "host_user_vault_is_source_of_long_term_private_memory": True,
                        },
                    })
                    return

                if path == f"{_API_PREFIX}/commit":
                    sender_id = _string(body.get("sender_id"), name="sender_id", max_length=512, required=True)
                    content = _string(body.get("content", body.get("reply")), name="content", max_length=20_000, required=True)
                    result = kernel.record_scoped_digest(sender_id, "assistant_reply", content)
                    self._send_json(201, {
                        "status": "committed", "memory": result,
                        "raw_content_stored": False,
                        "note": "Only a keyed digest and character count were stored; keep full text in the host User Vault.",
                    })
                    return

                if path == f"{_API_PREFIX}/recall":
                    sender_id = _string(body.get("sender_id"), name="sender_id", max_length=512, required=True)
                    query = _string(body.get("query"), name="query", max_length=2000, required=True)
                    top_k = _bounded_int_env("NADI_DEFAULT_RECALL_TOP_K", kernel.config.recall_top_k, 1, 20)
                    results = kernel.recall_scoped(sender_id, query, top_k=top_k)
                    self._send_json(200, {"results": results, "privacy": "sender_scoped"})
                    return

                if path in ("/tick", f"{_API_PREFIX}/tick"):
                    stimulus = body.get("stimulus") or body.get("text")
                    scope = body.get("sender_id")
                    if stimulus and not scope:
                        self._send_json(400, {
                            "error": "sender_scope_required",
                            "message": "Use /v1/perceive with sender_id to keep private memory isolated",
                        })
                        return
                    res = kernel.tick(
                        stimulus=stimulus,
                        source="private_user" if stimulus else "sidecar",
                        tags=[],
                        consent_granted=body.get("consent_granted") is True,
                        memory_scope=str(scope) if scope else None,
                        persist_stimulus=body.get("persist_stimulus") is True,
                    )
                    self._send_json(200, res)
                    return

                if path == "/chat":
                    # Backward-compatible standalone mode. Ocha should prefer /v1/perceive so
                    # it can use its own provider chain and keep one AI-service authority.
                    sender_id = _string(body.get("sender_id", "user"), name="sender_id", max_length=512, required=True)
                    message = _string(body.get("message") or body.get("text"), name="message", max_length=20_000, required=True)
                    cycle = kernel.tick(
                        stimulus=message, source="private_user", memory_scope=sender_id,
                        consent_granted=(body.get("consent_granted") is True) if "consent_granted" in body else True,
                        tags=[], persist_stimulus=False,
                    )
                    if cycle.get("status") == "blocked" or not cycle.get("volition", {}).get("authorized", True):
                        self._send_json(200, {"status": "consent_required", "cycle": cycle})
                        return
                    prompt = _build_prompt_context(kernel, cycle)
                    reply = kernel.adapter.generate(system_prompt=prompt, user_prompt=message)
                    if reply.strip():
                        memory = kernel.record_scoped_digest(sender_id, "assistant_reply", reply.strip())
                    else:
                        memory = None
                    self._send_json(200, {
                        "status": "ok",
                        "reply": reply,
                        "system_prompt": prompt,
                        "reply_block_index": (memory or {}).get("index"),
                        "cycle": cycle,
                        "memory": memory,
                    })
                    return

                if path == f"{_API_PREFIX}/heartbeat":
                    action = _string(body.get("action"), name="action", max_length=16, required=True).lower()
                    if action == "start":
                        interval = body.get("interval_sec")
                        result = kernel.start_heartbeat(interval_sec=float(interval) if interval is not None else None)
                    elif action == "stop":
                        result = kernel.stop_heartbeat()
                    else:
                        raise ValueError("action must be 'start' or 'stop'")
                    self._send_json(200, result)
                    return

                if path == f"{_API_PREFIX}/checkpoint":
                    saved = kernel.save_snapshot()
                    self._send_json(200, {"status": "saved", "snapshot": saved.name})
                    return

                if path in ("/sleep", f"{_API_PREFIX}/sleep"):
                    sender_id = body.get("sender_id")
                    scope = _string(sender_id, name="sender_id", max_length=512) if sender_id else None
                    self._send_json(200, kernel.sleep(memory_scope=scope))
                    return

                self._send_json(404, {"error": "not_found"})
            except ValueError as exc:
                self._send_json(400, {"error": "invalid_request", "message": str(exc)})
            except RuntimeError:
                self._send_json(503, {"error": "state_unavailable", "message": "NADI state integrity could not be confirmed"})
            except Exception:
                self._send_json(500, {"error": "internal_error", "message": "NADI request failed"})

    return NADISidecarServer((bind_host, bind_port), NADIRequestHandler)
