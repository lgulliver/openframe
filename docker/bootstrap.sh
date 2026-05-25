#!/bin/sh

set -eu

mkdir -p /data

cat >/data/gitconfig <<EOF
[init]
	defaultBranch = ${GIT_DEFAULT_BRANCH:-main}
EOF

if [ -n "${GIT_USER_NAME:-}" ]; then
  cat >>/data/gitconfig <<EOF
[user]
	name = ${GIT_USER_NAME}
EOF
fi

if [ -n "${GIT_USER_EMAIL:-}" ]; then
  if ! grep -q '^\[user\]' /data/gitconfig; then
    cat >>/data/gitconfig <<'EOF'
[user]
EOF
  fi
  cat >>/data/gitconfig <<EOF
	email = ${GIT_USER_EMAIL}
EOF
fi

if [ -n "${GIT_CORE_EDITOR:-}" ]; then
  cat >>/data/gitconfig <<EOF
[core]
	editor = ${GIT_CORE_EDITOR}
EOF
fi

git config --global include.path /data/gitconfig

if [ -d /opt/openframe/docker/startup.d ]; then
  for script in /opt/openframe/docker/startup.d/*.sh; do
    if [ ! -f "${script}" ]; then
      continue
    fi
    echo "Running startup hook: ${script}"
    sh "${script}"
  done
fi
