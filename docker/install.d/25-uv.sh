#!/bin/sh

set -eu

: "${UV_VERSION:?UV_VERSION is required}"

curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_UNMANAGED_INSTALL="/usr/local/bin" sh
