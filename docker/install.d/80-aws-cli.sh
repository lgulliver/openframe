#!/bin/sh

set -eu

ARCH="$(dpkg --print-architecture)"
case "${ARCH}" in
  amd64) AWS_ARCH=x86_64 ;;
  arm64) AWS_ARCH=aarch64 ;;
  *)
    echo "Unsupported architecture for AWS CLI: ${ARCH}" >&2
    exit 1
    ;;
esac

curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${AWS_ARCH}.zip" -o /tmp/awscliv2.zip
rm -rf /tmp/aws
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli --update
rm -rf /tmp/aws /tmp/awscliv2.zip
