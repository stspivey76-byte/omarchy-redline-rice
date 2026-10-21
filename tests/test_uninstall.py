"""Verify uninstall restores the original baseline across repeated installations."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class UninstallTests(unittest.TestCase):
    def test_repeated_install_restores_symlink_files_and_removes_updater(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=str(home / 'config'),
                       XDG_DATA_HOME=str(home / 'data'), XDG_STATE_HOME=str(home / 'state'),
                       REDLINE_NO_START='1', REDLINE_UPDATER_RUNNING='1')
            config = home / 'config'
            css = config / 'gtk-4.0/gtk.css'
            css.parent.mkdir(parents=True)
            original = home / 'original.css'
            original.write_text('/* original */\n')
            css.symlink_to(original)
            ff = config / 'fastfetch/config.jsonc'
            ff.parent.mkdir()
            ff.write_text('// original fastfetch\n{}\n')
            for _ in range(2):
                result = subprocess.run(['bash', str(ROOT / 'install.sh'), '--desktop', 'generic'], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(home / '.local/bin/redline-uninstall'), '--yes'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(css.is_symlink())
            self.assertEqual(css.resolve(), original)
            self.assertEqual(original.read_text(), '/* original */\n')
            self.assertEqual(ff.read_text(), '// original fastfetch\n{}\n')
            for target in ('data/redline-updater', 'data/redline-desktop', '.local/bin/redline-update', '.local/bin/redline-uninstall', 'config/autostart/redline-updater.desktop'):
                self.assertFalse((home / target).exists(), target)
            self.assertEqual(len(list((home / 'state/redline-desktop/backups').glob('install-*/uninstalled'))), 2)

    def test_no_backup_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp, XDG_STATE_HOME=tmp)
            result = subprocess.run(['bash', str(ROOT / 'uninstall.sh'), '--yes'], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No settings changed', result.stderr)
