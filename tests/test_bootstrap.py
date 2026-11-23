"""Portable static checks; actual Windows UAC/GUI needs an on-machine test."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SingleWindowContractTests(unittest.TestCase):
    def test_starts_one_powershell_window_without_python(self):
        start = (ROOT / "Start-Installer.cmd").read_text()
        vbs = (ROOT / "Start-Installer.vbs").read_text()
        self.assertIn("wscript.exe", start)
        self.assertIn("Bootstrap-Installer.ps1", vbs)
        self.assertNotIn("installer.py", vbs)
        self.assertNotIn("installer.py", start)

    def test_exactly_four_primary_actions_and_no_extra_gui(self):
        text = (ROOT / "Bootstrap-Installer.ps1").read_text()
        self.assertIn("Install Add-on", text)
        self.assertIn("Update from main", text)
        self.assertIn("Uninstall Add-on", text)
        self.assertIn("Launch PrintExp + 3D", text)
        for name in ("InstallButton", "UpdateButton", "UninstallButton", "LaunchButton"):
            self.assertIn(name, text)
        self.assertNotIn("Prepare the PrintExp 3D Installer", text)
        self.assertNotIn("Open Installer", text)
        self.assertNotIn("Install missing tools and open installer", text)
        self.assertFalse((ROOT / "installer.py").exists())
        self.assertEqual(text.count("$form.ShowDialog()"), 1)

    def test_all_mutations_request_uac_and_worker_checks_admin(self):
        text = (ROOT / "Bootstrap-Installer.ps1").read_text()
        self.assertIn("-Verb RunAs", text)
        self.assertIn("Test-Administrator", text)
        for action in ("install", "update", "uninstall"):
            self.assertIn(f"Begin-Modification '{action}'", text)
        self.assertIn('UAC is requested on EVERY modification', text)
        self.assertIn("-WindowStyle Hidden", text)

    def test_remembers_print_exp_folder(self):
        text = (ROOT / "Bootstrap-Installer.ps1").read_text()
        self.assertIn("selected-install.txt", text)
        self.assertIn("Read-Selection", text)
        self.assertIn("Save-Selection", text)
        self.assertIn("Add_FormClosing", text)

    def test_dependencies_still_auto_installed(self):
        text = (ROOT / "Bootstrap-Installer.ps1").read_text()
        for key in ("Ensure-Python", "Ensure-Git", "Ensure-CompilerIfNeeded", "Install-PythonFallback",
                    "Install-GitFallback", "Install-Compiler", "Get-AuthenticodeSignature", "Get-FileHash"):
            self.assertIn(key, text)

    def test_native_build_can_find_compiler(self):
        text = (ROOT / "Build-Native.cmd").read_text()
        self.assertIn("vswhere.exe", text)
        self.assertIn("vcvars64.bat", text)


if __name__ == "__main__":
    unittest.main()
