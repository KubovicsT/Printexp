# PrintExp 3D Add-on — Stage 1 (experimental)

A **single Windows add-on manager** for the inspected Gongzheng PrintExp build. Stage 1 tests an experimental 3D page in the existing PrintExp process. It does not yet control printing, Z motion, UV lamps or ink delivery.

## Open the one-window installer

Double-click `Start-Installer.vbs` (recommended; no console) or `Start-Installer.cmd`. This runs Windows' built-in PowerShell 5.1 and **does not require Python, Git or Visual Studio beforehand**.

There is just one user-facing management window:

- **PrintExp installation folder** with a Browse button, remembered in `%LOCALAPPDATA%\PrintExp3DAddOn\selected-install.txt`.
- **Install Add-on** — fetches `main` (no GitHub releases), installs any missing Python/Git/C++ Build Tools, builds native binaries when needed and installs only our add-on files.
- **Update from main** — downloads the latest `main` into a temporary workspace, creates a replacement add-on directory with normal PrintExp-inherited permissions, and swaps it in with rollback protection. This also repairs the older installer version that retained administrator-only permissions.
- **Uninstall Add-on** — removes only the managed add-on folder and checksum-verified launcher.
- **Launch PrintExp + 3D** — runs the Stage 1 experimental page. If Windows requires elevation for PrintExp, the native launcher requests UAC approval and relaunches itself elevated before attempting the UI hook.

**Install, Update and Uninstall always display the standard Windows UAC administrator prompt, before any PrintExp modification.** The original manager window stays open; the elevated worker runs with its console hidden, and reports completion in that window. If permission is denied, no change is attempted. The manager retains the last selected folder between runs. The operation log is saved to `%LOCALAPPDATA%\PrintExp3DAddOn\last-operation.log`.

If Python or Git is missing, they are downloaded via WinGet or signed official installers. If the native x64 components are not prebuilt and no compiler is found, the Microsoft C++ Build Tools are installed automatically (a large download; when `X:` is available this is the preferred location). Dependencies are checked only when needed for Install or Update, not before showing the UI. Uninstall needs Python but not Git or compiler.

GitHub is a **private repository**; Git Credential Manager may require your GitHub sign-in, even after UAC. Changing to a different administrator account can require a separate sign-in.

## Fix for the earlier "Access is denied" installation

The earlier installer moved the Git checkout straight from the elevated user's `%TEMP%` directory into `Program Files (x86)`. On the same Windows drive this can preserve the source directory's restrictive access permissions, leaving the normal user unable to execute `UV3DAddOn\dist\windows\PrintExp3DLauncher.exe` or read/update parts of the add-on.

**After every Install and Update, verification is mandatory before success is reported.** The elevated worker checks all tracked source files, the two compiled Windows binaries, Git revision, managed installation marker and launch script, including SHA-256 checksums. A missing/corrupt file causes installation failure or update rollback. After UAC, the normal-user window independently reads/checks the critical files to detect administrator-only access permissions. Only a complete, readable installation reports success. A failed normal-user access check leaves the files in place for diagnosis rather than silently calling it successful.

The installer now **copies** the checkout into a newly created folder under PrintExp, causing Windows to inherit that location's normal ACLs instead. **Update from main always builds a fresh folder and swaps it in, even if the Git commit has not changed**, so it can repair an already installed add-on. It preserves the old add-on until the replacement has passed verification, rolls back if the swap fails, and does not modify the original PrintExp executable or vendor DLLs. The manager no longer checks the old install marker without permission before showing the UAC prompt.

To recover from the old build: close PrintExp, download the current installer ZIP, open `Start-Installer.vbs`, and click **Update from main**. If update still fails, the existing managed directory is left in place. The status message and `%LOCALAPPDATA%\PrintExp3DAddOn\last-operation.log` can be used to identify where Windows denied access. Do not change global Windows security settings or disable antivirus protections to make an injected tab work.

If PrintExp refuses to start because of elevation, the native launcher requests administrator approval through standard Windows UAC, then starts PrintExp and its UI hook with matching permissions. The original PrintExp binary contains `requestedExecutionLevel level="highestAvailable"`. If process launch or hooking still fails after UAC, the launcher reports the actual **Win32 error code**. Do not disable Windows security protections to force the hook.

## Supported PrintExp version and safety

- Vendor executable: `PrintExp_X64.exe`, **GongZhong_V5.7.9.4.60.ADV_U_LSSD_20251027**.
- Required host SHA-256: `af1dbed5532ff4262fcc4d38e288940ece3c9f45ab1e803230d85e6092bbacf1`.
- Existing vendor executable/DLLs are never replaced. Only `UV3DAddOn/` and `Start PrintExp with 3D.cmd` are created/removed.
- Stop all printing and preferably disconnect the machine before testing. The Stage 1 UI loads via an experimental targeted Windows message hook and has **not been validated on hardware**. It is not an official PrintExp plugin API.
- Do not bypass executable-version validation.

