#!/usr/bin/env sh
set -eu

REMOTE_USER="${REMOTE_USER:-ge}"

unset HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy

if ! getent hosts host.docker.internal >/dev/null 2>&1; then
  gateway="$(ip route show default 2>/dev/null | awk '{print $3; exit}')"
  if [ -n "$gateway" ]; then
    echo "$gateway host.docker.internal" >> /etc/hosts
  fi
fi

if [ "$(id -u)" = "0" ]; then
  user_home="$(getent passwd "$REMOTE_USER" | cut -d: -f6)"
  user_group="$(id -gn "$REMOTE_USER")"
  bun_install="${BUN_INSTALL:-$user_home/.bun}"
  bun_cache="${BUN_INSTALL_CACHE_DIR:-$bun_install/install/cache}"

  mkdir -p "$bun_install/bin" "$bun_install/install/global" "$bun_cache"
  chown -R "$REMOTE_USER:$user_group" "$bun_install"

  export HOME="$user_home"
  export USER="$REMOTE_USER"
  export LOGNAME="$REMOTE_USER"
  exec runuser --preserve-environment -u "$REMOTE_USER" -- "$@"
fi

exec "$@"
