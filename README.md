# MeowCore runtime assets

Public, versioned binary assets downloaded by MeowCore.

G2P releases are built and tested from the private source repository. This repository stores only the native binaries and their checksums, SBOMs, source-input receipts, build metadata, and license notices. It does not build from embedded source archives or publish Python/eSpeak bundles.

Kokoro acoustic models and voice packs are published as separate, independently
downloadable English and Chinese releases. Each release mirrors bytes pinned by
SHA-256 from the upstream ONNX exporter and includes Apache-2.0 model terms,
MIT exporter attribution, a source receipt, notices, and checksums. The private release repository
contains native G2P source and build logic. Model mirroring is intentionally
performed here with this repository's short-lived Actions token, so it needs no
cross-repository personal access token.

## Ollama Linux runtimes

Linux Ollama CPU and CUDA archives are packed here from the official GitHub
release pinned in `ollama/runtimes.lock.json`. Scripts live in `scripts/ollama/`;
the published tarballs, MIT license, notices, and SHA-256 list go on the
immutable GitHub Release `ollama-v<engineVersion>`. Git does not store the
multi-gigabyte archives.

CPU packs drop `lib/ollama/cuda_v12` and `cuda_v13`. CUDA packs are the official
archives, renamed, and keep both CUDA 12 and 13 so Ollama can choose at runtime.
ROCm and MLX extras are not published. ARM CUDA is the SBSA/server build, not
Jetson. Darwin continues to use the official `ollama-darwin.tgz` from Ollama.

The lockfile is the version pin. Official Ollama `v0.32.14` becomes our
Release `ollama-v0.32.14`. A new upstream version needs a new lock commit and a
new Release; tags are never overwritten.

Point the lock at a new official version (checksums come from the official
GitHub `sha256sum.txt`):

```bash
scripts/ollama/bump-runtimes.sh 0.33.0
```

Official archives are downloaded by the packer into `ollama/upstream/` (gitignored).
If a file is already there and matches the pinned SHA-256, it is reused.

Validate without downloading the multi-gigabyte archives:

```bash
scripts/ollama/verify-runtimes.sh
scripts/ollama/pack-runtimes.test.sh
```

Optional local pack after bump. CI is what publishes; this is a smoke check.
Cached official tarballs stay in `ollama/upstream/`.

```bash
scripts/ollama/pack-runtimes.sh dist
```

Commit the lock, merge to `main`, then run workflow `Release Ollama Linux
runtimes`. That job reads the lock, fills `ollama/upstream/` as needed, packs
CPU/CUDA, and uploads GitHub Release `ollama-v<engineVersion>`. After it
finishes, copy `SHA256SUMS` into the desktop runtime catalog.
