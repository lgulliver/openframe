#!/bin/sh

set -eu

mkdir -p /workspace/.data

cat >/workspace/.data/gitconfig <<EOF
[init]
	defaultBranch = ${GIT_DEFAULT_BRANCH:-main}
EOF

if [ -n "${GIT_USER_NAME:-}" ]; then
  cat >>/workspace/.data/gitconfig <<EOF
[user]
	name = ${GIT_USER_NAME}
EOF
fi

if [ -n "${GIT_USER_EMAIL:-}" ]; then
  if ! grep -q '^\[user\]' /workspace/.data/gitconfig; then
    cat >>/workspace/.data/gitconfig <<'EOF'
[user]
EOF
  fi
  cat >>/workspace/.data/gitconfig <<EOF
	email = ${GIT_USER_EMAIL}
EOF
fi

if [ -n "${GIT_CORE_EDITOR:-}" ]; then
  cat >>/workspace/.data/gitconfig <<EOF
[core]
	editor = ${GIT_CORE_EDITOR}
EOF
fi

git config --global include.path /workspace/.data/gitconfig

if [ -d /workspace/docker/startup.d ]; then
  for script in /workspace/docker/startup.d/*.sh; do
    if [ ! -f "${script}" ]; then
      continue
    fi
    echo "Running startup hook: ${script}"
    sh "${script}"
  done
fi
