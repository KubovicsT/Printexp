"""Optional offline-development profile for the selected PrintExp installation.

PrintExp's own Project.ini documents PROJECT_MODE=0 as online and
PROJECT_MODE=1 as debug. This option does not emulate a connected controller.
Original bytes are backed up with SHA-256 validation inside UV3DAddOn and
restored by Uninstall or an explicit switch back to online mode.
"""
from __future__ import annotations

import re
from pathlib import Path

from host_backup import (HostPatchError, _read_manifest, apply_host_patch,
                         restore_host_patches, _sha)

MODE_KEY = "PROJECT_MODE"
PROFILE_FILE = "Project.ini"


class OfflineProfileError(Exception):
    pass


def _mode_span(data: bytes) -> tuple[int, int]:
    """Find the numeric mode in PROJECT_CONFIG without decoding GBK comments."""
    inside = False
    span: tuple[int, int] | None = None
    offset = 0
    for line in data.splitlines(keepends=True):
        trimmed = line.strip()
        if trimmed.startswith(b"[") and trimmed.endswith(b"]"):
            inside = trimmed.lower() == b"[project_config]"
        elif inside and not trimmed.startswith((b";", b"#", b"//")):
            m = re.match(rb"[ \t]*PROJECT_MODE[ \t]*=[ \t]*([01])(?=$|[ \t\r\n;#])",
                         line, re.IGNORECASE)
            if m:
                if span is not None:
                    raise OfflineProfileError("Project.ini contains duplicate PROJECT_MODE settings")
                span = (offset + m.start(1), int(m.group(1)))
        offset += len(line)
    if span is None:
        raise OfflineProfileError(
            "Project.ini has no recognized [PROJECT_CONFIG] PROJECT_MODE=0/1 setting"
        )
    return span


def read_project_mode(target: Path) -> int:
    ini = Path(target) / PROFILE_FILE
    return _mode_span(ini.read_bytes())[1]


def _offline_patch(target: Path) -> dict | None:
    for patch in _read_manifest(target)["patches"]:
        if patch.get("path", "").casefold() == PROFILE_FILE.casefold():
            return patch
    return None


def enable_offline(target: Path) -> str:
    target = Path(target).resolve()
    marker = target / "UV3DAddOn" / ".uv3d-managed-install.json"
    if not marker.is_file():
        raise OfflineProfileError("Install the PrintExp add-on before enabling offline development")
    ini = target / PROFILE_FILE
    data = ini.read_bytes()
    offset, mode = _mode_span(data)
    existing = _offline_patch(target)
    if existing:
        if mode == 1 and _sha(ini) == existing.get("patched_sha256"):
            return "Offline development mode already enabled; original Project.ini backup verified."
        raise OfflineProfileError(
            "Project.ini differs from the add-on's recorded backup; refusing to overwrite it"
        )
    if mode == 1:
        return "PrintExp already has debug mode enabled; no configuration was changed."
    if mode != 0:
        raise OfflineProfileError("Unsupported Project.ini mode")
    replacement = data[:offset] + b"1" + data[offset + 1:]
    apply_host_patch(target, PROFILE_FILE, _sha(ini), replacement)
    if read_project_mode(target) != 1 or _sha(ini) != _offline_patch(target)["patched_sha256"]:
        raise OfflineProfileError("Debug mode verification failed; restore from the in-folder backup")
    return "Offline debug mode enabled: Project.ini PROJECT_MODE=1. Original stored under UV3DAddOn/.host-patches."


def disable_offline(target: Path) -> str:
    target = Path(target).resolve()
    existing = _offline_patch(target)
    if not existing:
        return "No managed offline profile to restore; original Project.ini left untouched."
    patches = _read_manifest(target)["patches"]
    if len(patches) != 1:
        raise OfflineProfileError(
            "Other host patches also exist. Refusing to restore unrelated PrintExp files."
        )
    restore_host_patches(target)
    if read_project_mode(target) != 0:
        raise OfflineProfileError("Project.ini restore did not recover online mode")
    return "Original Project.ini restored: online mode. Its SHA-256 was verified."


def run_offline_action(target: Path, enabled: bool) -> str:
    try:
        return enable_offline(target) if enabled else disable_offline(target)
    except HostPatchError as exc:
        raise OfflineProfileError(str(exc)) from exc
