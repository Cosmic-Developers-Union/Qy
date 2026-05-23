FROM node:24 AS node
FROM oven/bun@sha256:e10577f0db68676a7024391c6e5cb4b879ebd17188ab750cf10024a6d700e5c4 AS bun
FROM ghcr.io/astral-sh/uv:latest AS uv
FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04

ARG APT_CACHE_PROXY
ARG BUN_REGISTRY
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=node /usr/local/ /usr/local/
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bunx /usr/local/bin/
COPY .devcontainer/entrypoint.sh /usr/local/bin/devcontainer-entrypoint

# use apt-cacher-ng
RUN if [ -n "$APT_CACHE_PROXY" ]; then \
    echo "Acquire::http::Proxy \"$APT_CACHE_PROXY\";" > /etc/apt/apt.conf.d/01proxy; \
    echo "Acquire::https::Proxy \"$APT_CACHE_PROXY\";" >> /etc/apt/apt.conf.d/01proxy; \
fi

RUN if [ -n "$BUN_REGISTRY" ]; then \
    mkdir -p /usr/local/etc; \
    echo "registry=$BUN_REGISTRY" > /usr/local/etc/npmrc; \
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

ENV BUN_REGISTRY="$BUN_REGISTRY" \
    BUN_INSTALL="/home/${USERNAME}/.bun" \
    BUN_INSTALL_CACHE_DIR="/home/${USERNAME}/.bun/install/cache" \
    HTTP_PROXY="" \
    HTTPS_PROXY="" \
    NPM_CONFIG_REGISTRY="$BUN_REGISTRY" \
    NO_PROXY="" \
    http_proxy="" \
    https_proxy="" \
    no_proxy="" \
    npm_config_registry="$BUN_REGISTRY"

RUN mkdir -p /home/$USERNAME/.bun/bin /home/$USERNAME/.bun/install/cache /home/$USERNAME/.bun/install/global && \
    chown -R $USERNAME:$(id -gn $USERNAME) /home/$USERNAME/.bun && \
    chmod +x /usr/local/bin/devcontainer-entrypoint

USER root

ENV PATH="/home/${USERNAME}/.bun/bin:${PATH}"
ENTRYPOINT ["/usr/local/bin/devcontainer-entrypoint"]
WORKDIR /workspace/Qy
