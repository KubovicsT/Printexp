"""Update an existing PrintExp 3D add-on without opening its installer window."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from addon_manager_core import ADDON_DIR, InstallationError, install_or_update


def update_existing(target: Path, log=print) -> str:
    if not (target / ADDON_DIR / ".uv3d-managed-install.json").is_file():
        raise InstallationError("The add-on is not installed. Open Installer and click Install first.")
    return install_or_update(target, log=log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update PrintExp 3D add-on from main")
    parser.add_argument("--target", required=True)
    parser.add_argument("--log-file", required=True)
    args = parser.parse_args(argv)
    log_file = Path(args.log_file).resolve()

    def log(message: str) -> None:
        with log_file.open("a", encoding="utf-8") as file:
            file.write(str(message) + "\n")

    try:
        log("Fetching latest origin/main (no releases)...")
        commit = update_existing(Path(args.target).expanduser().resolve(), log=log)
        log("SUCCESS: add-on updated to " + commit[:12])
        return 0
    except Exception as exc:
        log("ERROR: " + str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
