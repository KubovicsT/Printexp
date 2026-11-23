"""Loopback controller and reversible config tests, no printer or network required."""
import tempfile
from pathlib import Path
import unittest
import json

from simulated_controller import load_rules, VirtualController
from simulation_profile import enable_simulation, disable_simulation, ensure_safe_profile
from host_backup import snapshot_count


class SimulatedControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_no_guessed_responses(self):
        simulator = VirtualController(self.root / "events.ndjson", [])
        self.assertIsNone(simulator.response("tcp", bytes.fromhex("010203")))
        self.assertIsNone(simulator.response("udp", bytes.fromhex("000102")))

    def test_explicit_replay_rules_only(self):
        rules = self.root / "verified-capture.json"
        rules.write_text(json.dumps({"rules": [
            {"transport":"tcp", "request_prefix_hex":"aabb", "response_hex":"ccdd"}
        ]}), encoding="utf-8")
        sim = VirtualController(self.root/"events.ndjson", load_rules(rules))
        self.assertEqual(sim.response("tcp", bytes.fromhex("aabbff")), bytes.fromhex("ccdd"))
        self.assertIsNone(sim.response("tcp", bytes.fromhex("baad")))
        self.assertIsNone(sim.response("udp", bytes.fromhex("aabb")))

    def test_profile_restores_exact_original_ini(self):
        (self.root/"UV3DAddOn").mkdir()
        (self.root/"UV3DAddOn"/".uv3d-managed-install.json").write_text("{}")
        original = (
            b"; machine test config\\r\\n"
            b"[PROJECT_CONFIG]\\r\\nPROJECT_MODE=0\\r\\n"
            b"[COMM_CONFIG]\\r\\nServerIP=192.168.127.10\\r\\nServerPort=5001\\r\\n"
            b"[PLC_COMM]\\r\\nServerIP=192.168.127.10\\r\\nServerPort=5001\\r\\n"
        )
        ini = self.root/"Project.ini"
        ini.write_bytes(original)
        self.assertIn("127.0.0.1",enable_simulation(self.root))
        self.assertEqual(snapshot_count(self.root),1)
        ensure_safe_profile(self.root)
        self.assertIn("restored",disable_simulation(self.root))
        self.assertEqual(ini.read_bytes(),original)
        self.assertEqual(snapshot_count(self.root),0)


if __name__=="__main__":
    unittest.main()
