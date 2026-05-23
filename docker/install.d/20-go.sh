#!/bin/sh

set -eu

GO_VERSION="${GO_VERSION:-1.26.3}"
ARCH="$(dpkg --print-architecture)"

case "${ARCH}" in
  amd64) GO_ARCH=amd64 ;;
  arm64) GO_ARCH=arm64 ;;
  *)
    echo "Unsupported architecture for Go: ${ARCH}" >&2
    exit 1
    ;;
esac

curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz" -o /tmp/go.tgz
rm -rf /usr/local/go
tar -C /usr/local -xzf /tmp/go.tgz
ln -sf /usr/local/go/bin/go /usr/local/bin/go
ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt
rm -f /tmp/go.tgz
