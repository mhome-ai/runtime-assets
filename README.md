# MeowCore runtime assets

Public, versioned binary assets downloaded by MeowCore.

G2P releases are built and tested from the private source repository. This repository stores only the native binaries and their checksums, SBOMs, source-input receipts, build metadata, and license notices. It does not build from embedded source archives or publish Python/eSpeak bundles.

Kokoro acoustic models and voice packs are published as separate, independently
downloadable English and Chinese releases. Each release mirrors bytes pinned by
SHA-256 from the upstream ONNX exporter and includes an Apache-2.0/MIT license
bundle, source receipt, notices, and checksums. The private release repository
contains the validation workflow and manifest; this public repository is only
the immutable distribution endpoint.
