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


## Embedded native-window Stage 1

The previous owned WS_POPUP overlays are now replaced with two WS_CHILD
windows parented directly to the PrintExp main frame. The 3D tab occupies
the same first-row navigation area as Vision. Selecting 3D displays its
embedded page below the original top navigation while preserving the
existing device/status bar. Selecting Print, Settings, Adjust, Vision or
another native navigation button hides the 3D child page and lets PrintExp
switch normally.

This is a **native Windows child-page extension**, but not yet an entry in
the vendor's proprietary MFC page-factory registration table. Its next step
is native navigation factory integration after the diagnostic control IDs
are verified. No printer/motion/UV controls are used by this Stage 1 page.
The old draggable-popup coordinates are ignored by this new native layout.


## Stage 1 native PrintExp page registration (experimental)

The earlier manually drawn 3D tabs have been **removed**. Static analysis of
the exact SHA-pinned vendor executable identified the internal routine used
when the built-in Vision page appears after initialization:
`PrintExp_X64.exe + 0x48530` (AddPage). The native list is held in
`CMainFrame+0x4CC0`, and the selected-page index in `CMainFrame+0x4CBC`.

The 3D DLL now attempts to call that same native AddPage function on
PrintExp's main UI thread, after Vision is initialized, using the vendor's
own CStringW initialization and translation functions. No direct binary patch
is necessary for this experiment. This differs from the earlier child-tab
overlay: the **tab itself must be created and selected by PrintExp**.

The module tries to wrap the 3D content HWND as a native MFC CWnd. When
the relevant MFC exports are unavailable, it can temporarily use Vision's
existing MFC page object as a registration placeholder while handling the
3D content separately. **That fallback is experimental and is not a complete
independent native MFC page implementation.**

This code has an exact-method signature guard and checks that PrintExp's
page-list length increases by exactly one. The launcher only reports the
3D page as ready after the actual native registration succeeds. It is not
safe or supported on other PrintExp versions.

Logs: `UV3DAddOn/diagnostics/native-page.log` (inside selected PrintExp).
If the native 3D tab fails to appear, this log describes whether MFC frame
lookup, Vision readiness, or native registration was the blocker.

No printer or motor functions are called. Use only on your isolated test
installation with the printer idle or disconnected.


## Offline development mode (no printer attached)

The original Gongzheng `Project.ini` documents `[PROJECT_CONFIG] PROJECT_MODE=0`
as **online** and `PROJECT_MODE=1` as **debug**. The executable itself reads
this setting. We do not spoof a printer, send commands to its controller, or
claim a connected machine when using debug mode.

The installer keeps a single main window and four buttons. When you click
**Launch PrintExp + 3D** with `PROJECT_MODE=0`, you are asked whether this
is a printer-free development computer. Choose **Yes** to enable the
manufacturer's debug setting and launch. Windows requests UAC because it is
changing a file inside the selected PrintExp installation. Choose **No** to
start with the ordinary online setting, or **Cancel** to abort.

`offline_profile.py` changes only the ASCII digit in
`<selected PrintExp>/Project.ini`, preserving all original encoding and
comments (including GBK Chinese text). It stores an SHA-verified byte-for-byte
backup in `<selected PrintExp>/UV3DAddOn/.host-patches/` and records the
transaction. This backup is **preserved across Update from main** and
restored during **Uninstall Add-on**. If the file changes unexpectedly,
the add-on refuses to overwrite it.

**Important:** `PROJECT_MODE=1` is a documented *debug* setting, not
a proven complete printer simulator. Depending on vendor startup logic,
some PrintExp pages or device functions may remain unavailable. The 3D
module no longer depends on Vision being registered or uses Vision's
CWnd as a fallback. It requires its own MFC wrapper to register safely.
If PrintExp exits or registration fails, the launcher now reports the actual
host-exit status and records details in
`UV3DAddOn/diagnostics/native-page.log` and `stage1.log`.

For a printer-connected copy, choose **No** and keep online mode. The
offline mode remains active for the selected test installation until you
restore its original configuration through **Uninstall Add-on**. A printer
must remain disconnected during experimental native-page development.


