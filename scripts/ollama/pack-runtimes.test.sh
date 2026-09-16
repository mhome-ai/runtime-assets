#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/ollama-runtime-test.XXXXXX")"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

python3 - "$root" "$tmp" <<'PY'
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path
import sys

root = Path(sys.argv[1])
tmp = Path(sys.argv[2])
sys.path.insert(0, str(root / "scripts/ollama"))
import pack_runtimes

fixture_root = tmp / "root"
source_dir = tmp / "source"
output = tmp / "out"
source_tree = tmp / "tree"

(source_tree / "bin").mkdir(parents=True)
(source_tree / "lib/ollama/cuda_v12").mkdir(parents=True)
(source_tree / "lib/ollama/cuda_v13").mkdir(parents=True)
(source_tree / "lib/ollama/vulkan").mkdir(parents=True)
(source_tree / "bin/ollama").write_bytes(b"ollama-bin")
(source_tree / "lib/ollama/libggml.so").write_bytes(b"cpu")
(source_tree / "lib/ollama/cuda_v12/libggml-cuda.so").write_bytes(b"cuda12")
(source_tree / "lib/ollama/cuda_v13/libggml-cuda.so").write_bytes(b"cuda13")
(source_tree / "lib/ollama/vulkan/libggml-vulkan.so").write_bytes(b"vk")
os.chmod(source_tree / "bin/ollama", 0o755)

source_dir.mkdir()
archive = source_dir / "ollama-linux-amd64.tar.zst"
pack_runtimes.write_tree_archive(source_tree, archive)
digest = pack_runtimes.sha256_file(archive)
size = archive.stat().st_size

lock = {
    "schemaVersion": "meow.runtime.ollama-runtimes.v1",
    "engineVersion": "0.0.0",
    "publicTag": "ollama-v0.0.0",
    "displayName": "fixture",
    "upstreamRepository": "https://github.com/ollama/ollama",
    "upstreamTag": "v0.0.0",
    "license": json.loads((root / "ollama/runtimes.lock.json").read_text())["license"],
    "sources": {
        "linux-amd64": {
            "url": "https://github.com/ollama/ollama/releases/download/v0.0.0/ollama-linux-amd64.tar.zst",
            "fileName": "ollama-linux-amd64.tar.zst",
            "sha256": digest,
            "sizeBytes": size,
        }
    },
    "packs": [
        {
            "id": "linux-amd64-cpu",
            "source": "linux-amd64",
            "fileName": "ollama-linux-amd64-cpu.tar.zst",
            "transform": "exclude",
            "exclude": ["lib/ollama/cuda_v12", "lib/ollama/cuda_v13"],
            "require": ["bin/ollama"],
            "forbid": [
                "lib/ollama/cuda_v12",
                "lib/ollama/cuda_v13",
                "lib/ollama/rocm",
                "lib/ollama/mlx",
            ],
        },
        {
            "id": "linux-amd64-cuda",
            "source": "linux-amd64",
            "fileName": "ollama-linux-amd64-cuda.tar.zst",
            "transform": "identity",
            "require": ["bin/ollama", "lib/ollama/cuda_v12", "lib/ollama/cuda_v13"],
            "forbid": ["lib/ollama/rocm", "lib/ollama/mlx"],
        },
    ],
}

(fixture_root / "ollama").mkdir(parents=True)
(fixture_root / "LICENSES").mkdir(parents=True)
shutil.copy2(root / "LICENSES/ollama-MIT.txt", fixture_root / "LICENSES/ollama-MIT.txt")
shutil.copy2(root / "ollama/NOTICES.md", fixture_root / "ollama/NOTICES.md")
(fixture_root / "ollama/runtimes.lock.json").write_text(json.dumps(lock, indent=2) + "\n")

os.environ["OLLAMA_SOURCE_DIR"] = str(source_dir)
pack_runtimes.pack_runtimes(fixture_root, output, None)

cpu = output / "ollama-linux-amd64-cpu.tar.zst"
cuda = output / "ollama-linux-amd64-cuda.tar.zst"
cpu_names = pack_runtimes.list_members(cpu)
cuda_names = pack_runtimes.list_members(cuda)

assert any(name == "bin/ollama" or name.endswith("bin/ollama") for name in cpu_names), cpu_names
assert any("vulkan" in name for name in cpu_names), cpu_names
assert not any("cuda_v" in name for name in cpu_names), cpu_names
assert pack_runtimes.sha256_file(cuda) == digest
assert any("cuda_v12" in name for name in cuda_names)
assert any("cuda_v13" in name for name in cuda_names)
assert (output / "LICENSE").is_file()
assert (output / "SHA256SUMS").is_file()
print("ok")
PY
