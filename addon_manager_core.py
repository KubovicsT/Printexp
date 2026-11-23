"""Transactional, version-pinned PrintExp add-on installer. No vendor files are modified."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

REPOSITORY = "https://github.com/KubovicsT/Printexp.git"
ADDON_DIR = "UV3DAddOn"
LAUNCHER_NAME = "Start PrintExp with 3D.cmd"
MARKER_NAME = ".uv3d-managed-install.json"
MARKER_VALUE = "printexp-uv3d-addon-v1"
SUPPORTED_EXE_SHA256 = "af1dbed5532ff4262fcc4d38e288940ece3c9f45ab1e803230d85e6092bbacf1"
BINARIES = ("PrintExp3DLauncher.exe", "UV3DPage.dll")
Log = Callable[[str], None]


class InstallationError(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(args: list[str], cwd: Path | None = None, log: Log = print) -> str:
    command = ["git", *args]
    result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8",
                            errors="replace", capture_output=True, check=False,
                            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
    if result.returncode:
        # Never show full Git remote output containing URLs with credentials.
        raise InstallationError(f"Git failed ({result.returncode}): {' '.join(args[:3])}. "
                                "Check Git installation, GitHub access and network connection.\n"
                                + (result.stderr or result.stdout)[-900:])
    if result.stdout.strip():
        log(result.stdout.strip()[-600:])
    return result.stdout.strip()


def validate_target(folder: Path, expected_sha: str = SUPPORTED_EXE_SHA256) -> Path:
    folder = Path(folder).expanduser().resolve()
    binary = folder / "PrintExp_X64.exe"
    if not binary.is_file():
        raise InstallationError("Select the directory containing PrintExp_X64.exe.")
    if not (folder / "DeviceManager.dll").is_file():
        raise InstallationError("This does not appear to be a complete PrintExp installation (DeviceManager.dll missing).")
    current = sha256(binary)
    if current != expected_sha:
        raise InstallationError("Unsupported PrintExp_X64.exe build. Stage 1 is pinned to the exact "
                                "GongZhong V5.7.9.4.60 build inspected for this project.\n"
                                f"Found SHA256: {current}\nExpected: {expected_sha}\n"
                                "The installer will not inject a DLL into an unverified version.")
    if folder.is_symlink():
        raise InstallationError("The PrintExp directory cannot be a symbolic link.")
    return folder


def ensure_not_running() -> None:
    if os.name != "nt":
        return
    result = subprocess.run(["tasklist", "/NH", "/FO", "CSV", "/FI", "IMAGENAME eq PrintExp_X64.exe"],
                            capture_output=True, text=True, errors="replace",
                            creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    if result.returncode == 0 and '"printexp_x64.exe"' in result.stdout.lower():
        raise InstallationError("Close PrintExp completely before installing, updating or uninstalling.")


def launcher_text() -> str:
    return ('@echo off\r\n'
            'setlocal\r\n'
            'cd /d "%~dp0"\r\n'
            '"%~dp0UV3DAddOn\\dist\\windows\\PrintExp3DLauncher.exe" "%~dp0PrintExp_X64.exe"\r\n'
            'if errorlevel 1 (\r\n'
            '  echo The PrintExp 3D page could not be loaded.\r\n'
            '  pause\r\n'
            ')\r\n')


def ensure_binaries(checkout: Path, log: Log = print) -> None:
    missing = [name for name in BINARIES
               if not (checkout / "dist" / "windows" / name).is_file()]
    if not missing:
        return
    log("No prebuilt Windows DLL/launcher on main. Trying a local MSVC build...")
    if os.name != "nt":
        raise InstallationError("No compiled Windows x64 binaries. GitHub Actions build must succeed first.")
    script = checkout / "Build-Native.cmd"
    if not script.is_file():
        raise InstallationError("No Windows binaries or local build script in the selected branch.")
    result = subprocess.run(["cmd.exe", "/d", "/c", str(script)], cwd=checkout,
                            text=True, encoding="utf-8", errors="replace", capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    if result.returncode:
        raise InstallationError("Cannot build the native page. Relaunch Start-Installer.cmd to set up "
                                "the free Microsoft C++ Build Tools, then retry.\n"
                                + (result.stdout + result.stderr)[-1800:])
    log((result.stdout + result.stderr)[-700:])
    remaining = [name for name in BINARIES
                 if not (checkout / "dist" / "windows" / name).is_file()]
    if remaining:
        raise InstallationError("Native build did not produce: " + ", ".join(remaining))


def source_marker(target: Path) -> Path:
    return target / ADDON_DIR / MARKER_NAME


def assert_managed(target: Path) -> dict:
    addon = target / ADDON_DIR
    marker = source_marker(target)
    if addon.is_symlink() or marker.is_symlink():
        raise InstallationError("Installation contains a symbolic link; refusing to modify it.")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallationError("No valid UV3D installation marker. Uninstall refused to protect existing files.") from exc
    if data.get("format") != MARKER_VALUE or data.get("repo") != REPOSITORY:
        raise InstallationError("Unexpected installation marker; refusing to modify files.")
    return data


def install_or_update(target: Path, log: Log = print, repo_url: str = REPOSITORY,
                      expected_sha: str = SUPPORTED_EXE_SHA256) -> str:
    target = Path(target).expanduser().resolve()
    validate_target(target, expected_sha)
    ensure_not_running()
    addon = target / ADDON_DIR
    entry = target / LAUNCHER_NAME
    if addon.exists():
        assert_managed(target)
        if not (addon / ".git").is_dir():
            raise InstallationError("The add-on Git checkout is missing. No files were changed.")
        if not entry.is_file():
            raise InstallationError("The add-on launcher is missing. No files were changed.")
        old = assert_managed(target)
        if sha256(entry) != old.get("launcher_sha256"):
            raise InstallationError("The launch script has been modified. Refusing to overwrite it.")
        remote = run_git(["-C", str(addon), "remote", "get-url", "origin"], log=lambda msg: None)
        if remote != repo_url:
            raise InstallationError("The add-on Git remote is different from the expected repository.")
        if run_git(["-C", str(addon), "status", "--porcelain", "--untracked-files=no"], log=lambda msg: None):
            raise InstallationError("Managed add-on files have local changes; commit or revert them before updating.")
        log("Fetching latest main branch (no releases)...")
        run_git(["-C", str(addon), "fetch", "origin", "main"], log=log)
        run_git(["-C", str(addon), "merge", "--ff-only", "FETCH_HEAD"], log=log)
        ensure_binaries(addon, log=log)
        commit = run_git(["-C", str(addon), "rev-parse", "HEAD"], log=lambda msg: None)
        data = {**old, "commit": commit}
        source_marker(target).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        log(f"Updated to {commit[:12]}. Original PrintExp files remain untouched.")
        return commit
    if entry.exists():
        raise InstallationError(f"'{LAUNCHER_NAME}' already exists. Refusing to overwrite it.")
    log("Cloning private repository main branch via your installed Git credentials...")
    # Clone/build in the user profile rather than the protected PrintExp folder.
    # Installing into Program Files is handled through a separate UAC prompt.
    with tempfile.TemporaryDirectory(prefix="uv3d-setup-") as tmp:
        staged = Path(tmp) / "checkout"
        run_git(["clone", "--branch", "main", "--single-branch", repo_url, str(staged)], log=log)
        ensure_binaries(staged, log=log)
        commit = run_git(["-C", str(staged), "rev-parse", "HEAD"], log=lambda msg: None)
        # shutil.move also supports PrintExp being installed on another drive.
        # The managed add-on is the only directory written under PrintExp.
        shutil.move(str(staged), str(addon))
    try:
        entry.write_bytes(launcher_text().encode("utf-8"))
        data = {"format": MARKER_VALUE, "repo": REPOSITORY, "commit": commit,
                "host_exe_sha256": expected_sha, "launcher_sha256": sha256(entry)}
        source_marker(target).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except Exception:
        entry.unlink(missing_ok=True)
        shutil.rmtree(addon)
        raise
    log(f"Installed {commit[:12]}. Original PrintExp files remain untouched.")
    return commit


def uninstall(target: Path, log: Log = print) -> None:
    target = Path(target).expanduser().resolve()
    ensure_not_running()
    managed = assert_managed(target)
    addon = target / ADDON_DIR
    entry = target / LAUNCHER_NAME
    if not entry.is_file() or sha256(entry) != managed.get("launcher_sha256"):
        raise InstallationError("Launch script missing or edited. Aborting uninstall; no files removed.")
    # Only our new directory and our own launcher are removed. Vendor files are never modified.
    # The managed directory is intentionally reserved for source and binaries, not user projects.
    shutil.rmtree(addon)
    entry.unlink()
    log("Removed all add-on files. Original PrintExp files are unchanged.")
