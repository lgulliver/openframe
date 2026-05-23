#!/bin/sh

set -eu

TERRAFORM_VERSION="${TERRAFORM_VERSION:-1.15.4}"
ARCH="$(dpkg --print-architecture)"

case "${ARCH}" in
  amd64) TF_ARCH=amd64 ;;
  arm64) TF_ARCH=arm64 ;;
  *)
    echo "Unsupported architecture for Terraform: ${ARCH}" >&2
    exit 1
    ;;
esac

curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TF_ARCH}.zip" -o /tmp/terraform.zip
mkdir -p /tmp/terraform
unzip -q /tmp/terraform.zip -d /tmp/terraform
install -m 0755 /tmp/terraform/terraform /usr/local/bin/terraform
rm -rf /tmp/terraform /tmp/terraform.zip
