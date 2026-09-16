#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
lock="$root/ollama/runtimes.lock.json"
license="$root/LICENSES/ollama-MIT.txt"
notices="$root/ollama/NOTICES.md"

test -f "$license"
test -f "$notices"

license_sha="$(shasum -a 256 "$license" | awk '{print $1}')"
expected_license_sha="$(jq -r '.license.sha256' "$lock")"
test "$license_sha" = "$expected_license_sha"

jq -e '
  . as $root |
  .schemaVersion == "meow.runtime.ollama-runtimes.v1" and
  (.engineVersion | test("^[0-9]+\\.[0-9]+\\.[0-9]+$")) and
  (.publicTag == ("ollama-v" + .engineVersion)) and
  (.displayName | length > 0) and
  (.upstreamRepository == "https://github.com/ollama/ollama") and
  (.upstreamTag == ("v" + .engineVersion)) and
  (.license.url | test("^https://raw\\.githubusercontent\\.com/ollama/ollama/v")) and
  (.license.sha256 | test("^[0-9a-f]{64}$")) and
  .license.spdx == "MIT" and
  (.sources | type == "object") and
  (.sources | length > 0) and
  all(.sources[];
    (.url | test("^https://github\\.com/ollama/ollama/releases/download/v[0-9.]+/ollama-linux-(amd64|arm64)\\.tar\\.zst$")) and
    (.fileName | test("^ollama-linux-(amd64|arm64)\\.tar\\.zst$")) and
    (.sha256 | test("^[0-9a-f]{64}$")) and
    .sizeBytes > 0
  ) and
  (.packs | length > 0) and
  ([.packs[].id] | unique | length) == (.packs | length) and
  ([.packs[].fileName] | unique | length) == (.packs | length) and
  all(.packs[];
    (.id | test("^linux-(amd64|arm64)-(cpu|cuda)$")) and
    (.fileName == ("ollama-" + .id + ".tar.zst")) and
    (.source | in($root.sources)) and
    ((.transform == "identity") or (.transform == "exclude")) and
    (.require | length > 0) and
    all(.require[]; . == "bin/ollama" or startswith("lib/ollama/")) and
    all(.forbid[]; startswith("lib/ollama/")) and
    (if .transform == "exclude" then
      (.exclude | length > 0) and
      all(.exclude[]; . == "lib/ollama/cuda_v12" or . == "lib/ollama/cuda_v13")
     else
      (.exclude == null)
     end)
  )
' "$lock" >/dev/null
