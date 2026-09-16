#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
version="${1:?usage: bump-runtimes.sh <x.y.z>}"
exec python3 "$root/scripts/ollama/pack_runtimes.py" bump --root "$root" --version "$version"
