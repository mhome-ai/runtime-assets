#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
version="${1:?usage: bump-runtimes.sh <x.y.z>}"

args=(bump --root "$root" --version "$version")
if [[ -n "${OLLAMA_LICENSE_FILE:-}" ]]; then
  args+=(--license-file "$OLLAMA_LICENSE_FILE")
fi
exec python3 "$root/scripts/ollama/pack_runtimes.py" "${args[@]}"
