#!/bin/sh

set -eu

curl -sLS https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor >/etc/apt/keyrings/microsoft.gpg
chmod go+r /etc/apt/keyrings/microsoft.gpg

AZ_DIST="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
cat >/etc/apt/sources.list.d/azure-cli.sources <<EOF
Types: deb
URIs: https://packages.microsoft.com/repos/azure-cli/
Suites: ${AZ_DIST}
Components: main
Architectures: $(dpkg --print-architecture)
Signed-by: /etc/apt/keyrings/microsoft.gpg
EOF

apt-get update
apt-get install -y --no-install-recommends azure-cli
