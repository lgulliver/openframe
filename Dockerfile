FROM debian:bookworm-slim

SHELL ["/bin/bash", "-lc"]

ARG OPENCODE_VERSION=1.15.10
ARG EXTRA_APT_PACKAGES=""
ARG APT_PACKAGES_FILE=docker/apt-packages.txt
ARG DOTNET_SDK_VERSION=10.0.300
ARG GO_VERSION=1.26.3
ARG PYTHON_VERSION=3.14.5
ARG NODE_VERSION=24.16.0
ARG NVM_VERSION=0.40.3
ARG KUBECTL_VERSION=v1.36.0
ARG HELM_VERSION=v4.1.4
ARG TERRAFORM_VERSION=1.15.4
ARG BUN_VERSION=1.3.14

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    jq \
    make \
    nodejs \
    npm \
    openssh-client \
    procps \
    python3 \
    python3-pip \
    ripgrep \
    wget \
    xz-utils \
    zsh \
  && rm -rf /var/lib/apt/lists/*

COPY docker/install-tools.sh /tmp/install-tools.sh
COPY ${APT_PACKAGES_FILE} /tmp/apt-packages.txt
COPY docker/install.d /tmp/install.d

RUN chmod +x /tmp/install-tools.sh \
  && EXTRA_APT_PACKAGES="${EXTRA_APT_PACKAGES}" APT_PACKAGES_FILE=/tmp/apt-packages.txt /tmp/install-tools.sh \
  && find /tmp/install.d -type f -name '*.sh' -exec chmod +x {} + \
  && DOTNET_SDK_VERSION="${DOTNET_SDK_VERSION}" \
     GO_VERSION="${GO_VERSION}" \
     PYTHON_VERSION="${PYTHON_VERSION}" \
     NODE_VERSION="${NODE_VERSION}" \
     NVM_VERSION="${NVM_VERSION}" \
     KUBECTL_VERSION="${KUBECTL_VERSION}" \
     HELM_VERSION="${HELM_VERSION}" \
     TERRAFORM_VERSION="${TERRAFORM_VERSION}" \
     BUN_VERSION="${BUN_VERSION}" \
     sh -c 'for script in /tmp/install.d/*.sh; do "$script"; done' \
  && rm -rf /tmp/install.d /tmp/install-tools.sh /tmp/apt-packages.txt

RUN curl -fsSL https://opencode.ai/install | bash -s -- --version "${OPENCODE_VERSION}" --no-modify-path \
  && ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode

ENV DOTNET_ROOT=/usr/share/dotnet
ENV RUSTUP_HOME=/usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo
ENV NVM_DIR=/usr/local/nvm
ENV PATH=/usr/local/cargo/bin:/usr/share/dotnet:/usr/local/go/bin:/opt/python/${PYTHON_VERSION}/bin:/usr/local/bun/bin:${PATH}