## Files

```text
Start-Installer.vbs           Silent entry point: opens a single manager window
Start-Installer.cmd           Command-line entry point to the same manager
Bootstrap-Installer.ps1      One-window UI, dependency bootstrap and elevated worker
addon_action.py              Headless Install/Update/Uninstall command handler
addon_manager_core.py        Validated Git checkout, install, update, uninstall logic
Build-Native.cmd             Windows x64 MSVC build (if no prebuilt binaries)
src/native/                  Stage 1 native tab and launcher
.github/workflows/           Windows x64 build workflow
tests/                       Portable unit and contract tests
```

## Testing

```powershell
python -m unittest discover -s tests -v
```

These tests do not reproduce the actual Windows UAC flow or prove that the native tab will appear. Confirm behavior on the target Windows PC before proceeding to printer-control integration.


## Stage 1 visibility diagnostics

The experimental 3D control now uses a small **owned popup overlay** (inside the
PrintExp process, attached to its main window), rather than an MFC child control
that can be hidden beneath proprietary toolbar panes. It still does not register
a genuine native PrintExp page and is strictly a UI feasibility experiment.

The launcher waits for a stable main-frame candidate instead of immediately
choosing the first splash window, and the hook uses the **exact** HWND to which
the launcher posted its test message.

If PrintExp opens but the 3D tab remains invisible, close it and inspect:

`<PrintExp installation>/UV3DAddOn/diagnostics/stage1.log`

The log identifies the chosen host window, attempted UI construction, and
whether the tab was created and marked visible. It contains no printer commands.
This is a read-only UI test; do not run it during active printing.


## Vision tab and position calibration

The original PrintExp application already has a built-in page called
`PageVisionPrint` and the uploaded `Project.ini` enables it with
`[VISION_PRINT] SUPPORT_VISION_PRINT=1`. Vision sometimes becomes visible
after startup. This is a compiled feature, not proof of a plugin-registration
interface.

The experimental 3D tab polls the navigation area after startup. When the
Vision button exposes a discoverable Windows title, the 3D tab is placed
immediately **to the right of Vision**. If the vendor uses a custom-drawn
button, 3D uses the fallback location in `config/stage1.ini`.

To position the tab precisely in the marked slot, **drag the visible 3D
tab**. The selection is saved to `config/local-stage1.ini` in the managed
add-on directory and reused on subsequent launches. Delete that local file
to restore automatic alignment. No original PrintExp configuration is changed.

This remains a Stage 1 owned UI overlay. It has not yet been registered
as a true native MFC top-level page.

## Experimental native-page host patches (not activated yet)

The original PrintExp main executable hardcodes the native navigation page
names (`PageTask`, `PagePrint`, `PageSetting`, `PageAdjust`,
`PageVoltage`, `PageAdvance`, `PageVisionPrint` and others). A true native
MFC page requires verified integration with both the navigation and its
page-switching/factory code. The current UI is an in-process overlay; **no
vendor executable patch has been enabled yet**.

`host_backup.py` is a **disabled-by-default** host patch transaction layer for
that work. Every authorized change must verify the exact baseline SHA-256,
store the original bytes and manifest in
`<selected PrintExp folder>/UV3DAddOn/.host-patches/`, and verify the patched
result. Future updates preserve this backup. Uninstall restores patched host
files first, refuses unknown external changes, and only then deletes the add-on.

This containment applies to PrintExp file modifications and in-folder backups.
**The current Windows bootstrap still uses Windows temporary directories,
downloads optional machine-wide dependencies, and saves the path in
`%LOCALAPPDATA%`. It therefore does NOT yet satisfy a literal
"zero writes outside the selected folder" requirement. A fully portable,
in-folder bootstrap will be necessary before claiming that.**

## Native-page investigation log

Stage 1 now records **read-only UI structure** at several points after PrintExp
launch and whenever 3D is selected. The log includes Windows control classes,
top-navigation control IDs, positions, visibility, and page navigation events.
These observations will be used to identify how PrintExp switches its built-in
pages. **No original vendor file is patched during this diagnostic stage.**

The diagnostic is stored exclusively in the selected PrintExp directory:

`<selected PrintExp folder>/UV3DAddOn/diagnostics/stage1.log`

After launching the experimental 3D page, click **Vision**, **Print**, and
**3D**, close PrintExp, and share that log. Do not connect printer hardware
while running these UI experiments.
