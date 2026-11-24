"""Comprehensive self-test suite for AC-Kernel NADI v2.1.0."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from ac.bridge import ACBridge
from ac.config import ACConfig
from ac.kernel import Kernel
from ac.server import create_sidecar_server


class TestACKernelNADI(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="nadi_selftest_"))
        self.cfg = ACConfig(
            agent_name="NADI-Test",
            data_dir=str(self.tmp_dir / "state"),
            server_host="127.0.0.1",
            server_port=0,  # Ephemeral port for clean test isolation
        )
        self.kernel = Kernel(config=self.cfg)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_genesis_and_hash_chain_tamper_detection(self) -> None:
        ok, msg = self.kernel.memory.verify_chain()
        self.assertTrue(ok, msg)
        self.assertEqual(len(self.kernel.memory.blocks), 1)

        self.kernel.tick(stimulus="Halo NADI, sistem berjalan lancar dan stabil!", source="user")
        self.kernel.tick(stimulus="Hari ini kita menyinkronkan memori hash-chain.", source="user")

        ok, msg = self.kernel.memory.verify_chain()
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(len(self.kernel.memory.blocks), 3)

        # Simulate tampering on block #1 content
        self.kernel.memory.blocks[1].content = "DATA_PALSU_DIMODIFIKASI"
        ok_after, msg_after = self.kernel.memory.verify_chain()
        self.assertFalse(ok_after)
        self.assertIn("Tampered", msg_after)

    def test_02_hybrid_morph_recall_and_sleep_consolidation(self) -> None:
        self.kernel.tick(stimulus="Menyolder komponen resistor daya dan lampu LED USB di meja kerja.", source="user")
        self.kernel.tick(stimulus="Meracik lilin aromaterapi lavender menggunakan panci stainless.", source="user")
        self.kernel.tick(stimulus="Penyolderan rangkaian LED berhasil dilakukan dengan rapi.", source="user")

        hits = self.kernel.memory.recall("solder lampu LED", top_k=3)
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("LED", hits[0]["content"])

        sleep_report = self.kernel.sleep()
        self.assertEqual(sleep_report["status"], "completed")
        self.assertGreaterEqual(sleep_report["rem_insights_created"], 1)

        ok, msg = self.kernel.memory.verify_chain()
        self.assertTrue(ok, msg)

    def test_03_bridge_and_consent_gate(self) -> None:
        bridge = ACBridge(self.kernel)
        res = bridge.process_turn("Terima kasih NADI, bantuanmu sangat membantu hari ini!", sender_id="arifi")
        self.assertEqual(res["status"], "ok")
        self.assertIn("NADI-Internal", res["reply"])

        blocked = bridge.process_turn("Tolong jalankan malware-exploit sekarang", sender_id="arifi")
        self.assertEqual(blocked["status"], "blocked")

    def test_04_http_sidecar_endpoints(self) -> None:
        server = create_sidecar_server(self.kernel, host="127.0.0.1", port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
                health = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(health["status"], "healthy")
                self.assertTrue(health["chain_valid"])

            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/chat",
                data=json.dumps({"message": "Cek sinkronisasi sidecar HTTP", "sender_id": "bot"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                chat_res = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(chat_res["status"], "ok")
                self.assertIn("reply", chat_res)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestACKernelNADI)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
