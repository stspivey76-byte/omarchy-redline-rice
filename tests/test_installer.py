"""Exercise desktop routing and installation without changing the host desktop."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install-desktop.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

FAKE_TOOL = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
name = Path(sys.argv[0]).name
with open(os.environ["TOOL_LOG"], "a") as log:
    log.write(json.dumps([name, *args]) + "\\n")
if os.environ.get("FAIL_DESKTOP_TOOLS"):
    sys.stderr.write("No desktop service available\\n")
    sys.exit(1)
if name == "gsettings":
    if args[0] == "list-keys":
        print("color-scheme\\ngtk-theme\\npicture-uri\\npicture-uri-dark\\npicture-options\\npicture-filename")
    elif args[0] == "get":
        print("'original'")
elif name == "xfconf-query":
    if "-l" in args:
        print("/backdrop/screen0/monitor0/workspace0/last-image\\n/backdrop/screen0/monitor1/workspace0/last-image\\n/unrelated")
    elif "-s" not in args:
        print("original")
elif name == "omarchy" and args[:2] == ["hook", "install"]:
    import shutil
    target = Path.home() / ".config/omarchy/hooks" / (args[2] + ".d")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args[3], target / Path(args[3]).name)
'''


class InstallerTests(unittest.TestCase):
    def test_detection_prefers_active_desktop_over_installed_tools(self):
        for session, expected in (("GNOME", "gnome"), ("ubuntu:GNOME", "gnome"),
                                  ("KDE", "kde"), ("plasma", "kde"), ("XFCE", "xfce"),
                                  ("X-Cinnamon", "cinnamon"), ("MATE", "mate"),
                                  ("Budgie:GNOME", "budgie"), ("LXQt", "lxqt"),
                                  ("LXDE", "lxde"), ("Hyprland", "omarchy"),
                                  ("sway", "generic")):
            with self.subTest(session=session):
                self.assertEqual(installer.detect_desktop({"XDG_CURRENT_DESKTOP": session}, lambda _: "/bin/tool"), expected)
        self.assertEqual(installer.detect_desktop({"XDG_CURRENT_DESKTOP": "Hyprland"}, lambda _: None), "generic")
        self.assertEqual(installer.detect_desktop({}, lambda _: "/bin/tool"), "generic")
        self.assertEqual(installer.detect_desktop({"XDG_CURRENT_DESKTOP": "GNOME", "HYPRLAND_INSTANCE_SIGNATURE": "stale"}, lambda _: "/bin/tool"), "gnome")
        self.assertEqual(installer.detect_desktop({"XDG_CURRENT_DESKTOP": "sway", "HYPRLAND_INSTANCE_SIGNATURE": "stale"}, lambda _: "/bin/tool"), "generic")
        self.assertEqual(installer.detect_desktop({"DESKTOP_SESSION": "ubuntu-sway"}, lambda _: "/bin/tool"), "generic")
        self.assertEqual(installer.detect_desktop({"XDG_CURRENT_DESKTOP": "GNOME", "DESKTOP_SESSION": "plasma"}, lambda _: "/bin/tool"), "gnome")
        self.assertEqual(installer.detect_desktop({"XDG_CURRENT_DESKTOP": "Hyprland", "DESKTOP_SESSION": "gnome"}, lambda _: "/bin/tool"), "omarchy")

    def test_failed_native_settings_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            binary = home / "bin"
            binary.mkdir()
            tool = binary / "gsettings"
            tool.write_text(FAKE_TOOL)
            tool.chmod(0o755)
            env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "config"), XDG_DATA_HOME=str(home / "data"), XDG_STATE_HOME=str(home / "state"), PATH=str(binary) + ":" + os.environ["PATH"], TOOL_LOG=str(home / "log"), FAIL_DESKTOP_TOOLS="1", REDLINE_NO_START="1", REDLINE_UPDATER_RUNNING="1")
            result = subprocess.run(["bash", str(ROOT / "install.sh"), "--desktop", "gnome"], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Could not apply", result.stdout)
            self.assertIn("Completed with", result.stdout)
            self.assertTrue((home / "config/gtk-4.0/gtk.css").exists())

    def exercise_profile(self, profile):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "home"
            config = home / (".config" if profile == "omarchy" else "custom-config")
            data = home / "custom-data"
            state = home / "custom-state"
            binary = base / "bin"
            binary.mkdir()
            driver = binary / "driver"
            driver.write_text(FAKE_TOOL)
            driver.chmod(0o755)
            for name in ("gsettings", "xfconf-query", "plasma-apply-colorscheme", "plasma-apply-wallpaperimage", "pcmanfm", "pcmanfm-qt", "omarchy", "hyprctl"):
                (binary / name).symlink_to(driver)
            env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(config), XDG_DATA_HOME=str(data), XDG_STATE_HOME=str(state), PATH=str(binary) + ":" + os.environ["PATH"], TOOL_LOG=str(base / "tools.jsonl"), REDLINE_NO_START="1", REDLINE_UPDATER_RUNNING="1")
            gtk = config / "gtk-4.0/gtk.css"
            gtk.parent.mkdir(parents=True)
            original = "/* Existing styling */\nbutton { border-radius: 7px; }\n"
            real_css = base / "original.css"
            real_css.write_text(original)
            gtk.symlink_to(real_css)
            fastfetch = config / "fastfetch/config.jsonc"
            fastfetch.parent.mkdir()
            fastfetch.write_text("// existing JSONC\n{}\n")
            command = ["bash", str(ROOT / "install.sh"), "--desktop", profile]
            first = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(real_css.read_text(), original)
            self.assertEqual(gtk.read_text().count("BEGIN REDLINE GTK"), 1)
            self.assertTrue(gtk.read_text().endswith(original))
            if profile == "omarchy":
                self.assertTrue((config / "omarchy/plugins/steven.bar/Bar.qml").exists())
                self.assertEqual(len(list((config / "omarchy/plugins").iterdir())), 9)
                if env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"):
                    calls = [json.loads(line) for line in (base / "tools.jsonl").read_text().splitlines()]
                    self.assertIn(["omarchy", "restart", "shell"], calls)
                restored = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--yes"], env=env, capture_output=True, text=True)
                self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
                self.assertEqual(fastfetch.read_text(), "// existing JSONC\n{}\n")
                self.assertTrue(gtk.is_symlink())
                self.assertFalse((config / "omarchy/themes/redline").exists())
                self.assertFalse((config / "omarchy/plugins/steven.bar").exists())
                self.assertFalse((config / "omarchy/hooks/post-boot.d/redline-autoupdate").exists())
                self.assertFalse((home / ".local/bin/redline-update").exists())
                return
            self.assertFalse((config / "omarchy").exists())
            portable = json.loads(fastfetch.read_text())
            self.assertNotIn("omarchy-", json.dumps(portable["modules"]))
            self.assertEqual(portable["logo"]["source"], str(config / "fastfetch/omarchy-eclipse.txt"))
            if profile == "generic" and shutil.which("fastfetch"):
                rendered = subprocess.run(["fastfetch", "--config", str(fastfetch), "--pipe", "true"], env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(rendered.returncode, 0, rendered.stderr)
            calls = [json.loads(line) for line in (base / "tools.jsonl").read_text().splitlines()] if (base / "tools.jsonl").exists() else []
            if profile == "kde":
                self.assertIn(["plasma-apply-colorscheme", "Redline"], calls)
                self.assertTrue((data / "color-schemes/Redline.colors").is_file())
            elif profile == "xfce":
                sets = [c for c in calls if c[0] == "xfconf-query" and "-s" in c]
                self.assertEqual(len(sets), 3)  # theme and both monitors
            elif profile in ("gnome", "budgie", "cinnamon", "mate"):
                self.assertTrue(any(c[:2] == ["gsettings", "set"] for c in calls))
            elif profile in ("lxqt", "lxde"):
                self.assertTrue(any(c[0].startswith("pcmanfm") for c in calls))
            else:
                self.assertIn("No native adapter", first.stdout)
            initial = next((state / "redline-desktop/backups").iterdir())
            second = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(gtk.read_text().count("BEGIN REDLINE GTK"), 1)
            backups = list((state / "redline-desktop/backups").iterdir())
            latest = next(b for b in backups if b != initial)
            subprocess.run(["python3", str(latest / "restore.py")], env=env, check=True, capture_output=True)
            self.assertEqual(gtk.read_text().count("BEGIN REDLINE GTK"), 1)
            subprocess.run(["python3", str(initial / "restore.py")], env=env, check=True, capture_output=True)
            self.assertTrue(gtk.is_symlink())
            self.assertEqual(gtk.read_text(), original)
            self.assertEqual(fastfetch.read_text(), "// existing JSONC\n{}\n")
            self.assertFalse((data / "redline-desktop").exists())

    def test_profiles_install_update_restore(self):
        for profile in installer.PROFILES[1:]:
            with self.subTest(profile=profile):
                self.exercise_profile(profile)


if __name__ == "__main__":
    unittest.main()
