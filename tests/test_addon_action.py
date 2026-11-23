from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

from addon_action import run_action
from addon_manager_core import InstallationError


class ActionTests(unittest.TestCase):
    def test_install_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('addon_action.install_or_update', return_value='abcdef01234') as fn:
                run_action('install', Path(temp), log=lambda _:None)
                fn.assert_called_once()

    def test_update_rejects_uninstalled(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(InstallationError):
                run_action('update', Path(temp), log=lambda _:None)

    def test_update_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            marker = folder / 'UV3DAddOn' / '.uv3d-managed-install.json'
            marker.parent.mkdir()
            marker.write_text('{}')
            with patch('addon_action.install_or_update', return_value='abcdef01234') as fn:
                run_action('update', folder, log=lambda _:None)
                fn.assert_called_once()

    def test_uninstall_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('addon_action.uninstall') as fn:
                run_action('uninstall', Path(temp), log=lambda _:None)
                fn.assert_called_once()


if __name__=='__main__':
    unittest.main()
