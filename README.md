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

Validate without downloading upstream:

```bash
scripts/ollama/verify-runtimes.sh
scripts/ollama/pack-runtimes.test.sh
```

Pack from the pinned official archives (optional local cache of those files):

```bash
OLLAMA_SOURCE_DIR=/path/to/official-tars scripts/ollama/pack-runtimes.sh dist
```

Publish with workflow `Release Ollama Linux runtimes`. Existing release tags are
never overwritten. After a release, copy the published SHA-256 values into the
desktop runtime catalog.
