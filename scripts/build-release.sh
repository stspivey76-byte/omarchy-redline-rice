#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
mkdir -p dist
git archive --format=zip --prefix=redline-desktop/ HEAD -o dist/redline-desktop.zip
(cd dist && sha256sum redline-desktop.zip > SHA256SUMS)
echo "Release files: dist/redline-desktop.zip and dist/SHA256SUMS"
