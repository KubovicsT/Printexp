"""Verified, reversible patching of ONLY files inside a selected PrintExp folder.

This module is infrastructure for a future confirmed native-page registration
patch. It does not patch anything unless apply_host_patch is called explicitly.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

ADDON = "UV3DAddOn"
BACKUP_SUBDIR = ".host-patches"
MANIFEST = "manifest.json"
FORMAT = "printexp-uv3d-host-patches-v1"


class HostPatchError(Exception):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _location(selected: Path, relative: str) -> Path:
    """Keep targets in the selected folder and reject links/reparse paths."""
    selected = Path(selected).resolve(strict=True)
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(part in (".", "..") for part in path.parts):
        raise HostPatchError("Refusing an absolute or escaping host patch path")
    if path.parts[0].lower() == ADDON.lower():
        raise HostPatchError("Host patch targets must not include the add-on itself")
    candidate = selected.joinpath(*path.parts)
    if not candidate.resolve(strict=False).is_relative_to(selected):
        raise HostPatchError("Host patch target would leave the chosen folder")
    current = selected
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise HostPatchError("Host patch target passes through a link")
    return candidate


def _root(selected: Path) -> Path:
    result = Path(selected).resolve(strict=True) / ADDON / BACKUP_SUBDIR
    if result.is_symlink():
        raise HostPatchError("Backup directory cannot be a link")
    return result


def _read_manifest(selected: Path) -> dict:
    file = _root(selected) / MANIFEST
    if not file.exists():
        return {"format": FORMAT, "patches": []}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HostPatchError("Invalid host-patch manifest") from exc
    if data.get("format") != FORMAT or not isinstance(data.get("patches"), list):
        raise HostPatchError("Unexpected host-patch manifest format")
    return data


def _write_manifest(folder: Path, data: dict) -> None:
    # All temporary files are created INSIDE the selected PrintExp directory.
    folder.mkdir(parents=True, exist_ok=True)
    fd, tempname = tempfile.mkstemp(prefix=".uv3d-manifest-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(tempname, folder / MANIFEST)
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)


def _replace_bytes(target: Path, data: bytes) -> None:
    fd, tempname = tempfile.mkstemp(prefix=".uv3d-host-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tempname, target)
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)


def _backup_name(relative: str) -> str:
    return hashlib.sha256(relative.casefold().encode("utf-8")).hexdigest() + ".original"


def apply_host_patch(selected: Path, relative: str, expected_original_sha: str,
                     replacement: bytes) -> None:
    """Replace one verified original, retaining all backup bytes under UV3DAddOn.

    PrintExp must be stopped by the caller. Original content is checked first.
    A recovery manifest is written BEFORE touching the host file, so crashes
    cannot leave an untracked patch. Only content whose SHA matches exactly
    is eligible for later automatic restoration.
    """
    target = _location(selected, relative)
    if not target.is_file():
        raise HostPatchError("Expected PrintExp host file is missing")
    if len(replacement) == 0:
        raise HostPatchError("Empty replacement is forbidden")
    manifest = _read_manifest(selected)
    if any(p.get("path", "").casefold() == relative.casefold()
           for p in manifest["patches"]):
        raise HostPatchError("This host file already has a recorded patch")
    original_sha = _sha(target)
    if original_sha != expected_original_sha:
        raise HostPatchError("Original PrintExp host checksum does not match")
    backup_root = _root(selected)
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / _backup_name(relative)
    if backup.exists() or backup.is_symlink():
        raise HostPatchError("Backup filename already exists")
    backup.write_bytes(target.read_bytes())
    if _sha(backup) != expected_original_sha:
        backup.unlink(missing_ok=True)
        raise HostPatchError("Unable to verify original-file backup")
    patch = {"path": relative, "backup": backup.name,
             "original_sha256": expected_original_sha,
             "patched_sha256": hashlib.sha256(replacement).hexdigest()}
    manifest["patches"].append(patch)
    _write_manifest(backup_root, manifest)
    try:
        _replace_bytes(target, replacement)
        if _sha(target) != patch["patched_sha256"]:
            raise HostPatchError("Patched host checksum verification failed")
    except Exception:
        # Leave the backup and manifest if automatic rollback fails.
        try:
            _replace_bytes(target, backup.read_bytes())
            if _sha(target) == expected_original_sha:
                manifest["patches"].remove(patch)
                _write_manifest(backup_root, manifest)
                backup.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def verify_patched_host(selected: Path, relative: str,
                        expected_original_sha: str) -> bool:
    """Accept a patched host only if its stored original and patch match."""
    try:
        manifest = _read_manifest(selected)
        for patch in manifest["patches"]:
            if patch.get("path", "").casefold() == relative.casefold():
                backup = _root(selected) / patch["backup"]
                original = patch.get("original_sha256")
                if (original != expected_original_sha or
                    not backup.is_file() or _sha(backup) != original):
                    return False
                return _sha(_location(selected, relative)) == patch.get("patched_sha256")
    except (OSError, HostPatchError, KeyError, TypeError):
        pass
    return False


def restore_host_patches(selected: Path) -> None:
    """Restore every modified vendor file, then discard the in-folder backups.

    Uninstall must call this before deleting UV3DAddOn. Unexpected user changes
    abort rather than overwrite unknown file content.
    """
    manifest = _read_manifest(selected)
    patches = manifest["patches"]
    folder = _root(selected)
    # Preflight EVERY file before restoring ANY file.
    prepared = []
    for patch in patches:
        relative = patch["path"]
        target = _location(selected, relative)
        backup = folder / patch["backup"]
        if backup.is_symlink() or not backup.is_file():
            raise HostPatchError("Cannot restore: an original backup is missing")
        source_hash = patch["original_sha256"]
        if _sha(backup) != source_hash:
            raise HostPatchError("Cannot restore: an original backup has changed")
        current = _sha(target)
        if current not in (source_hash, patch["patched_sha256"]):
            raise HostPatchError("Cannot restore: host file changed since patching")
        prepared.append((target, backup, source_hash))
    for target, backup, expected in prepared:
        if _sha(target) != expected:
            _replace_bytes(target, backup.read_bytes())
            if _sha(target) != expected:
                raise HostPatchError("Restored host checksum mismatch: " + target.name)
    # Uninstall removes the entire managed add-on only after restore returns.
    if patches:
        manifest["patches"] = []
        _write_manifest(folder, manifest)


def snapshot_count(selected: Path) -> int:
    return len(_read_manifest(selected)["patches"])
