#!/bin/sh

set -eu

ARCH="$(dpkg --print-architecture)"
case "${ARCH}" in
  amd64) BIN_ARCH=amd64 ;;
  arm64) BIN_ARCH=arm64 ;;
  *)
    echo "Unsupported architecture for kubectl/helm: ${ARCH}" >&2
    exit 1
    ;;
esac

KUBECTL_VERSION="${KUBECTL_VERSION:-$(curl -L -s https://dl.k8s.io/release/stable.txt)}"
curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${BIN_ARCH}/kubectl" -o /usr/local/bin/kubectl
chmod +x /usr/local/bin/kubectl

HELM_VERSION="${HELM_VERSION:-v4.1.4}"
curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${BIN_ARCH}.tar.gz" -o /tmp/helm.tgz
mkdir -p /tmp/helm
tar -C /tmp/helm -xzf /tmp/helm.tgz
install -m 0755 "/tmp/helm/linux-${BIN_ARCH}/helm" /usr/local/bin/helm
rm -rf /tmp/helm /tmp/helm.tgz
