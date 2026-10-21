#!/usr/bin/env python3
"""Install shared Redline assets and apply settings for the active desktop."""
import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent.parent
PROFILES = ("auto", "omarchy", "gnome", "kde", "xfce", "cinnamon", "mate", "budgie", "lxqt", "lxde", "generic")


def detect_desktop(env=None, which=shutil.which):
    env = os.environ if env is None else env
    session = next((env[key] for key in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION") if env.get(key, "").strip()), "").lower()
    # Detect the active session, not whichever desktop tools happen to be installed.
    for profile, aliases in (
        ("cinnamon", ("cinnamon",)), ("budgie", ("budgie",)),
        ("kde", ("kde", "plasma")), ("xfce", ("xfce", "xubuntu")),
        ("mate", ("mate",)), ("lxqt", ("lxqt", "lubuntu")), ("lxde", ("lxde",)),
        ("gnome", ("gnome", "unity")),
    ):
        if any(alias in session for alias in aliases):
            return profile
    if session.strip() == "ubuntu":
        return "gnome"
    if ("hyprland" in session or (not session.strip() and env.get("HYPRLAND_INSTANCE_SIGNATURE"))) and which("omarchy"):
        return "omarchy"
    return "generic"


class Installer:
    def __init__(self, desktop):
        self.desktop = desktop
        home = Path.home()
        self.config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        self.data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
        state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state"))
        backup_parent = state / "redline-desktop/backups"
        backup_parent.mkdir(parents=True, exist_ok=True)
        self.backup = Path(tempfile.mkdtemp(prefix="install-", dir=backup_parent))
        self.manifest = {"desktop": desktop, "files": [], "settings": []}
        self.saved = set()
        self.warnings = []
        self.save()
        shutil.copy2(SOURCE / "scripts/restore-desktop.py", self.backup / "restore.py")
        print("Backup/restore: python3 " + shlex.quote(str(self.backup / "restore.py")), flush=True)

    def save(self):
        (self.backup / "restore.json").write_text(json.dumps(self.manifest, indent=2) + "\n")

    def preserve(self, path):
        path = Path(path)
        if str(path) in self.saved or any(str(parent) in self.saved for parent in path.parents):
            return
        self.saved.add(str(path))
        backup = self.backup / ("file-" + str(len(self.manifest["files"])))
        exists = path.exists() or path.is_symlink()
        if exists:
            if path.is_dir() and not path.is_symlink():
                shutil.copytree(path, backup, symlinks=True)
            else:
                shutil.copy2(path, backup, follow_symlinks=False)
        self.manifest["files"].append({"path": str(path), "backup": str(backup) if exists else None})
        self.save()

    def copy(self, source, destination):
        destination = Path(destination)
        self.preserve(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Replace a symlink itself, never overwrite the linked user's file.
        if destination.is_symlink():
            destination.unlink()
        if Path(source).is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)

    def run(self, *args):
        if not shutil.which(args[0]):
            self.warn("Missing " + args[0] + "; skipped: " + " ".join(args))
            return None
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as error:
            self.warn("Could not apply: " + " ".join(args) + "\n" + str(error))
            return None
        if result.returncode or "failed to commit changes" in result.stderr.lower():
            self.warn("Could not apply: " + " ".join(args) + "\n" + result.stderr.strip())
            return None
        return result.stdout.strip()

    def warn(self, message):
        self.warnings.append(message)
        print("NOTICE: " + message, flush=True)

    def gsettings(self, schema, key, value):
        keys = self.run("gsettings", "list-keys", schema)
        if keys is None or key not in keys.splitlines():
            self.warn(f"Unavailable setting: {schema} {key}")
            return
        old = self.run("gsettings", "get", schema, key)
        if old is None:
            return
        self.manifest["settings"].append({"restore": ["gsettings", "set", schema, key, old]})
        self.save()
        self.run("gsettings", "set", schema, key, value)

    def install_shared(self):
        self.assets = self.data / "redline-desktop"
        self.preserve(self.assets)
        if self.assets.is_symlink():
            self.assets.unlink()
        self.copy(SOURCE / "theme", self.assets / "theme")
        self.copy(SOURCE / "hooks/redline-gtk", self.assets / "gtk-style.sh")
        for version in ("3.0", "4.0"):
            self.preserve(self.config / ("gtk-" + version) / "gtk.css")
            settings_path = self.config / ("gtk-" + version) / "settings.ini"
            self.preserve(settings_path)
            settings = configparser.ConfigParser(interpolation=None)
            if settings_path.exists():
                settings.read(settings_path)
            if not settings.has_section("Settings"):
                settings.add_section("Settings")
            settings["Settings"]["gtk-application-prefer-dark-theme"] = "1"
            settings["Settings"]["gtk-theme-name"] = "Adwaita-dark"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = settings_path.with_suffix(".redline-tmp")
            with temporary.open("w") as output:
                settings.write(output)
            temporary.replace(settings_path)
        subprocess.run(["bash", str(self.assets / "gtk-style.sh"), "redline", str(self.assets / "theme")], check=True)
        self.copy(SOURCE / "fastfetch/omarchy-eclipse.txt", self.config / "fastfetch/omarchy-eclipse.txt")
        target = self.config / "fastfetch/config.jsonc"
        self.preserve(target)
        config = json.loads((SOURCE / "fastfetch/config.jsonc").read_text())
        config["logo"]["source"] = str(self.config / "fastfetch/omarchy-eclipse.txt")
        # Replace Omarchy-only probes with portable, built-in Fastfetch modules.
        replacements = iter((
            {"type": "os", "key": "OS"}, {"type": "de", "key": "Desktop"},
            {"type": "wm", "key": "Window manager"},
            {"type": "custom", "key": "Theme", "format": "Redline"},
            {"type": "packages", "key": "Packages"},
        ))
        config["modules"] = [next(replacements) if isinstance(m, dict) and m.get("type") == "command" and "omarchy-" in m.get("text", "") else m for m in config["modules"]]
        temporary = target.with_suffix(".redline-tmp")
        temporary.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(target)

    def apply(self):
        wallpaper = self.assets / "theme/backgrounds/tux-crimson-eclipse.png"
        uri = wallpaper.as_uri()
        if self.desktop in ("gnome", "budgie"):
            self.gsettings("org.gnome.desktop.interface", "color-scheme", "'prefer-dark'")
            self.gsettings("org.gnome.desktop.interface", "gtk-theme", "'Adwaita-dark'")
            self.gsettings("org.gnome.desktop.background", "picture-uri", repr(uri))
            self.gsettings("org.gnome.desktop.background", "picture-uri-dark", repr(uri))
            self.gsettings("org.gnome.desktop.background", "picture-options", "'zoom'")
        elif self.desktop == "cinnamon":
            self.gsettings("org.cinnamon.desktop.interface", "gtk-theme", "'Adwaita-dark'")
            self.gsettings("org.cinnamon.desktop.background", "picture-uri", repr(uri))
            self.gsettings("org.cinnamon.desktop.background", "picture-options", "'zoom'")
        elif self.desktop == "mate":
            self.gsettings("org.mate.interface", "gtk-theme", "'Adwaita-dark'")
            self.gsettings("org.mate.background", "picture-filename", repr(str(wallpaper)))
            self.gsettings("org.mate.background", "picture-options", "'zoom'")
        elif self.desktop == "kde":
            self.copy(SOURCE / "theme/Redline.colors", self.data / "color-schemes/Redline.colors")
            for name in ("kdeglobals", "plasma-org.kde.plasma.desktop-appletsrc"):
                self.preserve(self.config / name)
            self.run("plasma-apply-colorscheme", "Redline")
            self.run("plasma-apply-wallpaperimage", str(wallpaper))
        elif self.desktop == "xfce":
            self.preserve(self.config / "xfce4/xfconf/xfce-perchannel-xml/xsettings.xml")
            self.preserve(self.config / "xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml")
            self.xfconf("xsettings", "/Net/ThemeName", "Adwaita-dark")
            properties = self.run("xfconf-query", "-c", "xfce4-desktop", "-l")
            targets = [prop for prop in (properties or "").splitlines() if prop.startswith("/backdrop/") and prop.endswith(("/last-image", "/image-path"))]
            for prop in targets:
                self.xfconf("xfce4-desktop", prop, str(wallpaper))
            if not targets:
                self.warn("No active Xfce wallpaper properties found. Select the bundled wallpaper in Desktop Settings.")
        elif self.desktop in ("lxqt", "lxde"):
            # PCManFM writes its own settings; preserve its profile directories.
            manager = "pcmanfm-qt" if self.desktop == "lxqt" else "pcmanfm"
            self.preserve(self.config / manager)
            if self.desktop == "lxqt":
                self.run(manager, "--wallpaper-mode=zoom", "--set-wallpaper=" + str(wallpaper))
            else:
                self.run(manager, "--wallpaper-mode=zoom", "--set-wallpaper", str(wallpaper))
            if self.desktop == "lxqt":
                self.warn("GTK apps are styled; select your preferred Qt widget style in the desktop's Appearance settings.")
        else:
            self.warn("No native adapter for this session. GTK and Fastfetch installed; select the wallpaper manually: " + str(wallpaper))

    def xfconf(self, channel, prop, value):
        old = self.run("xfconf-query", "-c", channel, "-p", prop)
        if old is None:
            return
        self.manifest["settings"].append({"restore": ["xfconf-query", "-c", channel, "-p", prop, "-s", old]})
        self.save()
        self.run("xfconf-query", "-c", channel, "-p", prop, "-s", value)


def main():
    global SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", choices=PROFILES, default="auto")
    parser.add_argument("--detect", action="store_true", help="Print detected profile without making changes")
    parser.add_argument("--no-auto-update", action="store_true", help="Install without enabling automatic updates")
    # Accept the old updater argument only during migration from older releases.
    if os.environ.get("REDLINE_UPDATER_RUNNING"):
        parser.add_argument("--color", help=argparse.SUPPRESS)
    args = parser.parse_args()
    desktop = detect_desktop() if args.desktop == "auto" else args.desktop
    if args.detect:
        print(desktop)
        return
    from palette import choose_color, stage
    updater_config = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "redline-updater/config.json"
    saved = json.loads(updater_config.read_text()).get("color", "red") if updater_config.exists() else "red"
    color = choose_color(saved if saved in ("red", "blue", "green", "yellow", "pink", "purple") else "red", desktop)
    print("Selected color: " + color, flush=True)
    canonical = SOURCE
    with tempfile.TemporaryDirectory(prefix="redline-colors-") as temporary:
        SOURCE = stage(canonical, Path(temporary) / "redline-desktop", color)
        os.environ["REDLINE_BASE_SOURCE"] = str(canonical)
        os.environ["REDLINE_SELECTED_COLOR"] = color
        try:
            install_profile(args, desktop)
        finally:
            SOURCE = canonical


def preserve_runtime(installer):
    for path in (installer.data / "redline-updater", Path.home() / ".local/bin/redline-update",
                 Path.home() / ".local/bin/redline-uninstall", installer.config / "autostart/redline-updater.desktop"):
        installer.preserve(path)


def install_profile(args, desktop):
    print("Desktop profile: " + desktop, flush=True)
    if desktop == "omarchy":
        if not shutil.which("omarchy"):
            raise SystemExit("The Omarchy profile requires Omarchy to be installed")
        if os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")) != str(Path.home() / ".config"):
            raise SystemExit("The Omarchy installer requires the standard ~/.config directory")
        installer = Installer(desktop)
        omarchy = Path.home() / ".config/omarchy"
        for name in ("shell.json", "shell.toml", "themes/redline", "hooks/theme-set.d/redline-gtk",
                     "hooks/post-boot.d/redline-autoupdate", "hooks/post-update.d/redline-autoupdate"):
            installer.preserve(omarchy / name)
        for plugin in (SOURCE / "plugins").iterdir():
            installer.preserve(omarchy / "plugins" / plugin.name)
        for name in ("fastfetch/config.jsonc", "fastfetch/omarchy-eclipse.txt", "gtk-3.0/gtk.css", "gtk-4.0/gtk.css"):
            installer.preserve(installer.config / name)
        installer.preserve(Path.home() / ".local/state/omarchy/current")
        for key in ("color-scheme", "gtk-theme", "icon-theme"):
            old = installer.run("gsettings", "get", "org.gnome.desktop.interface", key)
            if old is not None:
                installer.manifest["settings"].append({"restore": ["gsettings", "set", "org.gnome.desktop.interface", key, old]})
        installer.save()
        preserve_runtime(installer)
        subprocess.run(["bash", str(SOURCE / "scripts/install-omarchy.sh")], check=True)
        subprocess.run([sys.executable, str(SOURCE / "scripts/register-updater.py"), str(SOURCE), desktop, *(["--disabled"] if args.no_auto_update else [])], check=True)
        return
    installer = Installer(desktop)
    installer.install_shared()
    installer.apply()
    preserve_runtime(installer)
    subprocess.run([sys.executable, str(SOURCE / "scripts/register-updater.py"), str(SOURCE), desktop, *(["--disabled"] if args.no_auto_update else [])], check=True)
    print("Shared theme, GTK styling, wallpaper assets and Fastfetch configuration installed.")
    print("Omarchy shell/bar plugins and idle settings require the Omarchy profile; other desktop panels are unchanged.")
    print("Reopen apps to load GTK styling. Fastfetch must already be installed.")
    print("Backup/restore: python3 " + shlex.quote(str(installer.backup / "restore.py")))
    if installer.warnings:
        print(f"Completed with {len(installer.warnings)} notice(s); review the skipped settings above.")


if __name__ == "__main__":
    if os.environ.get("REDLINE_UPDATER_RUNNING") or any(flag in sys.argv for flag in ("--detect", "--help", "-h")):
        main()
    else:
        from updater import lock, paths
        with lock(paths()[2] / "install.lock") as acquired:
            if not acquired:
                raise SystemExit("A Redline installation or update is already running; try again later.")
            main()
