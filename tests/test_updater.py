import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("redline_updater", SOURCE / "scripts/updater.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / "config"), XDG_DATA_HOME=str(self.home / "data"), XDG_STATE_HOME=str(self.home / "state"), XDG_CURRENT_DESKTOP="custom", XDG_SESSION_DESKTOP="", DESKTOP_SESSION="", HYPRLAND_INSTANCE_SIGNATURE="", REDLINE_NO_START="1", REDLINE_UPDATER_RUNNING="1", REDLINE_SELECTED_COLOR="purple")
        self.environment.start()
        self.addCleanup(self.environment.stop)
        result = subprocess.run(["bash", str(SOURCE / "install.sh"), "--desktop", "generic"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.agent = updater.Updater()
        self.tag = self.agent.config["version"]
        self.colors = self.home / "data/redline-desktop/theme/colors.toml"

    def release(self, tag=None):
        tag = tag or self.tag
        base = f"https://github.com/{updater.REPO}/releases/download/{tag}/"
        return {"tag_name": tag, "draft": False, "prerelease": False, "assets": [{"name": name, "browser_download_url": base + name} for name in ("redline-desktop.zip", "SHA256SUMS")]}

    def test_repairs_modified_and_missing_files_from_cached_release(self):
        expected = self.colors.read_bytes()
        self.colors.write_text("damaged")
        (self.home / "config/gtk-4.0/gtk.css").unlink()
        with patch.object(updater, "fetch", return_value=json.dumps(self.release()).encode()):
            self.agent.check(scheduled=True)
        self.assertEqual(self.colors.read_bytes(), expected)
        self.assertTrue((self.home / "config/gtk-4.0/gtk.css").exists())
        self.assertEqual(updater.broken_files(updater.read_json(self.agent.config_path)), [])
        self.assertTrue(Path(self.agent.status["last_backup"]).exists())

    def test_future_release_installs_and_older_release_cannot_downgrade(self):
        tag = "v99.0.0"
        release = self.release(tag)
        buffer = io.BytesIO()
        current = self.agent.root / "releases" / self.tag
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in current.rglob("*"):
                if path.is_file():
                    name = str(path.relative_to(current))
                    contents = (tag + "\n").encode() if name == "VERSION" else path.read_bytes()
                    if name == "theme/colors.toml":
                        contents += b"\n# Future test release\n"
                    archive.writestr("redline-desktop/" + name, contents)
        archive_bytes = buffer.getvalue()
        def fetch(url, limit):
            if url == updater.API:
                return json.dumps(release).encode()
            if url.endswith("SHA256SUMS"):
                return (hashlib.sha256(archive_bytes).hexdigest() + "  redline-desktop.zip\n").encode()
            return archive_bytes
        with patch.object(updater, "fetch", side_effect=fetch):
            self.agent.check()
        self.assertEqual(updater.read_json(self.agent.config_path)["version"], tag)
        self.assertEqual(updater.read_json(self.agent.config_path)["color"], "purple")
        self.assertIn("Future test release", self.colors.read_text())
        with patch.object(updater, "fetch", return_value=json.dumps(self.release()).encode()):
            updater.Updater().check()
        self.assertEqual(updater.read_json(self.agent.config_path)["version"], tag)

    def test_bad_checksum_never_replaces_installed_files(self):
        expected = self.colors.read_bytes()
        release = self.release("v99.0.0")
        def fetch(url, limit):
            if url == updater.API:
                return json.dumps(release).encode()
            return ("0" * 64 + "  redline-desktop.zip\n").encode() if url.endswith("SHA256SUMS") else b"bad zip"
        with patch.object(updater, "fetch", side_effect=fetch):
            self.agent.check()
        self.assertEqual(self.colors.read_bytes(), expected)
        self.assertEqual(updater.read_json(self.agent.config_path)["version"], self.tag)
        self.assertIn("checksum mismatch", self.agent.status["last_network_error"])

    def test_partial_install_failure_restores_managed_files(self):
        expected = self.colors.read_bytes()
        def run(payload, profile, env):
            self.colors.write_text("partially installed")
            return subprocess.CompletedProcess([], 2, stdout="Simulated installer failure")
        with patch.object(updater, "run_installer", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "status 2"):
                self.agent.apply(self.agent.root / "releases" / self.tag, "generic")
        self.assertEqual(self.colors.read_bytes(), expected)
        self.assertEqual(updater.read_json(self.agent.config_path)["version"], self.tag)

    def test_scheduled_checks_respect_disable_inactive_theme_and_lock(self):
        helper = self.home / ".local/bin/redline-update"
        subprocess.run([str(helper), "--disable"], check=True, capture_output=True)
        self.assertFalse(updater.read_json(self.agent.config_path)["enabled"])
        self.assertIn("Hidden=true", (self.home / "config/autostart/redline-updater.desktop").read_text())
        subprocess.run([str(helper), "--enable"], check=True, capture_output=True)
        self.assertTrue(updater.read_json(self.agent.config_path)["enabled"])
        self.assertIn("Hidden=false", (self.home / "config/autostart/redline-updater.desktop").read_text())
        subprocess.run([str(helper), "--updates-only"], check=True, capture_output=True)
        self.assertFalse(updater.read_json(self.agent.config_path)["repair"])
        with patch.object(updater, "fetch") as network:
            self.agent.config["enabled"] = False
            self.agent.check(scheduled=True)
            self.agent.config["enabled"] = True
            css = self.home / "config/gtk-4.0/gtk.css"
            css.write_text("/* Deliberately disabled */\n")
            self.agent.check(scheduled=True)
            css.write_text("/* BEGIN REDLINE GTK */\n")
            with updater.lock(self.agent.state / "install.lock"):
                self.agent.check()
            network.assert_not_called()

    def test_offline_repair_uses_local_payload(self):
        expected = self.colors.read_bytes()
        self.colors.unlink()
        with patch.object(updater, "fetch", side_effect=OSError("offline")):
            self.agent.check()
        self.assertEqual(self.colors.read_bytes(), expected)

    def test_system_update_forces_release_check_and_reapply(self):
        self.agent.status["release_checked"] = time.time()
        with patch.object(updater, "fetch", return_value=json.dumps(self.release()).encode()) as network, patch.object(self.agent, "apply") as apply:
            self.agent.check(scheduled=True, repair=True, force_release=True)
            network.assert_called_once()
            apply.assert_called_once()

    def test_timed_out_installer_stops_process_group(self):
        process = unittest.mock.Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired("install", 300), ("stopped", None)]
        with patch.object(updater.subprocess, "Popen", return_value=process), patch.object(updater.os, "killpg") as kill:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                updater.run_installer(self.agent.root / "releases" / self.tag, "generic", dict(os.environ))
            kill.assert_called_once_with(12345, updater.signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
