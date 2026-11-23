"""Offline PrintExp development mode: preserve original GBK INI and rollback."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_profile import (OfflineProfileError, enable_offline, disable_offline,
                             read_project_mode)
from host_backup import snapshot_count


class OfflineProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "PrintExp"
        self.addon = self.root / "UV3DAddOn"
        self.addon.mkdir(parents=True)
        (self.addon / ".uv3d-managed-install.json").write_text("{}", encoding="ascii")
        self.ini = self.root / "Project.ini"
        self.original = (
            b"; " + "\u8c03\u8bd5".encode("gbk") +
            b"\r\n[PROJECT_CONFIG]\r\nPROJECT_MODE=0\r\n"
            b"[VISION_PRINT]\r\nSUPPORT_VISION_PRINT=1;\r\n"
        )
        self.ini.write_bytes(self.original)

    def test_enable_restore_and_original_hash(self):
        result = enable_offline(self.root)
        self.assertIn("PROJECT_MODE=1", result)
        self.assertEqual(read_project_mode(self.root), 1)
        self.assertEqual(snapshot_count(self.root), 1)
        self.assertEqual(read_project_mode(self.root), 1)
        self.assertEqual(self.ini.read_bytes().replace(b"PROJECT_MODE=1", b"PROJECT_MODE=0"),
                         self.original)
        self.assertIn("restored", disable_offline(self.root))
        self.assertEqual(self.ini.read_bytes(), self.original)
        self.assertEqual(snapshot_count(self.root), 0)

    def test_enable_twice_does_not_duplicate_backups(self):
        enable_offline(self.root)
        self.assertIn("already enabled", enable_offline(self.root))
        self.assertEqual(snapshot_count(self.root), 1)

    def test_refuse_external_changes_during_restore(self):
        enable_offline(self.root)
        self.ini.write_bytes(b"[PROJECT_CONFIG]\r\nPROJECT_MODE=0\r\n; modified manually")
        with self.assertRaises((OfflineProfileError, Exception)):
            disable_offline(self.root)
        self.assertEqual(snapshot_count(self.root), 1)

    def test_unmanaged_debug_mode_is_not_modified(self):
        self.ini.write_bytes(self.original.replace(b"PROJECT_MODE=0", b"PROJECT_MODE=1"))
        self.assertIn("already has debug mode", enable_offline(self.root))
        self.assertEqual(snapshot_count(self.root), 0)
        disable_offline(self.root)
        self.assertEqual(read_project_mode(self.root), 1)

    def test_missing_config_refused(self):
        self.ini.write_bytes(b"[OTHER]\r\nPROJECT_MODE=0\r\n")
        with self.assertRaises(OfflineProfileError):
            enable_offline(self.root)
        self.assertEqual(snapshot_count(self.root), 0)

    def test_original_unchanged_without_addon(self):
        (self.addon / ".uv3d-managed-install.json").unlink()
        with self.assertRaises(OfflineProfileError):
            enable_offline(self.root)
        self.assertEqual(self.ini.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
