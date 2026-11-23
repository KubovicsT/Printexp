import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addon_manager_core import (ADDON_DIR, LAUNCHER_NAME, InstallationError,
                                install_or_update, uninstall, validate_target)


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE)


@unittest.skipUnless(__import__("shutil").which("git"), "Git is required")
class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.vendor = root / "VendorPrintExp"
        self.vendor.mkdir()
        self.exe = self.vendor / "PrintExp_X64.exe"
        self.exe.write_bytes(b"safe fake vendor exe test only")
        (self.vendor / "DeviceManager.dll").write_bytes(b"original dll")
        self.expected = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        self.repo = root / "repo"
        self.repo.mkdir()
        git("init", "-b", "main", cwd=self.repo)
        git("config", "user.name", "Tests", cwd=self.repo)
        git("config", "user.email", "tests@example.invalid", cwd=self.repo)
        (self.repo / "dist" / "windows").mkdir(parents=True)
        (self.repo / "dist" / "windows" / "UV3DPage.dll").write_bytes(b"fake DLL")
        (self.repo / "dist" / "windows" / "PrintExp3DLauncher.exe").write_bytes(b"fake EXE")
        (self.repo / "readme.txt").write_text("version 1")
        git("add", ".", cwd=self.repo)
        git("commit", "-m", "initial", cwd=self.repo)

    def run_install(self):
        return install_or_update(self.vendor, log=lambda _: None,
                                 repo_url=str(self.repo), expected_sha=self.expected)

    def test_checkout_is_staged_outside_vendor_directory(self):
        original = tempfile.TemporaryDirectory
        dirs = []
        def capture_tempdir(*args, **kwargs):
            dirs.append(kwargs.get("dir"))
            return original(*args, **kwargs)
        with patch("addon_manager_core.tempfile.TemporaryDirectory", side_effect=capture_tempdir):
            self.run_install()
        self.assertIn(None, dirs)
        self.assertTrue((self.vendor / ADDON_DIR).is_dir())

    def test_permission_probe_detects_denied_access(self):
        from installer import target_requires_elevation
        with patch("installer.tempfile.TemporaryFile", side_effect=PermissionError("Access denied")):
            self.assertTrue(target_requires_elevation(self.vendor))

    def test_wrong_folder_rejected(self):
        with self.assertRaises(InstallationError):
            validate_target(self.repo, self.expected)

    def test_wrong_binary_refused(self):
        with self.assertRaises(InstallationError):
            validate_target(self.vendor)

    def test_install_update_uninstall_preserves_original_vendor_files(self):
        original = {f.name: f.read_bytes() for f in self.vendor.iterdir() if f.is_file()}
        initial = self.run_install()
        self.assertTrue((self.vendor / ADDON_DIR / "dist" / "windows" / "UV3DPage.dll").is_file())
        self.assertTrue((self.vendor / LAUNCHER_NAME).is_file())
        self.assertEqual(self.run_install(), initial)
        (self.repo / "readme.txt").write_text("version 2")
        git("add", ".", cwd=self.repo)
        git("commit", "-m", "version 2", cwd=self.repo)
        self.assertNotEqual(self.run_install(), initial)
        self.assertEqual((self.vendor / ADDON_DIR / "readme.txt").read_text(), "version 2")
        uninstall(self.vendor, log=lambda _: None)
        self.assertEqual({f.name: f.read_bytes() for f in self.vendor.iterdir() if f.is_file()}, original)
        self.assertFalse((self.vendor / ADDON_DIR).exists())

    def test_refuses_overwriting_user_file(self):
        (self.vendor / LAUNCHER_NAME).write_text("custom owner file")
        with self.assertRaises(InstallationError):
            self.run_install()
        self.assertEqual((self.vendor / LAUNCHER_NAME).read_text(), "custom owner file")

    def test_refuses_deleting_edited_launcher(self):
        self.run_install()
        (self.vendor / LAUNCHER_NAME).write_text("customized")
        with self.assertRaises(InstallationError):
            uninstall(self.vendor, log=lambda _: None)
        self.assertTrue((self.vendor / ADDON_DIR).exists())

    def test_refuses_unmarked_addon_directory(self):
        (self.vendor / ADDON_DIR).mkdir()
        (self.vendor / ADDON_DIR / "user.txt").write_text("don't delete me")
        with self.assertRaises(InstallationError):
            self.run_install()
        self.assertTrue((self.vendor / ADDON_DIR / "user.txt").is_file())

    def test_refuses_modified_addon_files(self):
        self.run_install()
        (self.vendor / ADDON_DIR / "readme.txt").write_text("locally edited")
        with self.assertRaises(InstallationError):
            self.run_install()

if __name__ == "__main__":
    unittest.main()
