#!/bin/bash
# NebulaOS-klipper-mcu canonical CI entrypoint. GitHub Actions wraps this
# script rather than duplicating build logic in YAML.
#
# Steps:
#  1. verify thin repo layout (no vendored upstream Klipper source)
#  2. parse upstream.lock, fetch official Klipper, verify exact SHA
#  3. apply this repo's explicit patch queue as a clean deterministic commit
#  4. build twice, compare hashes for reproducibility
#  5. pack the raw binary into a Creality image
#  6. validate the candidate (+ stock fixtures if STOCK_FIXTURE_DIR is set)
#  7. run the 23-case negative fixture suite
#  8. run the flasher's fake-transport unit tests
#  9. parse the KE's real [load_cell_probe] config against the built dict
# 10. generate the provenance manifest
#
# Never touches hardware. Usage: scripts/ci.sh [artifact_dir]
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

ARTIFACT_DIR="${1:-artifacts}"
BUILD_DIR="build/klipper-src"
UPSTREAM_SHA="58bd67db3ce1be1951c3e4a6d1156a79903d4edc"
METADATA_VERSION="900"

# tools/creality_validator.py shells out to arm-none-eabi-readelf directly
# (not just build.sh's own make invocation), so the toolchain must be on
# PATH for the whole script, not just re-exported inside build.sh's own
# subprocess.
if [ -n "${TOOLCHAIN_BIN:-}" ]; then
    export PATH="$TOOLCHAIN_BIN:$PATH"
fi

rm -rf "$ARTIFACT_DIR"
mkdir -p "$ARTIFACT_DIR"

echo "== Step 1: thin-repo guard =="
./scripts/guard-no-vendored-source.sh

echo
echo "== Step 2: fetch official upstream Klipper =="
./scripts/fetch-upstream.sh "$BUILD_DIR"

echo
echo "== Step 3: apply explicit patch queue =="
./scripts/apply-patches.sh "$BUILD_DIR"

echo
echo "== Step 4a: record the reconstructed source diff =="
cd "$BUILD_DIR"
git diff "$UPSTREAM_SHA"..HEAD > "$REPO_ROOT/$ARTIFACT_DIR/reconstructed-source.diff"
cd "$REPO_ROOT"
# git am's exit 0 in step 3 is the authoritative "patch applied without
# fuzz" signal; this diff is kept as an artifact for direct human/tool
# comparison against patches/*.patch and against the archived Phase 1.7
# proof delta in _evidence/phase1.7-mcu-proof/source-patch-only.diff.
echo "OK: reconstructed diff recorded at $ARTIFACT_DIR/reconstructed-source.diff"

echo
echo "== Step 4b: build twice, compare hashes for reproducibility =="
# scripts/build.sh writes into the given artifact sub-namespace; run it
# twice into two separate sub-namespaces to compare.
rm -rf "$ARTIFACT_DIR/pass1" "$ARTIFACT_DIR/pass2"
mkdir -p "$ARTIFACT_DIR/pass1" "$ARTIFACT_DIR/pass2"
./scripts/build.sh "$BUILD_DIR" "$ARTIFACT_DIR/pass1"
./scripts/build.sh "$BUILD_DIR" "$ARTIFACT_DIR/pass2"

if ! cmp -s "$ARTIFACT_DIR/pass1/klipper.bin" "$ARTIFACT_DIR/pass2/klipper.bin"; then
    echo "FAIL: raw klipper.bin is not reproducible across two clean builds"
    exit 1
fi
echo "OK: raw klipper.bin is byte-identical across two clean builds"

if cmp -s "$ARTIFACT_DIR/pass1/klipper.elf" "$ARTIFACT_DIR/pass2/klipper.elf"; then
    echo "OK: klipper.elf is also byte-identical"
else
    echo "NOTE: klipper.elf differs (raw .bin identity is the load-bearing guarantee)"
fi

cp "$ARTIFACT_DIR/pass2/klipper.elf" "$ARTIFACT_DIR/klipper.elf"
cp "$ARTIFACT_DIR/pass2/klipper.bin" "$ARTIFACT_DIR/klipper.bin"
cp "$ARTIFACT_DIR/pass2/klipper.config" "$ARTIFACT_DIR/klipper.config"
cp "$ARTIFACT_DIR/pass2/klipper-creality.bin" "$ARTIFACT_DIR/klipper-creality.bin"

REPORT="$ARTIFACT_DIR/validator-report.txt"
: > "$REPORT"

echo
echo "== Step 5: offline validator - candidate ==" | tee -a "$REPORT"
python3 tools/creality_validator.py target "$ARTIFACT_DIR/klipper-creality.bin" \
    "$ARTIFACT_DIR/klipper.elf" "$ARTIFACT_DIR/klipper.config" 2>&1 | tee -a "$REPORT"

if [ -d "${STOCK_FIXTURE_DIR:-}" ]; then
    echo | tee -a "$REPORT"
    echo "== Step 5b: offline validator - stock fixtures ==" | tee -a "$REPORT"
    for f in "$STOCK_FIXTURE_DIR"/*.bin; do
        python3 tools/creality_validator.py format "$f" --expect-type mcu0 2>&1 | tee -a "$REPORT"
    done
else
    echo "NOTE: STOCK_FIXTURE_DIR not set - skipping stock-fixture pass " \
         "(proprietary Creality binaries are never committed to this repo)" | tee -a "$REPORT"
fi

echo | tee -a "$REPORT"
echo "== Step 6: negative fixture suite ==" | tee -a "$REPORT"
python3 tools/test_negative_fixtures.py "$ARTIFACT_DIR/klipper-creality.bin" \
    "$ARTIFACT_DIR/klipper.elf" "$ARTIFACT_DIR/klipper.config" 2>&1 | tee -a "$REPORT"

echo | tee -a "$REPORT"
echo "== Step 7: flasher unit tests (fake transport, no hardware) ==" | tee -a "$REPORT"
python3 tools/test_creality_flash.py "$ARTIFACT_DIR/klipper-creality.bin" \
    "$ARTIFACT_DIR/klipper.elf" "$ARTIFACT_DIR/klipper.config" 2>&1 | tee -a "$REPORT"

echo
echo "== Step 8: KE load_cell_probe config parse (offline, no hardware) =="
# test_klippy.py invokes ./klippy/klippy.py relative to the process cwd, so
# it must be run from inside the patched Klipper checkout.
( cd "$BUILD_DIR" && python3 scripts/test_klippy.py -d out \
    "$REPO_ROOT/tests/klippy/nebulaos_ke_load_cell.test" )

echo
echo "== Step 9: provenance manifest =="
python3 tools/generate_provenance.py \
    --repo "$BUILD_DIR" \
    --elf "$ARTIFACT_DIR/klipper.elf" \
    --raw-bin "$ARTIFACT_DIR/klipper.bin" \
    --packaged-bin "$ARTIFACT_DIR/klipper-creality.bin" \
    --config "$ARTIFACT_DIR/klipper.config" \
    --upstream-sha "$UPSTREAM_SHA" \
    --output "$ARTIFACT_DIR/provenance.json"

rm -rf "$ARTIFACT_DIR/pass1" "$ARTIFACT_DIR/pass2" "$ARTIFACT_DIR/build1"

echo
echo "All Phase 1.7 thin-repo CI gates passed. Artifacts in $ARTIFACT_DIR/."
echo "HARDWARE_FLASH_PERFORMED=NO"
