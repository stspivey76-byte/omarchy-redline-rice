#!/usr/bin/env bash
set -euo pipefail
for command in omarchy python3; do
  command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="$HOME/.config/omarchy"
mkdir -p "${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/backups"
backup_dir="$(mktemp -d "${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/backups/redline-desktop-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
mkdir -p "$config_dir/themes" "$config_dir/plugins" "$backup_dir/plugins"
for item in shell.json shell.toml themes/redline; do
  if [[ -e "$config_dir/$item" ]]; then
    mkdir -p "$backup_dir/$(dirname "$item")"
    cp -a "$config_dir/$item" "$backup_dir/$item"
  fi
done
for plugin in "$source_dir"/plugins/*; do
  name="$(basename "$plugin")"
  [[ ! -e "$config_dir/plugins/$name" ]] || cp -a "$config_dir/plugins/$name" "$backup_dir/plugins/"
  mkdir -p "$config_dir/plugins/$name"
  cp -a "$plugin/." "$config_dir/plugins/$name/"
done
mkdir -p "$config_dir/themes/redline"
cp -a "$source_dir/theme/." "$config_dir/themes/redline/"
cp "$source_dir/shell.json" "$source_dir/shell.toml" "$config_dir/"
# Keep the previous Fastfetch configuration and logo alongside the Omarchy backup.
fastfetch_dir="$HOME/.config/fastfetch"
mkdir -p "$fastfetch_dir" "$backup_dir/fastfetch"
for item in config.jsonc omarchy-eclipse.txt; do
  if [[ -e "$fastfetch_dir/$item" ]]; then
    cp -a "$fastfetch_dir/$item" "$backup_dir/fastfetch/$item"
  fi
done
cp "$source_dir/fastfetch/omarchy-eclipse.txt" "$fastfetch_dir/"
python3 - "$source_dir/fastfetch/config.jsonc" "$fastfetch_dir" <<'PYTHON'
import json
from pathlib import Path
import sys
config = json.loads(Path(sys.argv[1]).read_text())
destination = Path(sys.argv[2])
config["logo"]["source"] = str(destination / "omarchy-eclipse.txt")
(destination / "config.jsonc").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
PYTHON
# Preserve GTK files and any previous Redline hook before enabling color overrides.
for version in 3.0 4.0; do
  gtk_dir="$HOME/.config/gtk-$version"
  if [[ -e "$gtk_dir/gtk.css" || -L "$gtk_dir/gtk.css" ]]; then
    mkdir -p "$backup_dir/gtk-$version"
    cp -a "$gtk_dir/gtk.css" "$backup_dir/gtk-$version/"
  fi
done
hook_path="$config_dir/hooks/theme-set.d/redline-gtk"
if [[ -e "$hook_path" ]]; then
  mkdir -p "$backup_dir/hooks/theme-set.d"
  cp -a "$hook_path" "$backup_dir/hooks/theme-set.d/"
fi
omarchy hook install theme-set "$source_dir/hooks/redline-gtk"
omarchy theme set redline
# Also apply explicitly for environments that defer theme hooks.
bash "$hook_path" redline
omarchy theme bg set "$config_dir/themes/redline/backgrounds/tux-crimson-eclipse.png"
# QML can retain compiled copies of widgets after a rescan. Restart the shell
# after installing colored plugin code so every widget uses the selected hue.
if [[ -n ${WAYLAND_DISPLAY:-}${DISPLAY:-} ]]; then
  if ! restart_output="$(omarchy restart shell 2>&1)"; then
    shell_ready=0
    for ((attempt = 0; attempt < 20; attempt++)); do
      if OMARCHY_SHELL_IPC_TIMEOUT=0.5s omarchy-shell shell ping >/dev/null 2>&1; then
        shell_ready=1
        break
      fi
      sleep 0.5
    done
    if (( ! shell_ready )); then
      echo "NOTICE: Shell reload did not finish. Log out and back in to load all plugin colors." >&2
      echo "$restart_output" >&2
    fi
  fi
fi
echo "Installed. Previous configuration saved in: $backup_dir"
