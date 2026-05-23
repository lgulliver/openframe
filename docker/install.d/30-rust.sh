#!/bin/sh

set -eu

export RUSTUP_HOME=/usr/local/rustup
export CARGO_HOME=/usr/local/cargo
mkdir -p "${RUSTUP_HOME}" "${CARGO_HOME}"

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh
sh /tmp/rustup-init.sh -y --profile minimal --default-toolchain stable
ln -sf "${CARGO_HOME}/bin/cargo" /usr/local/bin/cargo
ln -sf "${CARGO_HOME}/bin/rustc" /usr/local/bin/rustc
ln -sf "${CARGO_HOME}/bin/rustup" /usr/local/bin/rustup
rm -f /tmp/rustup-init.sh
