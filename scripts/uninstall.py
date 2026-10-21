#!/usr/bin/env python3
"""Uninstall Redline by replaying installation backups in reverse order."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yes', action='store_true', help='Skip the confirmation prompt')
    args = parser.parse_args()
    home = Path.home()
    state = Path(os.environ.get('XDG_STATE_HOME', home / '.local/state'))
    data = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    backups = sorted((state / 'redline-desktop/backups').glob('install-*/restore.json'),
                     key=lambda p: p.parent.stat().st_mtime_ns, reverse=True)
    backups = [p for p in backups if not (p.parent / 'uninstalled').exists()]
    if not backups:
        raise SystemExit('No complete installation backups found. Older Omarchy releases require manual recovery; see README. No settings changed.')
    manifests = [json.loads(p.read_text()) for p in backups]
    for path, manifest in zip(backups, manifests):
        if not path.with_name('restore.py').is_file():
            raise SystemExit('Missing restore script: ' + str(path.parent))
        for item in manifest['files']:
            if item['backup'] and not os.path.lexists(item['backup']):
                raise SystemExit('Missing backup: ' + item['backup'])
    print('Restore settings from before the first recorded installation (' + str(len(backups)) + ' backups).')
    print('Newer edits to affected files will be replaced. Current affected files will be saved first.')
    if any(m['desktop'] in ('kde', 'lxqt', 'lxde') for m in manifests):
        if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            raise SystemExit('Log out and run this command from a text console so desktop services cannot overwrite restored files.')
    if not args.yes and input('Uninstall Redline and restore saved settings? [y/N] ').strip().lower() not in ('y', 'yes'):
        return
    # Share the updater lock, so no install/repair can race the restore.
    from updater import lock
    with lock(state / 'redline-updater/install.lock') as acquired:
        if not acquired:
            raise SystemExit('A Redline install/update is running. Try again when it finishes.')
        recovery = Path(tempfile.mkdtemp(prefix='uninstall-', dir=backups[0].parent.parent))
        entries = {}
        for manifest in manifests:
            for item in manifest['files']:
                target = Path(item['path'])
                if str(target) in entries:
                    continue
                saved = recovery / str(len(entries))
                entries[str(target)] = str(saved) if os.path.lexists(target) else None
                if target.is_dir() and not target.is_symlink():
                    shutil.copytree(target, saved, symlinks=True)
                elif os.path.lexists(target):
                    shutil.copy2(target, saved, follow_symlinks=False)
        (recovery / 'files.json').write_text(json.dumps(entries, indent=2))
        print('Recovery copy:', recovery)
        updater = data / 'redline-updater/updater.py'
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                argv = (proc / 'cmdline').read_bytes().split(b'\0')
                if str(updater).encode() in argv and b'--watch' in argv:
                    os.kill(int(proc.name), signal.SIGTERM)
            except (OSError, PermissionError):
                pass
        for path in backups:
            subprocess.run([sys.executable, str(path.with_name('restore.py'))], check=True)
            (path.parent / 'uninstalled').touch()
        if any(m['desktop'] == 'omarchy' for m in manifests):
            subprocess.run(['hyprctl', 'reload'], check=False)
            subprocess.run(['omarchy', 'restart', 'shell'], check=False)
            subprocess.run(['omarchy', 'restart', 'terminal'], check=False)
        print('Redline uninstalled. Log out and back in to reload all restored settings.')


if __name__ == '__main__':
    main()
