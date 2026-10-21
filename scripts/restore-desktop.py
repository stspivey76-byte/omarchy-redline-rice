#!/usr/bin/env python3
"""Restore one portable installation; see the README for desktop-specific session guidance."""
import json
from pathlib import Path
import shutil
import subprocess


def main():
    manifest = json.loads(Path(__file__).with_name("restore.json").read_text())
    # Restore file data before notifying desktop settings services.
    for item in reversed(manifest["files"]):
        path = Path(item["path"])
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        if item["backup"]:
            backup = Path(item["backup"])
            path.parent.mkdir(parents=True, exist_ok=True)
            if backup.is_dir() and not backup.is_symlink():
                shutil.copytree(backup, path, symlinks=True)
            else:
                shutil.copy2(backup, path, follow_symlinks=False)
    failed = False
    for item in reversed(manifest["settings"]):
        try:
            result = subprocess.run(item["restore"], check=False)
            failed |= result.returncode != 0
        except OSError as error:
            print(error)
            failed = True
    print("Files restored. Log out and back in to reload cached desktop settings.")
    if manifest["desktop"] in ("kde", "lxqt", "lxde"):
        print("For Plasma/PCManFM, restore from a text console after logging out; running desktops can overwrite restored files.")
    if failed:
        raise SystemExit("Some desktop settings could not be restored; retry in the original desktop session.")


if __name__ == "__main__":
    main()
