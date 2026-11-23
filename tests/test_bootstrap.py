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

    def test_update_can_repair_old_admin_only_addon_permissions(self):
        bootstrap = (ROOT / "Bootstrap-Installer.ps1").read_text()
        core = (ROOT / "addon_manager_core.py").read_text()
        self.assertNotIn("The add-on is not installed. Use Install Add-on first.", bootstrap)
        self.assertIn("shutil.copytree(staged, addon)", core)
        self.assertIn("shutil.copytree(staged, candidate)", core)
        self.assertNotIn("shutil.move(str(staged), str(addon))", core)
        self.assertIn("Get-SelectedFolder", bootstrap)
        self.assertIn("-Verb RunAs", bootstrap)
        self.assertIn("Start-Process -FilePath $native", bootstrap)

    def test_install_and_update_have_non_elevated_final_file_check(self):
        ui = (ROOT / "Bootstrap-Installer.ps1").read_text()
        core = (ROOT / "addon_manager_core.py").read_text()
        self.assertIn("Test-UserCanReadInstalledFiles", ui)
        self.assertIn("Post-install verification passed", ui)
        self.assertIn("Get-FileHash -LiteralPath $path", ui)
        self.assertIn("verify_installed_files(target, staged, commit, expected_sha, log=log)", core)

    def test_stage1_launcher_requests_elevation_for_protected_printexp(self):
        launcher = (ROOT / "src" / "native" / "Stage1Launcher.cpp").read_text(encoding="utf-8")
        for required in ("ERROR_ELEVATION_REQUIRED", "ERROR_ACCESS_DENIED", "ShellExecuteExW",
                         'info.lpVerb = L"runas"', "--elevated", "alreadyTriedElevation"):
            self.assertIn(required, launcher)
        self.assertIn("if (!alreadyTriedElevation &&", launcher)

    def test_stage1_targets_exact_message_window_and_owned_overlay(self):
        page = (ROOT / "src" / "native" / "Stage1Page.cpp").read_text(encoding="utf-8")
        launcher = (ROOT / "src" / "native" / "Stage1Launcher.cpp").read_text(encoding="utf-8")
        self.assertIn("Create3DPage(msg->hwnd)", page)
        self.assertIn("msg->message == WM_NULL", page)
        self.assertIn("WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE", page)
        self.assertIn("WS_POPUP | WS_VISIBLE", page)
        self.assertIn("ClientToScreen(g_host, &origin)", page)
        self.assertIn("stableSince", launcher)
        self.assertIn("diagnostics", page)
        self.assertIn("diagnostics", launcher)

    def test_vision_anchor_and_saved_draggable_position(self):
        page = (ROOT / "src" / "native" / "Stage1Page.cpp").read_text(encoding="utf-8")
        cfg = (ROOT / "config" / "stage1.ini").read_text(encoding="utf-8")
        for name in ("FindVisionControl", "EnumChildWindows",
                     "SetTimer(g_host", "kRepositionTimer", "WM_MOUSEMOVE",
                     "SaveTabLocation", "WritePrivateProfileStringW",
                     "fallback_tab_x"):
            self.assertIn(name, page)
        self.assertIn("tab_x=-1", cfg)

    def test_native_build_can_find_compiler(self):
        text = (ROOT / "Build-Native.cmd").read_text()
        self.assertIn("vswhere.exe", text)
        self.assertIn("vcvars64.bat", text)


if __name__ == "__main__":
    unittest.main()
