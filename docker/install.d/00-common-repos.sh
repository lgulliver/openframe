#!/bin/sh

set -eu

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  apt-transport-https \
  build-essential \
  clang \
  curl \
  fd-find \
  gnupg \
  gpg \
  less \
  libbz2-dev \
  libffi-dev \
  libgdbm-dev \
  liblzma-dev \
  libncurses5-dev \
  libnss3-dev \
  libreadline-dev \
  libsqlite3-dev \
  libssl-dev \
  libuuid1 \
  libxml2-dev \
  libxmlsec1-dev \
  llvm \
  lsb-release \
  tk-dev \
  unzip \
  uuid-dev \
  xz-utils \
  zlib1g-dev

ln -sf /usr/bin/fdfind /usr/local/bin/fd || true

mkdir -p /etc/apt/keyrings

curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" >/etc/apt/sources.list.d/github-cli.list
apt-get update
apt-get install -y --no-install-recommends gh
