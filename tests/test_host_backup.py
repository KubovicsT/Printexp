"""Host patch containment and exact restoration tests (never touch real PrintExp)."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from host_backup import (HostPatchError, apply_host_patch, restore_host_patches,
                         verify_patched_host, snapshot_count)


class HostPatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "Vendor"
        self.root.mkdir()
        (self.root / "UV3DAddOn").mkdir()
        self.exe = self.root / "PrintExp_X64.exe"
        self.original = b"original test executable (not a real printer)"
        self.exe.write_bytes(self.original)
        self.sha = hashlib.sha256(self.original).hexdigest()

    def test_patch_and_restore_only_inside_selected_folder(self):
        apply_host_patch(self.root, "PrintExp_X64.exe", self.sha, b"patched")
        self.assertTrue(verify_patched_host(self.root, "PrintExp_X64.exe", self.sha))
        self.assertEqual(self.exe.read_bytes(), b"patched")
        self.assertEqual(snapshot_count(self.root), 1)
        backup = self.root / "UV3DAddOn" / ".host-patches"
        self.assertTrue(backup.is_dir())
        self.assertTrue(list(backup.glob("*.original")))
        restore_host_patches(self.root)
        self.assertEqual(self.exe.read_bytes(), self.original)
        self.assertEqual(snapshot_count(self.root), 0)

    def test_wrong_original_hash_refused(self):
        with self.assertRaises(HostPatchError):
            apply_host_patch(self.root, "PrintExp_X64.exe", "00" * 32, b"patched")
        self.assertEqual(self.exe.read_bytes(), self.original)

    def test_escaped_path_refused(self):
        for relative in ("../outside.exe", "/tmp/outside", "UV3DAddOn/config.ini"):
            with self.assertRaises(HostPatchError):
                apply_host_patch(self.root, relative, self.sha, b"patched")

    def test_double_patch_refused(self):
        apply_host_patch(self.root, "PrintExp_X64.exe", self.sha, b"patched")
        with self.assertRaises(HostPatchError):
            apply_host_patch(self.root, "PrintExp_X64.exe", self.sha, b"other")

    def test_uninstall_refuses_unrecognized_modified_host(self):
        apply_host_patch(self.root, "PrintExp_X64.exe", self.sha, b"patched")
        self.exe.write_bytes(b"user modified")
        with self.assertRaisesRegex(HostPatchError, "changed since patching"):
            restore_host_patches(self.root)
        self.assertEqual(self.exe.read_bytes(), b"user modified")

    def test_cannot_traverse_symlink(self):
        other = self.root.parent / "other"
        other.mkdir()
        (other / "PrintExp_X64.exe").write_bytes(self.original)
        try:
            (self.root / "linked").symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(HostPatchError):
            apply_host_patch(self.root, "linked/PrintExp_X64.exe", self.sha, b"patched")


if __name__ == "__main__":
    unittest.main()
