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
  /data/instances \
  /data/logs

sh /opt/openframe/docker/bootstrap.sh

exec python3 /opt/openframe/manager.py
