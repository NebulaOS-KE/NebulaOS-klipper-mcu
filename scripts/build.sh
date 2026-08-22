#!/bin/bash
# Build the GD32F303 KE MCU candidate from the patched, disposable Klipper
# checkout produced by fetch-upstream.sh + apply-patches.sh, then pack it
# into a Creality-format image. Copies final artifacts into artifacts/.
#
# Optional: set TOOLCHAIN_BIN to prepend a specific arm-none-eabi-* toolchain
# directory onto PATH (used in CI to pin the exact toolchain from
# scripts/install-toolchain.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

BUILD_DIR="${1:-build/klipper-src}"
ARTIFACT_DIR="${2:-artifacts}"
METADATA_VERSION="900"

if [ -n "${TOOLCHAIN_BIN:-}" ]; then
    export PATH="$TOOLCHAIN_BIN:$PATH"
fi

echo "== Toolchain =="
arm-none-eabi-gcc --version | head -1
arm-none-eabi-ld --version | head -1

mkdir -p "$ARTIFACT_DIR"
cd "$BUILD_DIR"

cp "$REPO_ROOT/configs/ender3-v3-ke.defconfig" .config
python3 lib/kconfiglib/olddefconfig.py src/Kconfig >/dev/null
echo "OK: .config regenerated from configs/ender3-v3-ke.defconfig"

make clean >/dev/null
make >/dev/null

echo "OK: native GD32F303 build exit 0"

cp out/klipper.elf "$REPO_ROOT/$ARTIFACT_DIR/klipper.elf"
cp out/klipper.bin "$REPO_ROOT/$ARTIFACT_DIR/klipper.bin"
cp .config "$REPO_ROOT/$ARTIFACT_DIR/klipper.config"

cd "$REPO_ROOT"
python3 tools/creality_packer.py "$ARTIFACT_DIR/klipper.bin" "$ARTIFACT_DIR/klipper-creality.bin" \
    --version "$METADATA_VERSION"

echo "OK: build + pack complete, artifacts in $ARTIFACT_DIR/"
