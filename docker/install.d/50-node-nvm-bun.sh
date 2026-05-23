#!/bin/sh

set -eu

NODE_VERSION="${NODE_VERSION:-24.16.0}"
NVM_VERSION="${NVM_VERSION:-0.40.3}"
export NVM_DIR=/usr/local/nvm

mkdir -p "${NVM_DIR}"
curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh" -o /tmp/install-nvm.sh
PROFILE=/dev/null NVM_DIR="${NVM_DIR}" sh /tmp/install-nvm.sh
. "${NVM_DIR}/nvm.sh"
nvm install "${NODE_VERSION}"
nvm alias default "${NODE_VERSION}"
nvm use default

ln -sf "${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/node" /usr/local/bin/node
ln -sf "${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/npm" /usr/local/bin/npm
ln -sf "${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/npx" /usr/local/bin/npx
if [ -f "${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/corepack" ]; then
  ln -sf "${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/corepack" /usr/local/bin/corepack
fi

curl -fsSL https://bun.sh/install -o /tmp/install-bun.sh
BUN_INSTALL=/usr/local/bun sh /tmp/install-bun.sh
ln -sf /usr/local/bun/bin/bun /usr/local/bin/bun

cat >/etc/profile.d/nvm.sh <<'EOF'
export NVM_DIR=/usr/local/nvm
[ -s "${NVM_DIR}/nvm.sh" ] && . "${NVM_DIR}/nvm.sh"
EOF

rm -f /tmp/install-nvm.sh /tmp/install-bun.sh
