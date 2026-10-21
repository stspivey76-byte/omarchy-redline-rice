#!/usr/bin/env python3
"""Per-user release updates and managed-file repairs for Redline Desktop."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

REPO = "stspivey76-byte/omarchy-redline-rice"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def paths():
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "redline-updater"
    return config, data / "redline-updater", state


def read_json(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else (default or {})


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("Unsupported release version: " + value)
    return tuple(map(int, match.groups()))


def fetch(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "Redline-Desktop-Updater", "Accept": "application/vnd.github+json" if url == API else "application/octet-stream"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Download exceeded size limit")
    return body


def validate_payload(payload, tag):
    if (payload / "VERSION").read_text().strip() != tag:
        raise ValueError("Release tag and bundled VERSION do not match")
    for name in ("install.sh", "scripts/install-omarchy.sh", "hooks/redline-gtk"):
        subprocess.run(["bash", "-n", str(payload / name)], check=True, capture_output=True)
    json.loads((payload / "shell.json").read_text())
    json.loads((payload / "fastfetch/config.jsonc").read_text())
    for manifest in (payload / "plugins").glob("*/manifest.json"):
        json.loads(manifest.read_text())
    for name in ("scripts/install-desktop.py", "scripts/updater.py", "scripts/register-updater.py", "scripts/palette.py"):
        compile((payload / name).read_text(), str(payload / name), "exec")


def download_release(release, cache):
    tag = release["tag_name"]
    version(tag)
    assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
    expected_prefix = f"https://github.com/{REPO}/releases/download/{tag}/"
    for name in ("redline-desktop.zip", "SHA256SUMS"):
        if assets.get(name) != expected_prefix + name:
            raise ValueError("Missing or unexpected release asset: " + name)
    checksum = fetch(assets["SHA256SUMS"], 4096).decode()
    matches = re.findall(r"^([a-fA-F0-9]{64})\s+\*?redline-desktop\.zip$", checksum, re.M)
    if len(matches) != 1:
        raise ValueError("Invalid SHA256SUMS")
    archive = fetch(assets["redline-desktop.zip"], 64 * 1024 * 1024)
    if hashlib.sha256(archive).hexdigest() != matches[0].lower():
        raise ValueError("Release ZIP checksum mismatch")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        root = Path(temporary)
        zip_path = root / "download.zip"
        zip_path.write_bytes(archive)
        with zipfile.ZipFile(zip_path) as zipped:
            if sum(item.file_size for item in zipped.infolist()) > 128 * 1024 * 1024:
                raise ValueError("Release archive is too large")
            for item in zipped.infolist():
                path = Path(item.filename)
                if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "redline-desktop" or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe archive entry")
            zipped.extractall(root)
        payload = root / "redline-desktop"
        validate_payload(payload, tag)
        destination = cache / tag
        if destination.exists():
            shutil.rmtree(destination)
        payload.rename(destination)
    return destination


def broken_files(config):
    broken = []
    for name, expected in config["hashes"].items():
        path = Path(name)
        try:
            matches = path.is_file() and digest(path) == expected
        except OSError:
            matches = False
        if not matches:
            broken.append(name)
    for name in config["required"]:
        if not Path(name).is_file():
            broken.append(name)
    return broken


def snapshot(roots, state):
    parent = state / "backups"
    parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="before-update-", dir=parent))
    entries = []
    for name in dict.fromkeys(roots):
        path = Path(name)
        copy = backup / str(len(entries))
        exists = path.exists() or path.is_symlink()
        if exists:
            if path.is_dir() and not path.is_symlink():
                shutil.copytree(path, copy, symlinks=True)
            else:
                shutil.copy2(path, copy, follow_symlinks=False)
        entries.append({"path": str(path), "backup": str(copy) if exists else None})
    write_json(backup / "snapshot.json", entries)
    return backup


def restore_snapshot(backup):
    for entry in reversed(read_json(backup / "snapshot.json")):
        path = Path(entry["path"])
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        if entry["backup"]:
            copy = Path(entry["backup"])
            path.parent.mkdir(parents=True, exist_ok=True)
            if copy.is_dir() and not copy.is_symlink():
                shutil.copytree(copy, path, symlinks=True)
            else:
                shutil.copy2(copy, path, follow_symlinks=False)


def run_installer(payload, profile, env):
    command = ["bash", str(payload / "install.sh"), "--desktop", profile]
    process = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise RuntimeError("Installer timed out; stopped its process group before rollback")
    return subprocess.CompletedProcess(command, process.returncode, stdout=output)


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


class Updater:
    def __init__(self):
        self.config_dir, self.root, self.state = paths()
        self.config_path = self.root / "config.json"
        self.config = read_json(self.config_path)
        self.status = read_json(self.state / "status.json")

    def log(self, message):
        self.state.mkdir(parents=True, exist_ok=True)
        path = self.state / "update.log"
        if path.exists() and path.stat().st_size > 1024 * 1024:
            path.replace(path.with_suffix(".previous.log"))
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + message
        with path.open("a") as stream:
            stream.write(line + "\n")
        print(line, flush=True)

    def active(self, profile):
        if profile == "omarchy":
            theme = Path.home() / ".local/state/omarchy/current/theme.name"
            return not theme.exists() or theme.read_text().strip() == "redline"
        css = self.config_dir / "gtk-4.0/gtk.css"
        return not css.exists() or "BEGIN REDLINE GTK" in css.read_text()

    def detect(self):
        return subprocess.check_output([sys.executable, str(self.root / "install-desktop.py"), "--detect"], text=True).strip()

    def apply(self, payload, profile):
        validate_payload(payload, (payload / "VERSION").read_text().strip())
        backup = snapshot(self.config["roots"], self.state)
        self.status["last_backup"] = str(backup)
        write_json(self.state / "status.json", self.status)
        env = dict(os.environ, REDLINE_UPDATER_RUNNING="1", REDLINE_SELECTED_COLOR=self.config.get("color", "red"))
        previous_theme = None
        previous_background = None
        if profile == "omarchy":
            current = Path.home() / ".local/state/omarchy/current"
            previous_theme = (current / "theme.name").read_text().strip() if (current / "theme.name").exists() else None
            previous_background = (current / "background").resolve() if (current / "background").exists() else None
        try:
            result = run_installer(payload, profile, env)
            self.log(result.stdout.strip())
            if result.returncode:
                raise RuntimeError(f"Installer exited with status {result.returncode}")
            registered = read_json(self.config_path)
            if broken_files(registered):
                raise RuntimeError("Installed files failed verification")
        except Exception:
            restore_snapshot(backup)
            if previous_theme:
                reapplied = subprocess.run(["omarchy", "theme", "set", previous_theme], capture_output=True, text=True, timeout=60)
                if reapplied.returncode:
                    self.log("Managed files restored, but previous live theme could not be reapplied: " + reapplied.stderr)
                if previous_background and previous_background.exists():
                    subprocess.run(["omarchy", "theme", "bg", "set", str(previous_background)], capture_output=True, timeout=30)
            self.log("Failed installation: restored managed files from " + str(backup))
            raise
        self.log("Installed and verified " + registered["version"] + " for " + profile)

    def check(self, scheduled=False, repair=False, force_release=False):
        with lock(self.state / "install.lock") as acquired:
            if not acquired:
                self.log("Another update is already running; skipped")
                return
            if not self.config:
                raise RuntimeError("Run the Redline installer first")
            if scheduled and not self.config["enabled"]:
                return
            profile = self.detect()
            if scheduled and profile == self.config["profile"] and not self.active(profile):
                return  # Respect switching away from Redline or disabling its GTK styling.
            now = time.time()
            if scheduled and now < self.status.get("retry_after", 0):
                return
            target = self.config["version"]
            if not scheduled or force_release or now - self.status.get("release_checked", 0) >= 3600:
                self.status["release_checked"] = now
                try:
                    release = json.loads(fetch(API, 1024 * 1024))
                    if not release.get("draft") and not release.get("prerelease") and version(release["tag_name"]) > version(target):
                        target = release["tag_name"]
                        payload = download_release(release, self.root / "releases")
                    else:
                        payload = self.root / "releases" / target
                except Exception as error:
                    self.log("Release check failed; keeping installed version: " + str(error))
                    self.status["last_network_error"] = str(error)
                    target = self.config["version"]
                    payload = self.root / "releases" / target
            else:
                payload = self.root / "releases" / target
            damaged = broken_files(self.config) if self.config.get("repair", True) or repair else []
            if target != self.config["version"] or profile != self.config["profile"] or repair or damaged:
                self.log("Applying " + target + (f"; repairing {len(damaged)} managed file(s)" if damaged else ""))
                try:
                    self.apply(payload, profile)
                    self.status.update(last_success=time.time(), last_error=None, failures=0, retry_after=0)
                except Exception as error:
                    failures = self.status.get("failures", 0) + 1
                    self.status.update(last_error=str(error), failures=failures, retry_after=time.time() + min(3600, 300 * 2 ** min(failures, 4)))
                    self.log("Update failed; will retry later: " + str(error))
                    write_json(self.state / "status.json", self.status)
                    raise
            else:
                self.log("Up to date: " + target)
            self.status["last_check"] = time.time()
            write_json(self.state / "status.json", self.status)

    def watch(self):
        session = os.environ.get("XDG_SESSION_ID", "default")
        safe_session = re.sub(r"[^a-zA-Z0-9_-]", "_", session)
        with lock(self.state / ("watch-" + safe_session + ".lock")) as acquired:
            if not acquired:
                return
            self.log("Background updater started for session " + session)
            time.sleep(60)
            while True:
                current = read_json(self.config_path)
                if not current.get("enabled"):
                    return
                if "XDG_SESSION_ID" in os.environ and shutil.which("loginctl"):
                    result = subprocess.run(["loginctl", "show-session", session, "-p", "State", "--value"], capture_output=True, text=True)
                    if result.returncode or result.stdout.strip() == "closing":
                        return
                    if result.stdout.strip() == "online":
                        time.sleep(300)
                        continue
                # Spawn fresh code each time so updater changes take effect without logout.
                subprocess.run([sys.executable, str(self.root / "updater.py"), "--scheduled"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(300)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    for name in ("check", "repair", "status", "enable", "disable", "updates-only", "enable-repair", "watch", "scheduled", "after-system-update"):
        actions.add_argument("--" + name, action="store_true")
    args = parser.parse_args()
    updater = Updater()
    if args.status:
        print(json.dumps({"configuration": updater.config, "status": updater.status, "log": str(updater.state / "update.log")}, indent=2))
        return
    if args.enable or args.disable or args.updates_only or args.enable_repair:
        if not updater.config:
            parser.error("Run the Redline installer first")
        if args.enable or args.disable:
            updater.config["enabled"] = args.enable
        else:
            updater.config["repair"] = args.enable_repair
        write_json(updater.config_path, updater.config)
        if args.enable or args.disable:
            autostart = updater.config_dir / "autostart/redline-updater.desktop"
            if autostart.exists():
                autostart.write_text(re.sub(r"^Hidden=.*$", "Hidden=" + str(args.disable).lower(), autostart.read_text(), flags=re.M))
        print("Automatic updates:", updater.config["enabled"], "Managed-file repairs:", updater.config["repair"])
        if args.enable and not os.environ.get("REDLINE_NO_START"):
            subprocess.Popen([sys.executable, str(updater.root / "updater.py"), "--watch"], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    try:
        if args.watch:
            updater.watch()
        else:
            updater.check(scheduled=args.scheduled or args.after_system_update, repair=args.repair or (args.after_system_update and updater.config.get("repair", True)), force_release=args.after_system_update)
    except Exception as error:
        updater.log("ERROR: " + str(error))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
