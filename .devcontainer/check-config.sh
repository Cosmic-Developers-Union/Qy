#!/usr/bin/env bash
set -euo pipefail

errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

require_cmd bun
require_cmd uv
require_cmd getent

current_user="$(id -un)"
expected_user="${REMOTE_USER:-$current_user}"
home_dir="${HOME:-/home/$current_user}"
bun_install="${BUN_INSTALL:-$home_dir/.bun}"
bun_cache="${BUN_INSTALL_CACHE_DIR:-$bun_install/install/cache}"
workspace="${WORKSPACE_FOLDER:-/workspaces/Qy}"

if [ "$current_user" != "$expected_user" ]; then
  fail "current user is $current_user, expected $expected_user"
fi

if [ "$home_dir" != "/home/$current_user" ]; then
  fail "HOME is $home_dir, expected /home/$current_user"
fi

if [ "$bun_install" != "$home_dir/.bun" ]; then
  fail "BUN_INSTALL is $bun_install, expected $home_dir/.bun"
fi

if [ "$bun_cache" != "$bun_install/install/cache" ]; then
  fail "BUN_INSTALL_CACHE_DIR is $bun_cache, expected $bun_install/install/cache"
fi

if [ ! -d "$bun_install" ]; then
  fail "BUN_INSTALL directory does not exist: $bun_install"
elif [ ! -w "$bun_install" ]; then
  fail "BUN_INSTALL is not writable: $bun_install"
fi

if [ ! -d "$bun_cache" ]; then
  fail "Bun cache directory does not exist: $bun_cache"
elif [ ! -w "$bun_cache" ]; then
  fail "Bun cache directory is not writable: $bun_cache"
fi

if [ ! -d "$workspace" ]; then
  fail "workspace directory does not exist: $workspace"
fi

for path in "$workspace/.venv" "$workspace/node_modules"; do
  if [ ! -d "$path" ]; then
    fail "devcontainer volume directory does not exist: $path"
  elif [ ! -w "$path" ]; then
    fail "devcontainer volume directory is not writable: $path"
  fi
done

case ":$PATH:" in
  *":$bun_install/bin:"*) ;;
  *) fail "PATH does not include $bun_install/bin" ;;
esac

if ! getent hosts host.docker.internal >/dev/null 2>&1; then
  fail "host.docker.internal does not resolve"
fi

for name in HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy; do
  value="${!name-}"
  if [ -n "$value" ]; then
    fail "$name should be empty after container startup, got: $value"
  fi
done

if [ -z "${BUN_REGISTRY:-}" ]; then
  fail "BUN_REGISTRY is empty"
else
  case "$BUN_REGISTRY" in
    *127.0.0.1*|*localhost*) fail "BUN_REGISTRY must not point at container-local address: $BUN_REGISTRY" ;;
  esac
fi

if [ "${NPM_CONFIG_REGISTRY:-}" != "${BUN_REGISTRY:-}" ]; then
  fail "NPM_CONFIG_REGISTRY does not match BUN_REGISTRY"
fi

if [ "${npm_config_registry:-}" != "${BUN_REGISTRY:-}" ]; then
  fail "npm_config_registry does not match BUN_REGISTRY"
fi

if [ -f /usr/local/etc/npmrc ]; then
  if ! grep -qx "registry=${BUN_REGISTRY:-}" /usr/local/etc/npmrc; then
    fail "/usr/local/etc/npmrc registry does not match BUN_REGISTRY"
  fi
fi

bun_version="$(bun --version)"
if [ "$bun_version" != "1.3.14" ]; then
  fail "unexpected Bun version: $bun_version"
fi

if [ ! -d "$home_dir/.claude" ]; then
  warn "$home_dir/.claude is not mounted"
fi

if [ ! -f "$home_dir/.claude.json" ]; then
  warn "$home_dir/.claude.json is not mounted"
elif [ -w "$home_dir/.claude.json" ]; then
  fail "$home_dir/.claude.json should be mounted read-only"
fi

if [ "$errors" -gt 0 ]; then
  exit 1
fi

printf 'devcontainer config: OK\n'
