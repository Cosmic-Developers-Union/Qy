#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$BUN_INSTALL" "$BUN_INSTALL_CACHE_DIR"
mkdir -p "${GOPATH:-$HOME/go}/bin"
.devcontainer/check-config.sh

if [ -n "${BUN_REGISTRY:-}" ]; then
  bun install --registry "$BUN_REGISTRY"
else
  bun install
fi

uv sync --all-extras
.devcontainer/check-config.sh
