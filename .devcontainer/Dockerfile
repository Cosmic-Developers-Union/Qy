FROM node:24 AS node
FROM oven/bun:1 AS bun
FROM ghcr.io/astral-sh/uv:latest AS uv
FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04

ARG APT_CACHE_PROXY
ARG BUN_REGISTRY

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=node /usr/local/ /usr/local/
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bunx /usr/local/bin/

# use apt-cacher-ng
RUN if [ -n "$APT_CACHE_PROXY" ]; then \
    echo "Acquire::http::Proxy \"$APT_CACHE_PROXY\";" > /etc/apt/apt.conf.d/01proxy; \
    echo "Acquire::https::Proxy \"$APT_CACHE_PROXY\";" >> /etc/apt/apt.conf.d/01proxy; \
fi

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

ARG USERNAME=ge
ARG USER_UID=1000
ARG USER_GID=1000

RUN set -eux; \
    if id vscode >/dev/null 2>&1; then \
        usermod -l ge -d /home/ge -m vscode; \
    fi; \
    if getent group vscode >/dev/null; then \
        groupmod -n ge vscode; \
    fi; \
    mkdir -p /home/ge; \
    chown -R ge:$(id -gn ge) /home/ge

RUN usermod -s /usr/bin/zsh $USERNAME

RUN if [ -n "$BUN_REGISTRY" ]; then \
    echo "[install]" > $HOME/.bunfig.toml; \
    echo "registry = \"$BUN_REGISTRY\"" >> $HOME/.bunfig.toml; \
fi

USER $USERNAME

RUN --mount=type=cache,target=$HOME/.bun,sharing=locked \
  bun add -g @anthropic-ai/claude-code

ENV PATH="${HOME}/.bun/bin:${PATH}"
WORKDIR /workspace/Qy