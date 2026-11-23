"""Reversible redirection of a PrintExp test copy to a loopback-only controller.

No hardware communication is implemented here. The loopback endpoint is a
transport-only simulation until actual request/response frames are known.
"""
from __future__ import annotations

from pathlib import Path
import re

from host_backup import (HostPatchError, apply_host_patch,
                         restore_host_patches, snapshot_count, _sha, _read_manifest)

LOCAL = b"127.0.0.1"
ORIGINAL = b"192.168.127.10"
PROFILE_NAME = "Project.ini"


class SimulationProfileError(Exception):
    pass


def _change_ini(data: bytes, changes: dict[tuple[bytes, bytes], bytes]) -> bytes:
    current = b""
    found = set()
    result = []
    for line in data.splitlines(keepends=True):
        header = re.match(rb"^[ \t]*\[([A-Z0-9_]+)\]", line, re.I)
        if header:
            current = header.group(1).upper()
        match = re.match(rb"^([ \t]*)([A-Za-z0-9_]+)([ \t]*=[ \t]*)([^;\r\n]*)(.*)$", line)
        if match and not line.lstrip().startswith((b";", b"#", b"//")):
            key = (current, match.group(2).upper())
            if key in changes:
                if key in found:
                    raise SimulationProfileError("Duplicate configuration key " + repr(key))
                found.add(key)
                suffix = match.group(5)
                ending = b""
                if suffix.endswith(b"\r\n"):
                    ending = b"\r\n"
                    suffix = suffix[:-2]
                elif suffix.endswith(b"\n"):
                    ending = b"\n"
                    suffix = suffix[:-1]
                # Retain original indentation, separators, comments and newline.
                line = match.group(1) + match.group(2) + match.group(3) + changes[key] + suffix + ending
        result.append(line)
    if not changes.keys() <= found:
        missing = changes.keys() - found
        raise SimulationProfileError("Missing configuration keys: " + repr(missing))
    return b"".join(result)


def _simulated(target: Path) -> bool:
    file = Path(target) / PROFILE_NAME
    try:
        data = file.read_bytes()
        return (b"PROJECT_MODE=1" in data and
                data.count(b"ServerIP=127.0.0.1") >= 2)
    except OSError:
        return False


def enable_simulation(target: Path) -> str:
    target = Path(target).resolve(strict=True)
    if not (target / "UV3DAddOn" / ".uv3d-managed-install.json").is_file():
        raise SimulationProfileError("Add-on must be installed first")
    if _simulated(target) and snapshot_count(target):
        return "Loopback simulation profile is already enabled."
    current = _read_manifest(target)["patches"]
    # An older offline profile may have patched Project.ini. Restore it before
    # applying a combined offline+loopback profile; preserve the true original.
    if current:
        if any(p.get("path", "").casefold() != PROFILE_NAME.casefold() for p in current):
            raise SimulationProfileError("Other PrintExp host patches exist; refusing to replace them")
        if len(current) != 1:
            raise SimulationProfileError("Unexpected host backup count")
        restore_host_patches(target)
    ini = target / PROFILE_NAME
    data = ini.read_bytes()
    modified = _change_ini(data, {
        (b"PROJECT_CONFIG", b"PROJECT_MODE"): b"1",
        (b"COMM_CONFIG", b"SERVERIP"): LOCAL,
        (b"PLC_COMM", b"SERVERIP"): LOCAL
    })
    if data == modified:
        raise SimulationProfileError("Original profile is already redirected without a managed backup")
    apply_host_patch(target, PROFILE_NAME, _sha(ini), modified)
    if not _simulated(target):
        raise SimulationProfileError("Loopback profile could not be verified")
    return "Simulated connection configured: Project.ini now targets 127.0.0.1:5001 only."


def disable_simulation(target: Path) -> str:
    target = Path(target).resolve(strict=True)
    patches = _read_manifest(target)["patches"]
    if not patches:
        return "No managed simulation configuration to restore."
    if any(p.get("path", "").casefold() != PROFILE_NAME.casefold() for p in patches):
        raise SimulationProfileError("Other host patches exist; cannot restore automatically")
    restore_host_patches(target)
    return "Original PrintExp Project.ini configuration restored and verified."


def ensure_safe_profile(target: Path) -> None:
    if not _simulated(target):
        raise SimulationProfileError("Simulated connection requires mode=1 and both controller IPs on 127.0.0.1")
    if not snapshot_count(target):
        raise SimulationProfileError("Simulation profile has no verified original backup")
