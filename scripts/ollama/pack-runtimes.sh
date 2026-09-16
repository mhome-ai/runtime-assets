#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
output="${1:?usage: pack-runtimes.sh <output-dir> [pack-id]}"
pack_id="${2:-}"

args=(pack --root "$root" --output "$output")
if [[ -n "$pack_id" ]]; then
  args+=(--pack "$pack_id")
fi
exec python3 "$root/scripts/ollama/pack_runtimes.py" "${args[@]}"
