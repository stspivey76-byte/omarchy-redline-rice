#!/usr/bin/env bash
set -euo pipefail
for command in curl python3 sha256sum; do
  command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done
release_url="https://github.com/stspivey76-byte/omarchy-redline-rice/releases/latest/download"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
curl --fail --location --retry 3 "$release_url/redline-desktop.zip" -o "$work_dir/redline-desktop.zip"
curl --fail --location --retry 3 "$release_url/SHA256SUMS" -o "$work_dir/SHA256SUMS"
(cd "$work_dir" && sha256sum --check SHA256SUMS)
python3 - "$work_dir" <<'PYTHON'
from pathlib import Path
import sys
import zipfile
root = Path(sys.argv[1])
with zipfile.ZipFile(root / "redline-desktop.zip") as archive:
    archive.extractall(root)
PYTHON
bash "$work_dir/redline-desktop/install.sh" "$@"
