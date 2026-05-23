#!/bin/sh

set -eu

if [ -z "${OPENCODE_SERVER_PASSWORD:-}" ]; then
  echo "OPENCODE_SERVER_PASSWORD must be set in .env." >&2
  exit 1
fi

mkdir -p \
  "${HOME}" \
  "${HOME}/.config/opencode" \
  "${HOME}/.local/share/opencode" \
  /workspace/.data/instances \
  /workspace/.data/logs

sh /workspace/docker/bootstrap.sh

exec python3 /workspace/manager.py
