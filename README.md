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

## Installing

1. Ideally the **Build Windows x64 add-on (main)** GitHub Action will compile and commit the two native files. If GitHub Actions is unavailable, the installer can compile the native components locally using **free Microsoft Visual Studio 2022 Build Tools**, with **Desktop development with C++** installed. The installer explains this if the build cannot run.
2. Install **Python 3** and **Git for Windows** (Git Credential Manager recommended). Git needs access to this **private repository**. You may download this repository as ZIP only to bootstrap `Start-Installer.cmd`; the manager itself retrieves the latest branch using Git.
3. Run `Start-Installer.cmd` (or `python installer.py`). A real window will open.
4. Choose the folder containing `PrintExp_X64.exe` and `DeviceManager.dll`.
5. Click **Install**. The installer clones the latest `main` branch into `PrintExp/UV3DAddOn/` and creates `PrintExp/Start PrintExp with 3D.cmd`.
6. With the printer idle, use **Launch PrintExp + 3D** in the manager or run `Start PrintExp with 3D.cmd`. You should see a new `3D` tab near the top-right of the PrintExp window. Clicking it opens a Stage 1 test page; clicking again returns to the underlying PrintExp interface.
7. If the tab overlaps anything, adjust `UV3DAddOn/config/stage1.ini` (`tab_y` and `page_y`), then restart PrintExp using the 3D launcher. UI placement is provisional until verified on your exact screen layout.

**Important:** The launcher deliberately uses an **exact host executable checksum** and will not start an unsupported build. Stage 1 works on 64-bit Windows only. The third-party anti-virus or unequal process elevation levels can block Windows message hooking; if this happens, the launcher displays an error and leaves the vendor files untouched. In a failed attach, PrintExp may remain running without the new tab.

## Updates (no GitHub releases)

Click **Update from main** in the same manager window. The updater does a Git fetch followed by a fast-forward-only merge of `main`, updating the add-on source and compiled DLL/EXE in place. It refuses to update locally edited tracked files. `PrintExp_X64.exe` and other vendor files are never updated by this tool. Close PrintExp before updating.

The repository's Windows GitHub Action builds both native x64 components with MSVC and commits them back to **main** under `dist/windows/`. The script deliberately does not use GitHub releases. If the binaries are not yet on `main`, the manager attempts to compile them locally with MSVC before installing. It refuses a partial installation if no compiler is available.

## Uninstall

Close PrintExp and click **Uninstall**. Only the managed `UV3DAddOn/` directory and the checksum-verified `Start PrintExp with 3D.cmd` are removed. Since the installer never touches vendor files, original PrintExp is restored simply by removing the add-on. If someone edits the managed launcher, uninstall refuses to delete it; it never blindly removes unrelated files. Stage 1 stores no model or printer job data.

## Repository layout

```text
README.md
Start-Installer.cmd
Build-Native.cmd              local x64 build fallback (free MSVC Build Tools)
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
