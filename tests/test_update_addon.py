import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
from addon_manager_core import InstallationError
from update_addon import update_existing, main


class UpdateTests(unittest.TestCase):
    def test_uninstalled_folder_is_not_updated(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("update_addon.install_or_update") as command:
                with self.assertRaises(InstallationError):
                    update_existing(Path(temp))
                command.assert_not_called()

    def test_marker_installed_calls_existing_update_function(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "UV3DAddOn" / ".uv3d-managed-install.json"
            marker.parent.mkdir()
            marker.write_text("{}")
            with patch("update_addon.install_or_update", return_value="abcd1234") as command:
                self.assertEqual(update_existing(Path(temp)), "abcd1234")
                command.assert_called_once()

    def test_cli_exits_with_error_and_logs_if_not_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target"
            target.mkdir()
            log = Path(temp) / "test.log"
            self.assertNotEqual(main(["--target", str(target), "--log-file", str(log)]), 0)
            self.assertIn("ERROR:", log.read_text())

    def test_cli_success_writes_short_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "test.log"
            with patch("update_addon.update_existing", return_value="abcdef0123456789"):
                self.assertEqual(main(["--target", temp, "--log-file", str(log)]), 0)
            self.assertIn("SUCCESS: add-on updated to abcdef012345", log.read_text())


if __name__ == "__main__":
    unittest.main()
