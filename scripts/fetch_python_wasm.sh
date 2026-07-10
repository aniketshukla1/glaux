#!/usr/bin/env bash
# Install the CPython-WASI runtime that enables the WASM skill sandbox (v2).
#
# Downloads a pinned, checksum-verified python.wasm into <ATHENA_HOME>/python.wasm
# (default ~/.athena). Once present, sandbox execution runs skills inside a
# WebAssembly guest with no ambient authority — no env var needed (the backend
# defaults to "auto" and picks it up). See src/sandbox/WASM_V2.md.
#
# Source: VMware Labs webassembly-language-runtimes (CPython 3.12, wasi-sdk).
set -euo pipefail

VERSION="3.12.0"
TAG="3.12.0%2B20231211-040d5a6"
URL="https://github.com/vmware-labs/webassembly-language-runtimes/releases/download/python/${TAG}/python-${VERSION}.wasm"
SHA256="e5dc5a398b07b54ea8fdb503bf68fb583d533f10ec3f930963e02b9505f7a763"

ATHENA_HOME="${ATHENA_HOME:-$HOME/.athena}"
DEST="$ATHENA_HOME/python.wasm"

mkdir -p "$ATHENA_HOME"

if [ -f "$DEST" ] && command -v shasum >/dev/null 2>&1 \
   && [ "$(shasum -a 256 "$DEST" | awk '{print $1}')" = "$SHA256" ]; then
  echo "✓ python.wasm already installed and verified at $DEST"
  exit 0
fi

echo "Downloading CPython ${VERSION} WASI runtime (~25 MB)…"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
curl -fSL "$URL" -o "$TMP"

if command -v shasum >/dev/null 2>&1; then
  GOT="$(shasum -a 256 "$TMP" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  GOT="$(sha256sum "$TMP" | awk '{print $1}')"
else
  echo "!! no shasum/sha256sum available to verify the download" >&2
  GOT="$SHA256"  # can't verify; proceed
fi

if [ "$GOT" != "$SHA256" ]; then
  echo "✗ checksum mismatch: expected $SHA256, got $GOT" >&2
  exit 1
fi

mv "$TMP" "$DEST"
trap - EXIT
rm -f "$DEST.cwasm"  # drop any stale precompiled cache; it recompiles on first run
echo "✓ installed $DEST"
echo "  The WASM skill sandbox is now active (backend=auto). Verify: curl -s localhost:8000/api/health | grep sandbox"
