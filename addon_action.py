"""Headless add-on operation used only by the elevated PowerShell worker."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from addon_manager_core import ADDON_DIR, InstallationError, install_or_update, uninstall


def run_action(action: str, folder: Path, log=print) -> None:
    if action == "install":
        if (folder / ADDON_DIR).exists():
            raise InstallationError("Already installed; use Update from main.")
        commit = install_or_update(folder, log=log)
        log(f"Installed add-on at {commit[:12]}")
    elif action == "update":
        if not (folder / ADDON_DIR / ".uv3d-managed-install.json").is_file():
            raise InstallationError("No managed add-on installed; use Install Add-on.")
        commit = install_or_update(folder, log=log)
        log(f"Updated add-on to {commit[:12]}")
    elif action == "uninstall":
        uninstall(folder, log=log)
    else:
        raise InstallationError(f"Unknown action: {action}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PrintExp 3D elevated add-on worker")
    parser.add_argument("--action", required=True, choices=("install", "update", "uninstall"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--log-file", help="Write progress to the UI worker's operation log")
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        if args.log_file:
            with Path(args.log_file).open("a", encoding="utf-8") as stream:
                stream.write(str(message) + "\n")
        else:
            print(message)

    try:
        run_action(args.action, Path(args.target).expanduser().resolve(), log=log)
        return 0
    except (InstallationError, OSError, RuntimeError) as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
