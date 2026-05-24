FROM node:24 AS node
FROM oven/bun@sha256:e10577f0db68676a7024391c6e5cb4b879ebd17188ab750cf10024a6d700e5c4 AS bun
FROM ghcr.io/astral-sh/uv:latest AS uv
FROM golang:1.26.3-bookworm AS golang
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
COPY --from=golang /usr/local/go/ /usr/local/go/

RUN set -eux; \
    test -x /usr/local/go/bin/go; \
    test -x /usr/local/go/bin/gofmt; \
    ln -sf /usr/local/go/bin/go /usr/local/bin/go; \
    ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt; \
    go version

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
    llvm \
    llvm-dev \
    clang \
    clangd \
    clang-format \
    clang-tidy \
    lld \
    lldb \
    libclang-dev

COPY .devcontainer/entrypoint.sh /usr/local/bin/devcontainer-entrypoint
COPY .devcontainer/check-config.sh /usr/local/bin/devcontainer-check-config

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

RUN set -eux; \
    if [ "$USERNAME" != "vscode" ] && id vscode >/dev/null 2>&1; then \
        usermod -l "$USERNAME" -d "/home/$USERNAME" -m vscode; \
    fi; \
    if [ "$USERNAME" != "vscode" ] && getent group vscode >/dev/null; then \
        groupmod -n "$USERNAME" vscode; \
    fi; \
    if ! id "$USERNAME" >/dev/null 2>&1; then \
        useradd -m -s /usr/bin/zsh "$USERNAME"; \
    fi; \
    mkdir -p "/home/$USERNAME"; \
    chown -R "$USERNAME:$(id -gn "$USERNAME")" "/home/$USERNAME"

RUN usermod -s /usr/bin/zsh $USERNAME

ENV BUN_REGISTRY="$BUN_REGISTRY" \
    BUN_INSTALL="/home/${USERNAME}/.bun" \
    BUN_INSTALL_CACHE_DIR="/home/${USERNAME}/.bun/install/cache" \
    GOROOT="/usr/local/go" \
    GOPATH="/home/${USERNAME}/go" \
    GOPROXY="https://goproxy.cn,direct" \
    GOSUMDB="sum.golang.google.cn" \
    GOTOOLCHAIN="local" \
    HTTP_PROXY="" \
    HTTPS_PROXY="" \
    LLVM_CONFIG="llvm-config" \
    NPM_CONFIG_REGISTRY="$BUN_REGISTRY" \
    NO_PROXY="" \
    QY_CC="clang" \
    QY_LLVM_DIR="/usr/bin" \
    QY_LLC="llc" \
    http_proxy="" \
    https_proxy="" \
    no_proxy="" \
    npm_config_registry="$BUN_REGISTRY" \
    REMOTE_USER="$USERNAME"

RUN mkdir -p \
        /home/$USERNAME/.bun/bin \
        /home/$USERNAME/.bun/install/cache \
        /home/$USERNAME/.bun/install/global \
        /home/$USERNAME/go/bin && \
    chown -R $USERNAME:$(id -gn $USERNAME) /home/$USERNAME/.bun /home/$USERNAME/go && \
    chmod +x /usr/local/bin/devcontainer-entrypoint /usr/local/bin/devcontainer-check-config

USER root

ENV PATH="/usr/local/go/bin:/home/${USERNAME}/.bun/bin:/home/${USERNAME}/go/bin:${PATH}"
ENTRYPOINT ["/usr/local/bin/devcontainer-entrypoint"]
WORKDIR /workspaces/Qy
