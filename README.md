# PrintExp 3D Add-on — Stage 1 (experimental)

This repository contains a reversible add-on for the **specific** PrintExp installation inspected for the Gongzheng/UV3D project. The first milestone is a visual **3D** tab **inside the existing PrintExp window**. It deliberately has no printing, RIP, Z-axis, or UV-light control functionality.

**Status:** Source code and installer logic prepared; a genuine Windows x64 build and in-PrintExp runtime validation are required before declaring the new tab functional.

## Compatibility and safety

- Target executable: `PrintExp_X64.exe`, **GongZhong_V5.7.9.4.60.ADV_U_LSSD_20251027**.
- Exact host SHA-256: `af1dbed5532ff4262fcc4d38e288940ece3c9f45ab1e803230d85e6092bbacf1`.
- The installer and native launcher refuse mismatched executables. Do not bypass the check without investigating binary compatibility.
- **Never test while a print is active.** For the first launch, keep the printer idle, preferably disconnected. This is an unsupported integration technique and could make PrintExp unstable. An unexpected crash could interrupt printer operation.
- The vendor executable, driver DLLs, configuration, and machine control are not modified.
- The extension uses a targeted, thread-specific Windows `WH_GETMESSAGE` hook, loaded by the optional `PrintExp3DLauncher.exe`. Once the UI page is created, the native DLL is pinned in the PrintExp process until PrintExp exits. There is **no hidden persistent helper process** and no user-facing second application.
- No process memory patching or print/motion command code is included. The native hook is experimental; this is *not* a verified official PrintExp plug-in interface.
- The original PrintExp shortcut still launches unmodified PrintExp **without** the experimental 3D page. Launch using `Start PrintExp with 3D.cmd` for Stage 1.

## Installing (automatic dependency setup)

**Double-click `Start-Installer.cmd`.** Python, Git and Visual Studio C++ Build Tools **do not need to be installed beforehand**.

1. A Windows-native **Dependency Setup** window opens first, without requiring Python.
2. It checks Python 3 (including `tkinter`), Git for Windows, and whether compiled x64 page binaries or the Microsoft C++ compiler are present.
3. Click **Install missing tools and open installer**. Missing Python and Git are installed automatically through Windows Package Manager (`winget`), with signed official-installation fallbacks if WinGet is missing or fails. Existing installations are reused.
4. If the native x64 binaries are not included and no compiler is installed, the window offers **Microsoft Visual Studio 2022 C++ Build Tools**. This is a **large download**, may require an administrator prompt, and can be disabled if you don't want the toolchain. If disabled while needed, installation cannot proceed. On machines with an `X:` drive, the proposed Build Tools location is `X:\VisualStudioBuildTools` to avoid filling `C:`; you can change it before installing. Microsoft may still store shared installer components on `C:`.
5. The first window includes **Update from main**, and remembers the chosen PrintExp installation in `%LOCALAPPDATA%\\PrintExp3DAddOn\\selected-install.txt`. After dependencies are ready, the usual graphical PrintExp add-on installer opens automatically. Choose the folder containing `PrintExp_X64.exe` and `DeviceManager.dll`, then click **Install**. If Windows protects this folder (for example `C:\\Program Files (x86)\\`), the manager checks permission and requests elevation through the standard Windows UAC prompt **only for the add-on manager**. You do not need to run the whole dependency bootstrap as administrator.
6. The installer downloads and builds the latest **private** `main` branch in a writable Windows temporary directory, moves the finished add-on into `PrintExp/UV3DAddOn/`, and creates `PrintExp/Start PrintExp with 3D.cmd`. It never creates staging folders inside the vendor directory.
7. With the printer idle, preferably disconnected, click **Launch PrintExp + 3D**. You should see the Stage 1 test tab near the top-right of the existing PrintExp window.

If your GitHub account has not already been authenticated for Git, Git Credential Manager may prompt you to sign in through the browser to access this **private repository**. Dependency setup does not bypass GitHub permissions.

**Fallbacks and security:** WinGet verifies its package manifests; the direct Python.org fallback has a pinned publisher SHA-256 checksum and a checked Authenticode signature. The Git for Windows fallback is fetched from the project's official GitHub releases and its digital signature is verified. Build Tools are downloaded using Microsoft's official installer and verified as Microsoft-signed. The bootstrap never replaces or patches vendor PrintExp files. A reboot may be needed after installing some developer tools.

**Important:** The launcher deliberately uses an **exact host executable checksum** and will not start an unsupported build. Stage 1 works on 64-bit Windows only. Antivirus protections or process privilege differences can block the experimental Windows message hook. If that happens, PrintExp remains unmodified; it may stay open without the new page.

## Updates (no GitHub releases)

Click **Update from main** in the **first Dependency Setup window**. Choose the PrintExp folder there (the selection is remembered across launches), close PrintExp, and click Update. Python and Git are installed if missing. The update runs directly from this first window, requesting Windows administrator permission when needed. The updater does a Git fetch followed by a fast-forward-only merge of `main`, updating the add-on source and compiled DLL/EXE in place. It refuses to update locally edited tracked files. `PrintExp_X64.exe` and other vendor files are never updated by this tool. Close PrintExp before updating.

The repository's Windows GitHub Action builds both native x64 components with MSVC and commits them back to **main** under `dist/windows/`. The script deliberately does not use GitHub releases. If the binaries are not yet on `main`, the installer automatically builds them locally using the compiler installed during dependency setup.

## Uninstall

Close PrintExp and click **Uninstall**. Only the managed `UV3DAddOn/` directory and the checksum-verified `Start PrintExp with 3D.cmd` are removed. Since the installer never touches vendor files, original PrintExp is restored simply by removing the add-on. If someone edits the managed launcher, uninstall refuses to delete it; it never blindly removes unrelated files. Stage 1 stores no model or printer job data.

## Repository layout

```text
README.md
Start-Installer.cmd
Bootstrap-Installer.ps1         Native Windows dependency check/download UI
update_addon.py              First-window update command, without opening the installer GUI
installer.py                  Tkinter graphical manager
addon_manager_core.py        Git checkout, validation, update and uninstall
config/stage1.ini             provisional native tab position
src/native/Stage1Launcher.cpp  x64 launcher, checksum check and targeted hook
src/native/Stage1Page.cpp      injected, UI-only in-process tab and page
.github/workflows/windows-build.yml    Windows build, test and commit to main
tests/test_installer.py        installer/update/uninstall tests
dist/windows/                 produced by GitHub Actions, not in initial source commit
```

## Known limits — what Stage 1 proves

- The tab and its page are real Windows child windows hosted **inside PrintExp's process** via a loaded DLL. However, they are *not* registered with PrintExp's private MFC page/navigation manager, so the original page remains underneath when the test view is active. This is a deliberately constrained feasibility test, not the final integration mechanism.
- Navigation coordinates are preliminary, not derived from documented PrintExp APIs.
- Built-in printing functions, Z-axis motion, layer management, and in-memory PRN submission are **not implemented**.
- A validated official extension SDK or safe integration into the main MFC navigation would be the preferable next step once this first tab experiment is confirmed.
- Only tested local logic can be claimed to work until the Windows build passes and the user tests it on the supported installation.

## Developer tests

```powershell
python -m unittest discover -s tests -v
```

The tests use a temporary dummy vendor folder and a temporary Git repository. They never run PrintExp or use real printer DLLs.
