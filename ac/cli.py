"""Command-Line Interface for AC-Kernel NADI v2.1.0 (Mobile Termux / Desktop)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .bridge import ACBridge
from .config import ACConfig
from .kernel import Kernel
from .server import create_sidecar_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ac-nadi",
        description="AC-Kernel NADI v2.1.0 — Functional Artificial Consciousness Kernel CLI",
    )
    parser.add_argument(
        "--config",
        default="ac_config.json",
        help="Path to JSON config file (default: ac_config.json)",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override persistent state directory",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize config and genesis hash-chain ledger")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing config file")

    p_tick = sub.add_parser("tick", help="Run one cognitive tick (optionally with stimulus)")
    p_tick.add_argument("--stimulus", default=None, help="Optional input text stimulus")
    p_tick.add_argument("--source", default="cli", help="Stimulus source identifier")

    p_chat = sub.add_parser("chat", help="Process an interactive or one-shot bridge turn")
    p_chat.add_argument("message", nargs="?", default=None, help="User message (omit for REPL)")
    p_chat.add_argument("--sender", default="user", help="Sender identifier")

    p_recall = sub.add_parser("recall", help="Query associative SHA-256 hash-chain memory")
    p_recall.add_argument("query", help="Search query")
    p_recall.add_argument("-k", type=int, default=5, help="Number of results")

    sub.add_parser("sleep", help="Run NREM/REM sleep consolidation cycle")
    sub.add_parser("verify", help="Verify cryptographic integrity of the SHA-256 hash chain")
    sub.add_parser("status", help="Display current kernel state snapshot")

    p_serve = sub.add_parser("serve", help="Start HTTP sidecar server")
    p_serve.add_argument("--host", default=None, help="Bind host")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port")

    return parser


def _load_kernel(args: argparse.Namespace) -> Kernel:
    cfg = ACConfig.load(args.config)
    if args.data_dir:
        cfg.data_dir = args.data_dir
    return Kernel(config=cfg)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        cfg_path = Path(args.config)
        cfg = ACConfig()
        if args.data_dir:
            cfg.data_dir = args.data_dir
        if not cfg_path.exists() or args.force:
            cfg.save(cfg_path)
        kernel = Kernel(config=cfg)
        ok, detail = kernel.memory.verify_chain()
        print(json.dumps({"initialized": True, "config": str(cfg_path), "chain": detail, "valid": ok}, indent=2))
        return 0

    kernel = _load_kernel(args)

    if args.command == "tick":
        res = kernel.tick(stimulus=args.stimulus, source=args.source)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.command == "chat":
        bridge = ACBridge(kernel)
        if args.message:
            res = bridge.process_turn(user_message=args.message, sender_id=args.sender)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0

        print(f"=== {kernel.config.agent_name} Interactive REPL (ketik 'exit' untuk keluar) ===")
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line or line.lower() in ("exit", "quit"):
                break
            res = bridge.process_turn(user_message=line, sender_id=args.sender)
            print(f"[{res['cycle']['affect']['dominant_emotion']}] {res['reply']}")
        return 0

    if args.command == "recall":
        hits = kernel.memory.recall(query=args.query, top_k=args.k)
        print(json.dumps({"query": args.query, "results": hits}, indent=2, ensure_ascii=False))
        return 0

    if args.command == "sleep":
        rep = kernel.sleep()
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0

    if args.command == "verify":
        ok, detail = kernel.memory.verify_chain()
        print(json.dumps({"valid": ok, "detail": detail, "head_hash": kernel.memory.head_hash}, indent=2))
        return 0 if ok else 2

    if args.command == "status":
        print(json.dumps(kernel.status(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "serve":
        server = create_sidecar_server(kernel, host=args.host, port=args.port)
        addr, prt = server.server_address
        print(f"AC-Kernel NADI v2.1.0 sidecar listening on http://{addr}:{prt}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
