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
require_cmd go
require_cmd gofmt
require_cmd clang
require_cmd clang++
require_cmd clangd
require_cmd clang-format
require_cmd clang-tidy
require_cmd llc
require_cmd lld
require_cmd ld.lld
require_cmd lldb
require_cmd llvm-ar
require_cmd llvm-config
require_cmd llvm-nm
require_cmd llvm-ranlib

current_user="$(id -un)"
expected_user="${REMOTE_USER:-$current_user}"
home_dir="${HOME:-/home/$current_user}"
bun_install="${BUN_INSTALL:-$home_dir/.bun}"
bun_cache="${BUN_INSTALL_CACHE_DIR:-$bun_install/install/cache}"
go_root="${GOROOT:-/usr/local/go}"
go_path="${GOPATH:-$home_dir/go}"
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

if [ "$go_root" != "/usr/local/go" ]; then
  fail "GOROOT is $go_root, expected /usr/local/go"
fi

if [ "$go_path" != "$home_dir/go" ]; then
  fail "GOPATH is $go_path, expected $home_dir/go"
fi

if [ ! -x "$go_root/bin/go" ]; then
  fail "missing executable: $go_root/bin/go"
fi

if [ ! -x "$go_root/bin/gofmt" ]; then
  fail "missing executable: $go_root/bin/gofmt"
fi

if [ ! -x /usr/local/bin/go ]; then
  fail "missing executable: /usr/local/bin/go"
fi

if [ ! -x /usr/local/bin/gofmt ]; then
  fail "missing executable: /usr/local/bin/gofmt"
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

if [ ! -d "$go_path" ]; then
  fail "GOPATH directory does not exist: $go_path"
elif [ ! -w "$go_path" ]; then
  fail "GOPATH is not writable: $go_path"
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

case ":$PATH:" in
  *":$go_root/bin:"*) ;;
  *) fail "PATH does not include $go_root/bin" ;;
esac

case ":$PATH:" in
  *":$go_path/bin:"*) ;;
  *) fail "PATH does not include $go_path/bin" ;;
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

if [ "${GOPROXY:-}" != "https://goproxy.cn,direct" ]; then
  fail "GOPROXY should be https://goproxy.cn,direct, got: ${GOPROXY:-}"
fi

if [ "$(go env GOPROXY)" != "https://goproxy.cn,direct" ]; then
  fail "go env GOPROXY does not match https://goproxy.cn,direct"
fi

if [ "${GOSUMDB:-}" != "sum.golang.google.cn" ]; then
  fail "GOSUMDB should be sum.golang.google.cn, got: ${GOSUMDB:-}"
fi

if [ "$(go env GOSUMDB)" != "sum.golang.google.cn" ]; then
  fail "go env GOSUMDB does not match sum.golang.google.cn"
fi

if [ "${GOTOOLCHAIN:-}" != "local" ]; then
  fail "GOTOOLCHAIN should be local, got: ${GOTOOLCHAIN:-}"
fi

if [ "$(go env GOTOOLCHAIN)" != "local" ]; then
  fail "go env GOTOOLCHAIN does not match local"
fi

if [ "$(go env GOROOT)" != "$go_root" ]; then
  fail "go env GOROOT does not match GOROOT"
fi

if [ "$(go env GOPATH)" != "$go_path" ]; then
  fail "go env GOPATH does not match GOPATH"
fi

if [ "${QY_LLC:-}" != "llc" ]; then
  fail "QY_LLC should be llc, got: ${QY_LLC:-}"
fi

if [ "${QY_CC:-}" != "clang" ]; then
  fail "QY_CC should be clang, got: ${QY_CC:-}"
fi

if [ "${QY_LLVM_DIR:-}" != "/usr/bin" ]; then
  fail "QY_LLVM_DIR should be /usr/bin, got: ${QY_LLVM_DIR:-}"
fi

if [ "${LLVM_CONFIG:-}" != "llvm-config" ]; then
  fail "LLVM_CONFIG should be llvm-config, got: ${LLVM_CONFIG:-}"
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
