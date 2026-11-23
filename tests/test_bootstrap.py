"""Portable repository checks for the bootstrap entrypoint.

Actual automatic installer execution is a Windows-only end-to-end test.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapContractTests(unittest.TestCase):
    def test_entrypoint_has_no_python_or_git_prerequisite(self):
        start = (ROOT / "Start-Installer.cmd").read_text(encoding="utf-8")
        self.assertIn("Bootstrap-Installer.ps1", start)
        self.assertIn("powershell.exe", start)
        self.assertNotIn("where py", start)
        self.assertNotIn("where git", start)

    def test_bootstrap_checks_then_downloads_missing_deps(self):
        text = (ROOT / "Bootstrap-Installer.ps1").read_text(encoding="utf-8")
        for required in ("Resolve-Python", "Resolve-Git", "Resolve-Compiler", "Resolve-Winget",
                         "Python.Python.3.13", "Git.Git", "Install-PythonFallback",
                         "Install-GitFallback", "Install-Compiler", "Get-AuthenticodeSignature",
                         "Get-FileHash", "Install missing tools", "BuildToolsCheckbox",
                         "CheckOnly", "installer.py"):
            self.assertIn(required, text)
        self.assertIn("https://www.python.org/ftp/python/3.13.14/", text)
        self.assertIn("https://aka.ms/vs/17/release/vs_BuildTools.exe", text)

    def test_native_build_can_find_custom_compiler_path(self):
        script = (ROOT / "Build-Native.cmd").read_text(encoding="utf-8")
        self.assertIn("vswhere.exe", script)
        self.assertIn("vcvars64.bat", script)


if __name__ == "__main__":
    unittest.main()
