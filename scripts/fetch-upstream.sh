#!/bin/bash
# Fetch the official upstream Klipper checkout pinned in upstream.lock into a
# disposable build directory. Fails hard if the checkout does not exactly
# match the pinned SHA. This checkout is build input only - it is never
# committed to this repository.
set -euo pipefail
cd "$(dirname "$0")/.."

LOCK_FILE="upstream.lock"
BUILD_DIR="${1:-build/klipper-src}"

KLIPPER_REPO=$(grep '^KLIPPER_REPO=' "$LOCK_FILE" | cut -d= -f2-)
KLIPPER_SHA=$(grep '^KLIPPER_SHA=' "$LOCK_FILE" | cut -d= -f2-)

if [ -z "$KLIPPER_REPO" ] || [ -z "$KLIPPER_SHA" ]; then
    echo "FAIL: could not parse KLIPPER_REPO/KLIPPER_SHA from $LOCK_FILE"
    exit 1
fi

echo "== Fetching official upstream Klipper =="
echo "repo: $KLIPPER_REPO"
echo "pinned sha: $KLIPPER_SHA"

rm -rf "$BUILD_DIR"
mkdir -p "$(dirname "$BUILD_DIR")"
git clone --quiet "$KLIPPER_REPO" "$BUILD_DIR"

cd "$BUILD_DIR"
# Fetch tags explicitly too (some clones/CI runners shallow-fetch tags
# inconsistently) - needed for a stable `git describe` version string.
git fetch --quiet --tags origin
git checkout --quiet "$KLIPPER_SHA"

ACTUAL_SHA=$(git rev-parse HEAD)
if [ "$ACTUAL_SHA" != "$KLIPPER_SHA" ]; then
    echo "FAIL: checked-out HEAD ($ACTUAL_SHA) does not match pinned SHA ($KLIPPER_SHA)"
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "FAIL: fetched upstream checkout is not clean"
    exit 1
fi

echo "OK: official upstream Klipper checked out clean at exactly $ACTUAL_SHA"
