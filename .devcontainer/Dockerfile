FROM ubuntu:24.04

ARG USERNAME=ubuntu
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PATH=/home/${USERNAME}/.local/bin:${PATH}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
COPY --from=oven/bun:1 /usr/local/bin/bun /usr/local/bin/bun

#RUN set -eux; \
#    apt-get update; \
#    apt-get install -y --no-install-recommends \
#        bash-completion \
#        binutils \
#        build-essential \
#        ca-certificates \
#        clang \
#        clangd \
#        clang-format \
#        clang-tidy \
#        cmake \
#        curl \
#        gdb \
#        git \
#        gnupg \
#        lcov \
#        lld \
#        lldb \
#        llvm \
#        llvm-dev \
#        llvm-runtime \
#        locales \
#        make \
#        ninja-build \
#        pkg-config \
#        python-is-python3 \
#        python3 \
#        python3-dev \
#        python3-pip \
#        python3-venv \
#        sudo \
#        unzip \
#        xz-utils \
#        zip \
#        zsh; \
#    if ! getent group "${USERNAME}" >/dev/null; then \
#        groupadd --gid "${USER_GID}" "${USERNAME}"; \
#    fi; \
#    if ! id -u "${USERNAME}" >/dev/null 2>&1; then \
#        useradd --uid "${USER_UID}" --gid "${USERNAME}" --create-home --shell /usr/bin/zsh "${USERNAME}"; \
#    fi; \
#    usermod --shell /usr/bin/zsh "${USERNAME}"; \
#    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USERNAME}"; \
#    chmod 0440 "/etc/sudoers.d/${USERNAME}"; \
#    locale-gen en_US.UTF-8; \
#    ln -sf /usr/local/bin/bun /usr/local/bin/bunx; \
#    chown -R "${USERNAME}:${USERNAME}" "/home/${USERNAME}"; \
#    apt-get clean; \
#    rm -rf /var/lib/apt/lists/*

USER ${USERNAME}
