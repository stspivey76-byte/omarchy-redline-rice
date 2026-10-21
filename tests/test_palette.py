import colorsys
import errno
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shlex
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("palette", SOURCE / "scripts/palette.py")
palette = importlib.util.module_from_spec(spec)
spec.loader.exec_module(palette)


class PaletteTests(unittest.TestCase):
    def test_manual_installs_require_menu_and_reject_color_flag(self):
        with patch.dict(os.environ, {}, clear=True), patch("builtins.open", side_effect=OSError("no terminal")):
            with self.assertRaisesRegex(SystemExit, "menu"):
                palette.choose_color("red", "generic")
        import subprocess
        env = dict(os.environ)
        env.pop("REDLINE_UPDATER_RUNNING", None)
        result = subprocess.run(["bash", str(SOURCE / "install.sh"), "--color", "blue"], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_all_six_palettes_preserve_plugins_and_select_wallpaper(self):
        with tempfile.TemporaryDirectory() as tmp:
            for color in palette.COLORS:
                with self.subTest(color=color):
                    staged = palette.stage(SOURCE, Path(tmp) / color, color)
                    image = "tux-crimson-eclipse.png" if color == "red" else f"tux-{color}-eclipse.png"
                    self.assertEqual((staged / "theme/backgrounds/tux-crimson-eclipse.png").read_bytes(), (SOURCE / "theme/backgrounds" / image).read_bytes())
                    self.assertEqual((staged / "shell.json").read_bytes(), (SOURCE / "shell.json").read_bytes())
                    self.assertEqual(len(list((staged / "plugins").iterdir())), 10)
                    seed = palette.COLORS[color][1:]
                    hue = colorsys.rgb_to_hsv(*(int(seed[i:i + 2], 16) / 255 for i in (0, 2, 4)))[0]
                    for original in (SOURCE / "plugins").rglob("*.qml"):
                        changed = staged / original.relative_to(SOURCE)
                        self.assertEqual(palette.HEX.sub("#COLOR", original.read_text()), palette.HEX.sub("#COLOR", changed.read_text()))
                        for match in palette.HEX.finditer(changed.read_text()):
                            value = match[0][-6:]
                            h, s, v = colorsys.rgb_to_hsv(*(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)))
                            if s > 0.25 and v > 0.2:
                                self.assertLess(min(abs(h - hue), 1 - abs(h - hue)), 0.025, f"{color}: {changed}: {match[0]}")
                    css = (staged / "theme/gtk-4.0/gtk.css").read_text()
                    self.assertIn("--accent-fg-color: #080406;" if color in ("yellow", "green") else "--accent-fg-color: #ffffff;", css)

    def test_picker_accepts_number_name_default_and_cancel(self):
        for inputs, expected in ((["2\n"], "blue"), (["pink\n"], "pink"), (["\n"], "purple"), (["invalid\n", "6\n"], "purple")):
            terminal = Mock()
            terminal.readline.side_effect = inputs
            self.assertEqual(palette.picker("purple", "gnome", terminal), expected)
        terminal = Mock()
        terminal.readline.return_value = "q\n"
        with self.assertRaises(SystemExit):
            palette.picker("red", "gnome", terminal)

    def test_piped_installer_reads_color_from_controlling_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=str(home / "config"), XDG_DATA_HOME=str(home / "data"), XDG_STATE_HOME=str(home / "state"), REDLINE_NO_START="1")
            for name in ("REDLINE_NONINTERACTIVE", "REDLINE_UPDATER_RUNNING", "REDLINE_SELECTED_COLOR", "REDLINE_BASE_SOURCE"):
                env.pop(name, None)
            script = "bash " + shlex.quote(str(SOURCE / "install.sh")) + " --desktop generic --no-auto-update"
            command = "printf '%s\\n' " + shlex.quote(script) + " | bash"
            pid, fd = pty.fork()
            if pid == 0:
                os.execve("/bin/bash", ["bash", "-c", command], env)
            transcript = b""
            answered = False
            status = None
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if select.select([fd], [], [], 0.1)[0]:
                        try:
                            output = os.read(fd, 65536)
                        except OSError as error:
                            if error.errno == errno.EIO:
                                break
                            raise
                        if not output:
                            break
                        transcript += output
                        if b"Choose 1" in transcript and not answered:
                            os.write(fd, b"2\n")
                            answered = True
                    finished, child_status = os.waitpid(pid, os.WNOHANG)
                    if finished:
                        status = child_status
                        break
                else:
                    self.fail("Piped installer did not finish: " + transcript.decode(errors="replace"))
                if status is None:
                    _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0, transcript.decode(errors="replace"))
                self.assertTrue(answered)
                saved = json.loads((home / "data/redline-updater/config.json").read_text())
                self.assertEqual(saved["color"], "blue")
                self.assertFalse(saved["enabled"])
                self.assertEqual((home / "data/redline-desktop/theme/backgrounds/tux-crimson-eclipse.png").read_bytes(), (SOURCE / "theme/backgrounds/tux-blue-eclipse.png").read_bytes())
            finally:
                os.close(fd)
                if status is None:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)


if __name__ == "__main__":
    unittest.main()
