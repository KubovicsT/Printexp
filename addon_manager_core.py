"""Transactional, version-pinned PrintExp add-on installer. No vendor files are modified."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Callable

from host_backup import HostPatchError, verify_patched_host, restore_host_patches

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
    if current != expected_sha and not verify_patched_host(folder, "PrintExp_X64.exe", expected_sha):
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


def write_launcher_bytes(path: Path, content: bytes) -> None:
    """Write only the managed launcher; replaceable in transaction tests."""
    path.write_bytes(content)


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


def remove_managed_directory(path: Path) -> None:
    """Remove a marker-verified checkout, including read-only Git objects on Windows."""
    def retry_readonly(remove_func, entry, failure):
        error = failure[1]
        if not isinstance(error, PermissionError):
            raise error
        os.chmod(entry, stat.S_IWRITE | stat.S_IREAD)
        remove_func(entry)
    shutil.rmtree(path, onerror=retry_readonly)


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


def _clone_release(staged: Path, repo_url: str, log: Log) -> str:
    """Fetch the latest main branch to a user/temp location, never into PrintExp.

    Git may create files with temp-directory ACLs. They must be COPIED (not
    renamed) into Program Files to inherit the PrintExp directory's ACLs.
    """
    log("Downloading latest main branch into a temporary workspace...")
    run_git(["clone", "--branch", "main", "--single-branch", repo_url, str(staged)], log=log)
    ensure_binaries(staged, log=log)
    return run_git(["-C", str(staged), "rev-parse", "HEAD"], log=lambda msg: None)


def _verify_package(root: Path, source: Path) -> None:
    """Check every tracked source file and both runnable binaries after copying.

    This runs against the actual destination, not merely the staged download.
    Never consider a directory entry alone proof of a complete installation.
    """
    tracked = run_git(["-C", str(source), "ls-files"], log=lambda _: None).splitlines()
    required = set(tracked)
    required.update(str(Path("dist") / "windows" / binary) for binary in BINARIES)
    required.add(str(Path(".git") / "HEAD"))
    for name in sorted(required):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise InstallationError("Unsafe source path in add-on repository: " + name)
        original = source / relative
        installed = root / relative
        if not original.is_file() or not installed.is_file():
            raise InstallationError("Post-install verification: missing required file: " + name)
        try:
            if original.stat().st_size == 0 or sha256(installed) != sha256(original):
                raise InstallationError("Post-install verification: corrupted or empty file: " + name)
        except PermissionError as exc:
            raise InstallationError("Post-install verification: access denied reading " + name) from exc


def verify_installed_files(target: Path, source: Path, commit: str,
                           expected_sha: str, log: Log = print) -> None:
    """End-to-end installation check, including launcher, marker and Git HEAD."""
    target = Path(target)
    addon = target / ADDON_DIR
    entry = target / LAUNCHER_NAME
    log("Post-install verification: checking add-on files, checksums, launcher and version...")
    _verify_package(addon, source)
    try:
        if not entry.is_file():
            raise InstallationError("Post-install verification: launch script is missing")
        expected_launcher = hashlib.sha256(launcher_text().encode("utf-8")).hexdigest()
        if sha256(entry) != expected_launcher:
            raise InstallationError("Post-install verification: launch script was not installed correctly")
        marker = assert_managed(target)
        if (marker.get("commit") != commit or
                marker.get("host_exe_sha256") != expected_sha or
                marker.get("launcher_sha256") != expected_launcher):
            raise InstallationError("Post-install verification: installation marker is missing or inconsistent")
        installed_head = run_git(["-C", str(addon), "rev-parse", "HEAD"], log=lambda _: None)
        if installed_head != commit:
            raise InstallationError("Post-install verification: installed Git revision does not match")
    except PermissionError as exc:
        raise InstallationError("Post-install verification: access denied to installed add-on") from exc
    log("Post-install verification PASSED: all required add-on files are present and match the source.")


def install_or_update(target: Path, log: Log = print, repo_url: str = REPOSITORY,
                      expected_sha: str = SUPPORTED_EXE_SHA256) -> str:
    target = Path(target).expanduser().resolve()
    validate_target(target, expected_sha)
    ensure_not_running()
    addon = target / ADDON_DIR
    entry = target / LAUNCHER_NAME
    is_update = addon.exists()
    existing_marker = None
    previous_launcher = None
    if is_update:
        existing_marker = assert_managed(target)
        if not (addon / ".git").is_dir():
            raise InstallationError("The installed add-on Git checkout is missing. No files were changed.")
        if not entry.is_file():
            raise InstallationError("The add-on launcher is missing. No files were changed.")
        previous_launcher = entry.read_bytes()
        if sha256(entry) != existing_marker.get("launcher_sha256"):
            raise InstallationError("The add-on launcher has been modified; refusing to overwrite it.")
        remote = run_git(["-C", str(addon), "remote", "get-url", "origin"], log=lambda msg: None)
        if remote != repo_url:
            raise InstallationError("The installed add-on has an unexpected Git remote.")
        if run_git(["-C", str(addon), "status", "--porcelain", "--untracked-files=no"],
                   log=lambda msg: None):
            raise InstallationError("The installed add-on has edited tracked files. No changes were made.")
    elif entry.exists():
        raise InstallationError(f"'{LAUNCHER_NAME}' already exists. Refusing to overwrite it.")

    with tempfile.TemporaryDirectory(prefix="uv3d-setup-") as tmp:
        staged = Path(tmp) / "checkout"
        commit = _clone_release(staged, repo_url, log)
        if is_update:
            # This is also a repair for old installations that were moved from
            # an elevated user's temp directory. The candidate inherits the
            # target parent's normal ACLs; the old restrictive ACLs are discarded.
            suffix = uuid.uuid4().hex
            candidate = target / f"{ADDON_DIR}.staging-{suffix}"
            backup = target / f"{ADDON_DIR}.backup-{suffix}"
            backed_up = False
            installed_candidate = False
            try:
                log("Preparing an updated add-on with freshly inherited PrintExp permissions...")
                shutil.copytree(staged, candidate)
                # In-folder originals must survive any Git-main add-on update.
                original_backups = addon / ".host-patches"
                if original_backups.exists():
                    if original_backups.is_symlink():
                        raise InstallationError("Host backup directory cannot be a link.")
                    shutil.copytree(original_backups, candidate / ".host-patches")
                local_settings = addon / "config" / "local-stage1.ini"
                if local_settings.is_file() and not local_settings.is_symlink():
                    shutil.copy2(local_settings, candidate / "config" / "local-stage1.ini")
                _verify_package(candidate, staged)
                new_launcher = launcher_text().encode("utf-8")
                data = {**existing_marker, "commit": commit,
                        "launcher_sha256": hashlib.sha256(new_launcher).hexdigest()}
                (candidate / MARKER_NAME).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                addon.rename(backup)
                backed_up = True
                candidate.rename(addon)
                installed_candidate = True
                write_launcher_bytes(entry, new_launcher)
                verify_installed_files(target, staged, commit, expected_sha, log=log)
            except Exception as exc:
                if installed_candidate and addon.exists():
                    remove_managed_directory(addon)
                if backed_up and backup.exists():
                    backup.rename(addon)
                if previous_launcher is not None and entry.exists():
                    write_launcher_bytes(entry, previous_launcher)
                raise InstallationError(f"Update failed; previous version restored: {exc}") from exc
            finally:
                if candidate.exists():
                    remove_managed_directory(candidate)
            try:
                remove_managed_directory(backup)
            except OSError as exc:
                # A successful update is safer than undoing it just because
                # Windows blocked deletion of obsolete, backed-up Git objects.
                log(f"WARNING: Old add-on backup could not be removed: {backup} ({exc})")
            log(f"Updated to {commit[:12]}, including repair of inherited file permissions.")
            return commit

        log("Installing add-on files with the PrintExp folder's inherited permissions...")
        try:
            # Never rename/move a folder from %TEMP% into Program Files. Doing
            # so can retain the ADMIN user's private temp ACL and cause Access
            # Denied when the standard user launches the installed EXE.
            shutil.copytree(staged, addon)
            _verify_package(addon, staged)
            write_launcher_bytes(entry, launcher_text().encode("utf-8"))
            data = {"format": MARKER_VALUE, "repo": REPOSITORY, "commit": commit,
                    "host_exe_sha256": expected_sha, "launcher_sha256": sha256(entry)}
            source_marker(target).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            verify_installed_files(target, staged, commit, expected_sha, log=log)
        except Exception:
            entry.unlink(missing_ok=True)
            if addon.exists():
                remove_managed_directory(addon)
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
    # Restore originals before deleting their only verified backups.
    try:
        restore_host_patches(target)
    except HostPatchError as exc:
        raise InstallationError("Uninstall stopped to protect PrintExp: " + str(exc)) from exc
    remove_managed_directory(addon)
    entry.unlink()
    log("Removed all add-on files. Original PrintExp files are unchanged.")
