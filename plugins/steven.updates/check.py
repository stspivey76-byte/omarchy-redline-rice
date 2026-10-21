#!/usr/bin/env python3
"""Read-only update checks; never installs or upgrades software."""
import concurrent.futures
import datetime
import json
import os
import shutil
import subprocess

def check(label, command, kind="lines", empty_codes=()):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=150,
                                env={**os.environ, "LC_ALL": "C", "NO_COLOR": "1", "MISE_MINIMUM_RELEASE_AGE": "0",
                                     "CHECKUPDATES_DB": os.path.join(
                                         os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                                         "steven-updates", "db")})
        if result.returncode in empty_codes:
            return label, [], None
        # yay returns 1 with no output when there are no AUR updates.
        if label == "AUR" and result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
            return label, [], None
        if result.returncode != 0:
            return label, [], (result.stderr.strip() or "check failed")[:180]
        if kind == "mise":
            data = json.loads(result.stdout)
            lines = [f"{name}: {item['current']} → {item['latest']}" for name, item in data.items()]
        elif kind == "firmware":
            data = json.loads(result.stdout)
            lines = [device.get("Name", "Device") for device in data.get("Devices", []) if device.get("Releases")]
        else:
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return label, lines, None
    except Exception as error:
        return label, [], str(error)[:180]

checks = []
for label, executable, arguments, kind, empty in [
    ("System", "checkupdates", ["--nocolor"], "lines", (2,)),
    ("AUR", "yay", ["-Qua", "--color", "never"], "lines", ()),
    ("Tools (mise)", "mise", ["outdated", "--global", "--json"], "mise", ()),
    ("Flatpak", "flatpak", ["remote-ls", "--updates", "--columns=application"], "lines", ()),
    ("Firmware", "fwupdmgr", ["get-updates", "--json"], "firmware", (2,)),
]:
    if shutil.which(executable):
        checks.append((label, [executable, *arguments], kind, empty))

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(lambda args: check(*args), checks))
count = sum(len(lines) for _, lines, _ in results)
errors = [f"{label}: {error}" for label, _, error in results if error]
details = [f"{count} available updates", "Checked " + datetime.datetime.now().strftime("%H:%M")]
for label, lines, error in results:
    details.append(f"\n{label}: {'check failed' if error else len(lines)}")
    details.extend(lines[:10])
    if len(lines) > 10:
        details.append(f"… and {len(lines) - 10} more")
if errors:
    details.extend(["\nChecks incomplete:", *errors])
details.append("\nLeft click: open system updater\nRight/middle click: check again")
print(json.dumps({"count": count, "errors": len(errors), "tooltip": "\n".join(details)}))
