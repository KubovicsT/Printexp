import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addon_manager_core import (ADDON_DIR, LAUNCHER_NAME, InstallationError,
                                install_or_update, uninstall, validate_target,
                                verify_installed_files)


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

    def test_update_rebuilds_managed_directory_even_on_same_commit(self):
        self.run_install()
        first_stat = (self.vendor / ADDON_DIR).stat()
        first_head = subprocess.check_output(
            ["git", "-C", str(self.vendor / ADDON_DIR), "rev-parse", "HEAD"], text=True
        ).strip()
        second_head = self.run_install()
        self.assertEqual(first_head, second_head)
        self.assertNotEqual(first_stat.st_ino, (self.vendor / ADDON_DIR).stat().st_ino)
        self.assertEqual([], list(self.vendor.glob(ADDON_DIR + ".backup-*")))
        self.assertEqual([], list(self.vendor.glob(ADDON_DIR + ".staging-*")))

    def test_detached_python_worker_can_replace_installed_addon(self):
        """Real subprocess runs from outside the folder being renamed."""
        import shutil
        self.run_install()
        original = (self.vendor / ADDON_DIR / ".uv3d-managed-install.json").read_bytes()
        with tempfile.TemporaryDirectory(prefix="uv3d-detached-worker-test-") as location:
            stage = Path(location)
            for filename in ("addon_manager_core.py", "host_backup.py"):
                shutil.copy2(Path(__file__).resolve().parents[1] / filename,
                             stage / filename)
            code = (
                "from pathlib import Path; "
                "from addon_manager_core import install_or_update; "
                "import sys; "
                "install_or_update(Path(sys.argv[1]), "
                "repo_url=sys.argv[2], expected_sha=sys.argv[3], log=lambda *_: None)"
            )
            result = subprocess.run(
                [sys.executable, "-c", code,
                 str(self.vendor), str(self.repo), self.expected],
                cwd=stage, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + "\\n" + result.stderr)
        self.assertEqual(original,
                         (self.vendor / ADDON_DIR / ".uv3d-managed-install.json").read_bytes())
        self.assertEqual([], list(self.vendor.glob(ADDON_DIR + ".backup-*")))
        self.assertEqual([], list(self.vendor.glob(ADDON_DIR + ".staging-*")))

    def test_update_failure_restores_previous_version(self):
        self.run_install()
        original_launcher = (self.vendor / LAUNCHER_NAME).read_bytes()
        original_head = subprocess.check_output(
            ["git", "-C", str(self.vendor / ADDON_DIR), "rev-parse", "HEAD"], text=True
        ).strip()
        from addon_manager_core import write_launcher_bytes
        failed_once = False
        def fail_at_final_launcher_write(path, data):
            nonlocal failed_once
            # The helper only writes our managed launch script. On Windows,
            # TemporaryDirectory may use a reparse point so resolved and
            # unresolved paths need not compare equal.
            if not failed_once:
                failed_once = True
                raise PermissionError("simulated blocked launcher write")
            return write_launcher_bytes(path, data)
        with patch("addon_manager_core.write_launcher_bytes", side_effect=fail_at_final_launcher_write):
            with self.assertRaises(InstallationError):
                self.run_install()
        self.assertTrue(failed_once)
        self.assertEqual((self.vendor / LAUNCHER_NAME).read_bytes(), original_launcher)
        self.assertEqual(subprocess.check_output(
            ["git", "-C", str(self.vendor / ADDON_DIR), "rev-parse", "HEAD"], text=True
        ).strip(), original_head)
        self.assertEqual([], list(self.vendor.glob(ADDON_DIR + ".staging-*")))

    def test_post_install_verification_accepts_complete_files(self):
        head = self.run_install()
        self.assertIsNone(verify_installed_files(
            self.vendor, self.repo, head, self.expected, log=lambda _: None))

    def test_post_install_verification_detects_missing_binary(self):
        head = self.run_install()
        (self.vendor / ADDON_DIR / "dist" / "windows" / "UV3DPage.dll").unlink()
        with self.assertRaisesRegex(InstallationError, "missing required file"):
            verify_installed_files(self.vendor, self.repo, head, self.expected, log=lambda _: None)

    def test_post_install_verification_detects_modified_binary(self):
        head = self.run_install()
        (self.vendor / ADDON_DIR / "dist" / "windows" / "PrintExp3DLauncher.exe").write_bytes(b"damaged")
        with self.assertRaisesRegex(InstallationError, "corrupted or empty file"):
            verify_installed_files(self.vendor, self.repo, head, self.expected, log=lambda _: None)

    def test_post_install_verification_detects_missing_launcher(self):
        head = self.run_install()
        (self.vendor / LAUNCHER_NAME).unlink()
        with self.assertRaisesRegex(InstallationError, "launch script is missing"):
            verify_installed_files(self.vendor, self.repo, head, self.expected, log=lambda _: None)

    def test_update_verification_failure_rolls_back(self):
        self.run_install()
        original_launcher = (self.vendor / LAUNCHER_NAME).read_bytes()
        original_head = subprocess.check_output(
            ["git", "-C", str(self.vendor / ADDON_DIR), "rev-parse", "HEAD"], text=True
        ).strip()
        with patch("addon_manager_core.verify_installed_files", side_effect=InstallationError("deliberate verification failure")):
            with self.assertRaisesRegex(InstallationError, "previous version restored"):
                self.run_install()
        self.assertEqual((self.vendor / LAUNCHER_NAME).read_bytes(), original_launcher)
        self.assertEqual(subprocess.check_output(
            ["git", "-C", str(self.vendor / ADDON_DIR), "rev-parse", "HEAD"], text=True
        ).strip(), original_head)

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
