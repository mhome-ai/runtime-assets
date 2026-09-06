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
