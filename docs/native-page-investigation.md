# PrintExp native 3D page investigation (read-only analysis)

## Host and scope

- Inspected vendor program: `PrintExp_X64.exe` from
  `GongZhong_V5.7.9.4.60.ADV_U_LSSD_20251027`.
- Original SHA-256: `af1dbed5532ff4262fcc4d38e288940ece3c9f45ab1e803230d85e6092bbacf1`.
- Windows PE32+ x64, Microsoft MFC 10 (`mfc100u.dll`).
- The user's **selected PrintExp installation is a disposable second copy**.
  Never patch or replace files in another PrintExp installation or shared
  operating-system printer drivers.
- Stage 1 currently uses a targeted `WH_GETMESSAGE` hook and an owned-popup
  window. **It does not participate in the vendor's native page-selection
  lifecycle**, so it must be replaced before calling Stage 1 complete.

## Direct evidence for compiled page registration

The inspected executable contains the UTF-16 strings

```text
PageTask
PagePrint
PageSetting
PageAdjust
PageVoltage
PageAdvance
PageVisionPrint
PageWaveEdit
PageLog
```

together in the PE `.rdata` section. A code block near virtual address
`0x140046B36` constructs an array of nine pointers to those page names in
stack offsets `0x20`–`0x60` for a page-resource lookup.

The executable also contains title-bar labels and `%s\MainFrame`,
`%s\PagePng\%s_Normal.png` and `%s\PagePng\%s_Active.png`, with separate
construction paths. The installed resources include
`PageVisionPrint_Normal.png` and `PageVisionPrint_Active.png`. The actual
application's Vision feature is controlled by
`Project.ini` section `[VISION_PRINT]` / `SUPPORT_VISION_PRINT`.

**IMPORTANT:** The above code block establishes only a compiled page-name
lookup. It is NOT yet confirmed to be the complete page factory or navigation
dispatcher. Appending a tenth entry to this fixed-size stack array is unsafe:
the surrounding stack has other variables. Blindly modifying those bytes can
crash the machine-control application.

## Required findings before an executable patch

1. From an actual Stage 1 run, inspect
   `UV3DAddOn/diagnostics/stage1.log` for top navigation window class,
   control ID, geometry, and page-container parent.
2. Exercise built-in **Print → Settings → Vision → Print**, then 3D.
   Check the logged `WM_COMMAND`/`WM_NOTIFY` navigation events.
3. Confirm whether the native navigation is exposed as a windowed
   `CXTabMenu` control or is completely owner-drawn inside the frame.
4. Identify the **page creation/registration** function and **page-switching**
   function separately. Prove the functions using the isolated test copy
   without connecting the printer.
5. Only then choose between a supported vendor module registration API
   and a SHA-pinned binary patch for inserting the genuine 3D page.
6. Verify automatic hiding/showing when selecting every original tab, correct
   resizing, focus, startup timing, reopening and shutdown behavior.

## Vendor patch transaction rules

Use `host_backup.py` for a future authorized patch. It stores original bytes
and a SHA manifest strictly under the selected installation:
`UV3DAddOn/.host-patches/`. `addon_manager_core.py` preserves those backups
during updates and restores them before uninstalling.

No executable patch is currently enabled, because the page factory and
dispatcher have not yet been verified. **Do not claim a native page was
installed while the visible UI is still an owned popup.**

## Caveat about absolute folder-only writes

The runtime **PrintExp modifications and host backups** are constrained to
the selected folder. The older bootstrap still uses Windows `%TEMP%` for
request handoff, `%LOCALAPPDATA%` to remember the installation path, and
(optionally) installs Python/Git/toolchain dependencies system-wide. This
must be redesigned for a literally self-contained portable installer.
A fully portable installer should locate its own installation by running
from within the selected folder and place its work directory and any tools
inside that folder.
