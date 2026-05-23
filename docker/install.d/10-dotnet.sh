#!/bin/sh

set -eu

DOTNET_SDK_VERSION="${DOTNET_SDK_VERSION:-10.0.300}"
DOTNET_ROOT="/usr/share/dotnet"

mkdir -p "${DOTNET_ROOT}"
curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh
chmod +x /tmp/dotnet-install.sh
/tmp/dotnet-install.sh --version "${DOTNET_SDK_VERSION}" --install-dir "${DOTNET_ROOT}"
ln -sf "${DOTNET_ROOT}/dotnet" /usr/local/bin/dotnet
rm -f /tmp/dotnet-install.sh
