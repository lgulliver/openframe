#!/bin/sh

set -eu

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This image expects an apt-based runtime." >&2
  exit 1
fi

manifest_packages=""
if [ -n "${APT_PACKAGES_FILE:-}" ] && [ -f "${APT_PACKAGES_FILE}" ]; then
  manifest_packages="$(grep -v '^[[:space:]]*#' "${APT_PACKAGES_FILE}" | grep -v '^[[:space:]]*$' | tr '\n' ' ' || true)"
fi

all_packages="$(printf '%s %s' "${manifest_packages}" "${EXTRA_APT_PACKAGES:-}" | xargs)"

if [ -n "${all_packages}" ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends fd-find ${all_packages}
  apt-get clean
  rm -rf /var/lib/apt/lists/*
fi

if command -v fdfind >/dev/null 2>&1; then
  ln -sf /usr/bin/fdfind /usr/local/bin/fd || true
fi
