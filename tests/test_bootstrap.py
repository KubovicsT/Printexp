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

    def test_launcher_prefers_updated_manager_in_selected_installation(self):
        vbs = (ROOT / "Start-Installer.vbs").read_text(encoding="utf-8")
        ui = (ROOT / "Bootstrap-Installer.ps1").read_text(encoding="utf-8")
        for expected in ("selected-install.txt", "UV3DAddOn", ".uv3d-managed-install.json",
                         "Bootstrap-Installer.ps1", "PrintExp_X64.exe"):
            self.assertIn(expected, vbs)
        self.assertIn("Opening the updated add-on manager", ui)
        self.assertIn("UV3DAddOn\\Start-Installer.vbs", ui)
        self.assertIn("$form.ClientSize", ui)
        self.assertIn("$form.AutoScroll = $true", ui)
        self.assertIn("$script:SimulationCheck.BringToFront()", ui)

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

    def test_fresh_pc_without_saved_folder_can_open_browse_dialog(self):
        bootstrap = (ROOT / "Bootstrap-Installer.ps1").read_text(encoding="utf-8")
        self.assertIn("function Test-ExistingDirectory", bootstrap)
        self.assertIn("[string]::IsNullOrWhiteSpace($Path)", bootstrap)
        self.assertIn("if (Test-ExistingDirectory $previousSelection)", bootstrap)
        self.assertIn("if (Test-ExistingDirectory '') { throw", bootstrap)
        self.assertNotIn("Test-Path -LiteralPath $script:FolderInput.Text", bootstrap)

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

    def test_loopback_simulation_is_ui_opt_in_and_UAC_guarded(self):
        ui = (ROOT / "Bootstrap-Installer.ps1").read_text(encoding="utf-8")
        actions = (ROOT / "addon_action.py").read_text(encoding="utf-8")
        source = (ROOT / "simulated_controller.py").read_text(encoding="utf-8")
        profile = (ROOT / "simulation_profile.py").read_text(encoding="utf-8")
        for keyword in ("Simulate machine connection", "simulate-enable",
                        "simulate-disable", "Start-SimulatedPrintExp",
                        "Begin-Modification 'simulate-enable'", "127.0.0.1"):
            self.assertIn(keyword,ui)
        self.assertIn("ensure_not_running()",actions)
        self.assertIn("enable_simulation(folder)",actions)
        self.assertIn("HOST = \"127.0.0.1\"",source)
        self.assertIn('PORT = 5001',source)
        self.assertIn('unsupported_request_no_response',source)
        self.assertIn('restore_host_patches',profile)

    def test_legacy_visual_cpp_2010_mfc_runtime_bootstrap(self):
        bootstrap = (ROOT / "Bootstrap-Installer.ps1").read_text(encoding="utf-8")
        for required in ("mfc100u.dll", "Microsoft.VCRedist.2010.x64",
                         "Test-VC2010X64Runtime", "Ensure-VC2010X64Runtime",
                         "vc2010-install", "Confirm-Authenticode $download 'Microsoft Corporation'",
                         "Begin-Modification 'vc2010-install'"):
            self.assertIn(required, bootstrap)
        self.assertIn("Start-NativePrintExp $folder -NoAddon:$baseline", bootstrap)
        self.assertIn("ModifierKeys", bootstrap)
        self.assertIn("VC2010_x64=",bootstrap)

    def test_offline_mode_is_reversible_and_does_not_depend_on_vision(self):
        script = (ROOT / "offline_profile.py").read_text(encoding="utf-8")
        ui = (ROOT / "Bootstrap-Installer.ps1").read_text(encoding="utf-8")
        page = (ROOT / "src" / "native" / "Stage1Page.cpp").read_text(encoding="utf-8")
        action = (ROOT / "addon_action.py").read_text(encoding="utf-8")
        for token in ("PROJECT_MODE", "apply_host_patch", "restore_host_patches"):
            self.assertIn(token,script)
        self.assertIn("offline-enable", ui)
        self.assertIn("Begin-Modification 'offline-enable'", ui)
        self.assertIn("offline-disable", action)
        self.assertIn("SafePageCount(frame,image,&count)", page)
        self.assertNotIn("Waiting for PrintExp to register Vision first", page)
        self.assertNotIn("nativePage = visionWnd", page)

    def test_stage1_launcher_requests_elevation_for_protected_printexp(self):
        launcher = (ROOT / "src" / "native" / "Stage1Launcher.cpp").read_text(encoding="utf-8")
        for required in ("ERROR_ELEVATION_REQUIRED", "ERROR_ACCESS_DENIED", "ShellExecuteExW",
                         'info.lpVerb = L"runas"', "--elevated", "alreadyTriedElevation"):
            self.assertIn(required, launcher)
        self.assertIn("if (!alreadyTriedElevation &&", launcher)

    def test_uses_the_native_print_exp_page_registry(self):
        page = (ROOT / "src" / "native" / "Stage1Page.cpp").read_text(encoding="utf-8")
        launcher = (ROOT / "src" / "native" / "Stage1Launcher.cpp").read_text(encoding="utf-8")
        for keyword in ("NativeAddPage", "TryNativePageRegistration",
                        "image+0x48530", "image+0x340c0", "image+0x11490",
                        "mfc100u.dll", "g_nativeIndex", "g_frame",
                        "native AddPage registered 3D"):
            self.assertIn(keyword, page)
        self.assertIn("msg->message==WM_NULL", page)
        self.assertIn("stableSince", launcher)
        self.assertNotIn('kTabClass',page)
        self.assertNotIn("WS_POPUP",page)
        self.assertNotIn("WS_CHILD|WS_VISIBLE",page)

    def test_native_3d_page_only_runs_ui_operations(self):
        page = (ROOT / "src" / "native" / "Stage1Page.cpp").read_text(encoding="utf-8")
        self.assertIn("Printing, Z-axis motion and UV lamp commands are disabled",page)
        self.assertIn("SetWindowSubclass",page)
        self.assertIn("PrintExp native AddPage",page)
        self.assertNotIn("motor_run",page)
        self.assertNotIn("PrintModule.dll",page)

    def test_native_build_can_find_compiler(self):
        text = (ROOT / "Build-Native.cmd").read_text()
        self.assertIn("vswhere.exe", text)
        self.assertIn("vcvars64.bat", text)


if __name__ == "__main__":
    unittest.main()
