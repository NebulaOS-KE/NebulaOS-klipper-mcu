#!/bin/bash
# Build the community mainboard firmwares (community/<board>/<chip>.defconfig)
# from the official Klipper pinned in upstream.lock - plain upstream, no patch:
# these boards keep their own SD-card bootloader, which takes an ordinary
# Klipper image. The KE build (scripts/ci.sh) is separate and unchanged.
#
# NOT SUPPORTED by NebulaOS: these are built from published, working recipes
# so users can try them easily (see community/README.md).
#
# Every target is built twice from a clean tree; the two klipper.bin must be
# byte-identical, and the image's vector table must start inside the
# application area of the resulting .config, and that .config must hold the
# recipe's "# expect:" values (bootloader offset, MCU, baud) - a wrong
# bootloader offset is the one setting that can brick a board.
#
# Usage: scripts/build-community.sh [out_dir]      (default: artifacts/community)
# Needs arm-none-eabi-gcc on PATH (scripts/install-toolchain.sh) and python3.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
OUT=$(mkdir -p "${1:-artifacts/community}" && cd "${1:-artifacts/community}" && pwd)
SRC="$ROOT/build/klipper-community"

KLIPPER_SHA=$(grep '^KLIPPER_SHA=' upstream.lock | cut -d= -f2-)
./scripts/fetch-upstream.sh "$SRC"
command -v arm-none-eabi-gcc >/dev/null || { echo "FAIL: arm-none-eabi-gcc not on PATH"; exit 1; }
GCC_VERSION=$(arm-none-eabi-gcc --version | head -1)
MCU_REPO_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)

build_once() { # defconfig -> $SRC/out/klipper.bin, $SRC/.config
    (cd "$SRC" && make -s distclean >/dev/null 2>&1 || true
     grep -v '^#' "$1" > "$SRC/.config"
     make -s olddefconfig >/dev/null
     make -s -j"$(nproc)" >/dev/null)
}

check_vectors() { # bin config -> fails unless SP is in RAM and reset is in the app area
    python3 - "$1" "$2" <<'PY'
import re, struct, sys
data = open(sys.argv[1], "rb").read(8)
cfg = open(sys.argv[2]).read()
def num(key):
    return int(re.search(r"^CONFIG_%s=(\S+)$" % key, cfg, re.M).group(1), 0)
app, flash = num("FLASH_APPLICATION_ADDRESS"), num("FLASH_BOOT_ADDRESS") + num("FLASH_SIZE")
ram, ram_end = num("RAM_START"), num("RAM_START") + num("RAM_SIZE")
sp, reset = struct.unpack("<II", data)
ok = ram < sp <= ram_end and app <= (reset & ~1) < flash
print("VECTORS sp=%#x reset=%#x app=%#x ram=%#x-%#x %s"
      % (sp, reset, app, ram, ram_end, "OK" if ok else "FAIL"))
sys.exit(0 if ok else 1)
PY
}

for recipe in community/*/*.defconfig; do
    board=$(basename "$(dirname "$recipe")")
    chip=$(basename "$recipe" .defconfig)
    dest="$OUT/$board/$chip"
    name="nebulaos-$board-$chip.bin"
    echo "== $board / $chip =="
    mkdir -p "$dest"
    build_once "$ROOT/$recipe"
    cp "$SRC/out/klipper.bin" "$dest/$name.pass1"
    build_once "$ROOT/$recipe"
    if ! cmp -s "$SRC/out/klipper.bin" "$dest/$name.pass1"; then
        echo "FAIL: $board/$chip: two clean builds differ"; exit 1
    fi
    rm -f "$dest/$name.pass1"
    cp "$SRC/out/klipper.bin" "$dest/$name"
    cp "$SRC/.config" "$dest/klipper.config"
    cp "$ROOT/$recipe" "$dest/recipe.defconfig"
    check_vectors "$dest/$name" "$dest/klipper.config"
    # The recipe's own "# expect:" line: the values that must not drift
    # (bootloader offset above all). Refuses a recipe without one.
    expect=$(sed -n 's/^# expect: //p' "$ROOT/$recipe")
    [ -n "$expect" ] || { echo "FAIL: $recipe has no '# expect:' line"; exit 1; }
    for kv in $expect; do
        grep -qx -- "$kv" "$dest/klipper.config" || { echo "FAIL: $board/$chip: $kv not in the resulting .config"; exit 1; }
    done
    echo "EXPECT OK: $expect"
    (cd "$dest" && sha256sum "$name" > SHA256SUMS)
    {
        echo "board=$board"
        echo "chip=$chip"
        echo "klipper_repo=$(grep '^KLIPPER_REPO=' upstream.lock | cut -d= -f2-)"
        echo "klipper_sha=$KLIPPER_SHA"
        echo "klipper_version=$(cd "$SRC" && git describe --tags --always)"
        echo "nebulaos_klipper_mcu_commit=$MCU_REPO_COMMIT"
        echo "toolchain=$GCC_VERSION"
        echo "python=$(python3 --version 2>&1)"
        echo "sha256=$(cut -d' ' -f1 "$dest/SHA256SUMS")"
        echo "reproducible=two clean builds byte-identical"
        echo "status=COMMUNITY BOARD - not supported by NebulaOS"
    } > "$dest/build-info.txt"
    cat "$dest/SHA256SUMS"
done
echo "COMMUNITY_BUILD=OK out=$OUT"