## Fresh Windows PC: required Microsoft 2010 x64 MFC runtime

`PrintExp_X64.exe` is built against `mfc100u.dll` (the Unicode Microsoft
Foundation Class library of Visual C++ 2010). The uploaded vendor directory
has `mfc100.dll`, but NOT `mfc100u.dll`. Windows must supply the x64
runtime before the program can even start. Having newer C++ Build Tools
does not install this legacy dependency.

The single-window installer detects it. When absent, **Launch PrintExp + 3D**
offers to download and install the Microsoft Visual C++ 2010 SP1 x64
Redistributable. The download is performed from WinGet's official Microsoft
package manifest when available, falling back to Microsoft's own
`download.microsoft.com` installer, with Authenticode validation.
Windows requests UAC before installing this **system-wide prerequisite**
(outside the selected PrintExp directory, unlike the add-on itself).

The installer verifies the presence of `mfc100u.dll` before launching
PrintExp. If the runtime is installed but the program still closes,
**hold Shift while clicking Launch PrintExp + 3D** to launch the original
PrintExp executable without any 3D DLL injection. This isolates native
PrintExp startup problems from experimental page-registration crashes.

For a fuller baseline diagnosis, run the built-in script (no printer required):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "UV3DAddOn\tools\Diagnose-PrintExpOffline.ps1" -PrintExpFolder "C:\Path\To\PrintExp" -LaunchBaseline
```

It writes `UV3DAddOn/diagnostics/offline-startup-report.txt` under the
selected installation. If original PrintExp remains running it leaves it
alone; if it exits, the script records the exit code and related Windows
Application Error events. It does not modify the original EXE, issue
printer commands or simulate a connected controller. Only start with
`-LaunchBaseline` when PrintExp is not already running.


## Simulate machine connection (experimental, offline development PC)

The **single-window launcher** now includes the checkbox
**Simulate machine connection (offline test)**. When enabled, Launch requests
administrator permission to change the selected test copy's `Project.ini`.
The backed-up original is preserved inside
`UV3DAddOn/.host-patches/`. It changes `PROJECT_MODE` to debug and the
controller TCP/PLC IP settings to **127.0.0.1**, keeping the port at **5001**.
Uncheck simulation and Launch to restore the original settings with UAC; the
regular Uninstall button restores the exact original bytes as well.

A locally hosted Python controller listens on **127.0.0.1:5001 TCP and UDP**
and launches the experimental native 3D PrintExp loader. It never forwards
anything to a physical controller. Incoming requests and the simulator's
response decisions are written in hex to:

`<selected PrintExp folder>/UV3DAddOn/diagnostics/simulated-controller.ndjson`

**Current limitation:** This is currently a loopback transport simulator, NOT
a fully emulated Hoson mainboard. PrintExp can require firmware responses to
its startup handshake. Those message formats and expected values have not
been captured from the actual machine. An accepted TCP connection alone may
therefore **not** make PrintExp fully initialize. This is not a successful
machine simulation until PrintExp actually completes startup on the
disconnected PC. If no requests arrive in the log, PrintExp may be reading an
additional device profile or may be stopping before the network connection.

A future validated response profile can be stored at:

`UV3DAddOn/config/simulated-controller-rules.json`

Its format matches
`config/simulated-controller-rules.example.json`:

```json
{"rules":[{"transport":"tcp","request_prefix_hex":"<verified hex>",
           "response_hex":"<verified controller response>"}]}
```

Only use packets verified from your actual controller capture. The default
contains no reply rules and intentionally does not invent firmware responses.
Run this **only on a physically disconnected development PC** until all
device profiles and network paths have been reviewed. The manufacturer's
configuration modules may specify other controller addresses independently
of `Project.ini`; the add-on has not proven that all network paths are
contained.

On startup failures, save the `simulated-controller.ndjson`,
`native-page.log` and `stage1.log` files. They distinguish transport
connection, missing protocol replies, native UI registration, and PrintExp
startup failures. Printing and motion controls remain disabled in our page.
