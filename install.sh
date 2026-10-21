#!/usr/bin/env bash
set -euo pipefail
command -v python3 >/dev/null || { echo "Missing dependency: python3" >&2; exit 1; }
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$source_dir/scripts/install-desktop.py" "$@"
