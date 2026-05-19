FROM node:24 AS node
FROM oven/bun:1 AS bun
FROM ghcr.io/astral-sh/uv:latest AS uv
FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=node /usr/local/ /usr/local/
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bunx /usr/local/bin/

# use apt-cacher-ng
RUN cat <<EOF > /etc/apt/apt.conf.d/01proxy
Acquire::http::Proxy "http://192.168.49.12:3142";
Acquire::https::Proxy "http://192.168.49.12:3142";
EOF
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
     apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    wget \
    unzip \
    ninja-build \
    llvm clang lld

# RUN npm install -g bun --registry=http://192.168.49.12:4873 \
RUN cat <<EOF > $HOME/.bunfig.toml
[install]
registry = "http://192.168.49.12:4873"
EOF
RUN --mount=type=cache,target=$HOME/.bun,sharing=locked \
  bun add -g @anthropic-ai/claude-code