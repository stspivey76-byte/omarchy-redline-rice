#!/usr/bin/env python3
"""Install and register the per-user updater after a successful theme install."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from updater import digest, paths, read_json, snapshot, validate_payload, version, write_json


def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def register(source, profile, disabled=False):
    canonical = Path(os.environ.get("REDLINE_BASE_SOURCE", str(source)))
    color = os.environ.get("REDLINE_SELECTED_COLOR", "red")
    config, root, state = paths()
    tag = (source / "VERSION").read_text().strip()
    version(tag)
    validate_payload(source, tag)
    prior = read_json(root / "config.json")
    enabled = False if disabled else prior.get("enabled", True)
    root.mkdir(parents=True, exist_ok=True)
    launcher = Path.home() / ".local/bin/redline-update"
    autostart = config / "autostart/redline-updater.desktop"
    runtime_paths = [root / "updater.py", root / "install-desktop.py", root / "uninstall.py", root / "config.json", launcher, launcher.with_name("redline-uninstall"), autostart]
    if profile == "omarchy":
        runtime_paths.extend(config / "omarchy/hooks" / (kind + ".d") / "redline-autoupdate" for kind in ("post-boot", "post-update"))
    snapshot(map(str, runtime_paths), state)
    for name in ("updater.py", "install-desktop.py", "uninstall.py"):
        temporary = root / (name + ".new")
        shutil.copy2(source / "scripts" / name, temporary)
        temporary.replace(root / name)
    payload = root / "releases" / tag
    if canonical.resolve() != payload.resolve():
        staging = root / "releases" / (tag + ".new")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        for name in ("VERSION", "install.sh", "scripts", "theme", "plugins", "hooks", "fastfetch", "shell.json", "shell.toml"):
            origin = canonical / name
            if origin.is_dir():
                shutil.copytree(origin, staging / name, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(origin, staging / name)
        if payload.exists():
            shutil.rmtree(payload)
        staging.rename(payload)
    hashes = {}
    managed_roots = []

    def manage_tree(origin, destination):
        managed_roots.append(str(destination))
        for item in origin.rglob("*"):
            if item.is_file() and "__pycache__" not in item.parts:
                hashes[str(destination / item.relative_to(origin))] = digest(item)

    if profile == "omarchy":
        omarchy = Path.home() / ".config/omarchy"
        manage_tree(source / "theme", omarchy / "themes/redline")
        for plugin in (source / "plugins").iterdir():
            manage_tree(plugin, omarchy / "plugins" / plugin.name)
        managed_roots.extend(str(omarchy / name) for name in ("shell.json", "shell.toml", "hooks/theme-set.d/redline-gtk"))
        hashes[str(omarchy / "hooks/theme-set.d/redline-gtk")] = digest(source / "hooks/redline-gtk")
    else:
        assets = root.parent / "redline-desktop"
        manage_tree(source / "theme", assets / "theme")
        managed_roots.append(str(assets / "gtk-style.sh"))
        hashes[str(assets / "gtk-style.sh")] = digest(source / "hooks/redline-gtk")
        if profile == "kde":
            hashes[str(root.parent / "color-schemes/Redline.colors")] = digest(source / "theme/Redline.colors")
            managed_roots.extend(str(path) for path in (root.parent / "color-schemes/Redline.colors", config / "kdeglobals", config / "plasma-org.kde.plasma.desktop-appletsrc"))
        elif profile == "xfce":
            managed_roots.extend(str(config / "xfce4/xfconf/xfce-perchannel-xml" / name) for name in ("xsettings.xml", "xfce4-desktop.xml"))
        elif profile in ("lxqt", "lxde"):
            managed_roots.append(str(config / ("pcmanfm-qt" if profile == "lxqt" else "pcmanfm")))
    logo = config / "fastfetch/omarchy-eclipse.txt"
    hashes[str(logo)] = digest(source / "fastfetch/omarchy-eclipse.txt")
    required = [str(config / "fastfetch/config.jsonc")]
    if profile == "omarchy":
        required.extend(str(Path.home() / ".config/omarchy" / name) for name in ("shell.json", "shell.toml"))
    managed_roots.extend([str(logo), *required])
    for gtk in ("gtk-3.0", "gtk-4.0"):
        required.append(str(config / gtk / "gtk.css"))
        managed_roots.append(str(config / gtk / "gtk.css"))
        if profile != "omarchy":
            managed_roots.append(str(config / gtk / "settings.ini"))
    managed_roots.extend(map(str, runtime_paths))
    write_json(root / "config.json", {"version": tag, "profile": profile, "color": color, "enabled": enabled, "repair": prior.get("repair", True), "hashes": hashes, "required": required, "roots": managed_roots})
    launcher.parent.mkdir(parents=True, exist_ok=True)
    temporary = launcher.with_suffix(".new")
    temporary.write_text("#!/usr/bin/env bash\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(root / "updater.py")) + ' "$@"\n')
    temporary.chmod(0o755)
    temporary.replace(launcher)
    uninstall = launcher.with_name("redline-uninstall")
    uninstall.write_text("#!/usr/bin/env bash\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(root / "uninstall.py")) + ' "$@"\n')
    uninstall.chmod(0o755)
    autostart.parent.mkdir(parents=True, exist_ok=True)
    autostart.write_text("[Desktop Entry]\nType=Application\nName=Redline Desktop Updater\nComment=Keep Redline theme and plugins up to date\nExec=" + desktop_quote(sys.executable) + " " + desktop_quote(root / "updater.py") + " --watch\nTerminal=false\nHidden=" + str(not enabled).lower() + "\n")
    if profile == "omarchy":
        with tempfile.TemporaryDirectory() as temporary_dir:
            hook = Path(temporary_dir) / "redline-autoupdate"
            for kind, action in (("post-boot", "--watch"), ("post-update", "--after-system-update")):
                hook.write_text("#!/usr/bin/env bash\nnohup " + shlex.quote(str(launcher)) + " " + action + " </dev/null >/dev/null 2>&1 &\n")
                subprocess.run(["omarchy", "hook", "install", kind, str(hook)], check=True)
    print("Automatic Redline updates:", "enabled" if enabled else "disabled")
    print("Updater:", str(launcher), "--status")
    if enabled and not os.environ.get("REDLINE_UPDATER_RUNNING") and not os.environ.get("REDLINE_NO_START"):
        subprocess.Popen([sys.executable, str(root / "updater.py"), "--watch"], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("profile")
    parser.add_argument("--disabled", action="store_true")
    args = parser.parse_args()
    register(args.source, args.profile, args.disabled)
