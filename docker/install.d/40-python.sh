#!/bin/sh

set -eu

PYTHON_VERSION="${PYTHON_VERSION:-3.14.5}"
MAJOR_MINOR="$(printf '%s' "${PYTHON_VERSION}" | cut -d. -f1,2)"

curl -fsSL "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz" -o /tmp/python.tar.xz
mkdir -p /tmp/python-src
tar -C /tmp/python-src --strip-components=1 -xf /tmp/python.tar.xz
cd /tmp/python-src
./configure --enable-optimizations --with-ensurepip=install --prefix "/opt/python/${PYTHON_VERSION}"
make -j"$(nproc)"
make install

ln -sf "/opt/python/${PYTHON_VERSION}/bin/python${MAJOR_MINOR}" /usr/local/bin/python${MAJOR_MINOR}
ln -sf "/opt/python/${PYTHON_VERSION}/bin/python3" /usr/local/bin/python3
ln -sf "/opt/python/${PYTHON_VERSION}/bin/python3" /usr/local/bin/python
ln -sf "/opt/python/${PYTHON_VERSION}/bin/pip3" /usr/local/bin/pip3
ln -sf "/opt/python/${PYTHON_VERSION}/bin/pip3" /usr/local/bin/pip

rm -rf /tmp/python-src /tmp/python.tar.xz
