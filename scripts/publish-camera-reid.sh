#!/usr/bin/env bash
set -euo pipefail

# Thin entry used by GitHub Actions. Packs from camera-reid.lock.json and
# optionally publishes an immutable GitHub Release.
publish="${1:-false}"
root="$(cd "$(dirname "$0")/.." && pwd)"
lock="$root/camera-reid.lock.json"

"$root/scripts/verify-camera-reid.sh"
version="$(jq -r '.version' "$lock")"
tag="$(jq -r '.publicTag' "$lock")"
name="$(jq -r '.displayName' "$lock")"
dist="$root/dist/camera-reid-$version"
rm -rf "$dist"
"$root/scripts/prepare-camera-reid.sh" "$dist"

if [[ "$publish" != "true" ]]; then
  echo "Prepared $dist without publishing"
  exit 0
fi

if gh release view "$tag" --repo mhome-ai/runtime-assets >/dev/null 2>&1; then
  echo "release already exists and will not be overwritten: $tag" >&2
  exit 1
fi

gh release create "$tag" "$dist"/* \
  --repo mhome-ai/runtime-assets \
  --title "$name" \
  --notes "Camera ReID OSNet ${version}. Immutable ONNX weights for the Camera node." \
  --latest=false
echo "Published https://github.com/mhome-ai/runtime-assets/releases/tag/$tag"
