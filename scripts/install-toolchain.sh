#!/bin/bash
# Download and SHA256-verify the pinned Arm GNU Toolchain used to build the
# MCU candidate in CI. Matches the major.minor GCC series proven locally
# (arm-none-eabi-gcc 15.2.x) - see docs/TOOLCHAIN.md for why an exact
# distro-build match isn't attempted and how that's judged acceptable.
#
# Usage: scripts/install-toolchain.sh [install_dir]
# Prints the toolchain's bin/ directory on stdout when it succeeds.
set -euo pipefail

TOOLCHAIN_VERSION="15.2.rel1"
TOOLCHAIN_ARCHIVE="arm-gnu-toolchain-${TOOLCHAIN_VERSION}-x86_64-arm-none-eabi.tar.xz"
TOOLCHAIN_URL="https://developer.arm.com/-/media/Files/downloads/gnu/${TOOLCHAIN_VERSION}/binrel/${TOOLCHAIN_ARCHIVE}"
TOOLCHAIN_SHA256="597893282ac8c6ab1a4073977f2362990184599643b4c5ee34870a8215783a16"

INSTALL_DIR="${1:-/tmp/arm-gnu-toolchain}"
CACHE_DIR="${TOOLCHAIN_CACHE_DIR:-/tmp}"
ARCHIVE_PATH="$CACHE_DIR/$TOOLCHAIN_ARCHIVE"

if [ ! -f "$ARCHIVE_PATH" ]; then
    echo "Downloading $TOOLCHAIN_URL ..." >&2
    curl -sL -o "$ARCHIVE_PATH" "$TOOLCHAIN_URL"
fi

ACTUAL_SHA256=$(sha256sum "$ARCHIVE_PATH" | cut -d' ' -f1)
if [ "$ACTUAL_SHA256" != "$TOOLCHAIN_SHA256" ]; then
    echo "FAIL: toolchain archive SHA256 mismatch" >&2
    echo "  expected: $TOOLCHAIN_SHA256" >&2
    echo "  actual:   $ACTUAL_SHA256" >&2
    rm -f "$ARCHIVE_PATH"
    exit 1
fi
echo "OK: toolchain archive SHA256 verified ($TOOLCHAIN_SHA256)" >&2

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
tar xf "$ARCHIVE_PATH" -C "$INSTALL_DIR" --strip-components=1

"$INSTALL_DIR/bin/arm-none-eabi-gcc" --version | head -1 >&2

echo "$INSTALL_DIR/bin"
