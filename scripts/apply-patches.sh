#!/bin/bash
# Apply this repo's explicit patch queue (patches/series) on top of the
# freshly fetched, pinned upstream Klipper checkout, producing a clean
# (non-dirty) deterministic commit per patch - never a plain `git apply`
# left as uncommitted changes, which would make Klipper's embedded
# `git describe --dirty` version string non-deterministic.
#
# Each patch's committer identity/date is forced to match its own author
# identity/date (both recorded in the mail-format patch itself), so the
# resulting commit is reproducible across machines/CI runs regardless of
# the applying environment's local git config or clock.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

BUILD_DIR="${1:-build/klipper-src}"
SERIES_FILE="$REPO_ROOT/patches/series"

if [ ! -d "$BUILD_DIR/.git" ]; then
    echo "FAIL: $BUILD_DIR is not a git checkout - run scripts/fetch-upstream.sh first"
    exit 1
fi

cd "$BUILD_DIR"

if [ -n "$(git status --porcelain)" ]; then
    echo "FAIL: $BUILD_DIR is not clean before patch application"
    exit 1
fi

echo "== Applying explicit patch queue ($SERIES_FILE) =="
while IFS= read -r patch_name; do
    [ -z "$patch_name" ] && continue
    case "$patch_name" in \#*) continue ;; esac

    patch_path="$REPO_ROOT/patches/$patch_name"
    if [ ! -f "$patch_path" ]; then
        echo "FAIL: patch listed in series but missing: $patch_name"
        exit 1
    fi

    AUTHOR_LINE=$(grep -m1 '^From: ' "$patch_path" | sed 's/^From: //')
    DATE_LINE=$(grep -m1 '^Date: ' "$patch_path" | sed 's/^Date: //')
    AUTHOR_NAME=$(echo "$AUTHOR_LINE" | sed -E 's/ <.*//')
    AUTHOR_EMAIL=$(echo "$AUTHOR_LINE" | sed -E 's/.*<(.*)>.*/\1/')

    echo "-- applying $patch_name (author: $AUTHOR_LINE, date: $DATE_LINE)"
    GIT_COMMITTER_NAME="$AUTHOR_NAME" \
    GIT_COMMITTER_EMAIL="$AUTHOR_EMAIL" \
    GIT_COMMITTER_DATE="$DATE_LINE" \
        git am --quiet "$patch_path"
done < "$SERIES_FILE"

if [ -n "$(git status --porcelain)" ]; then
    echo "FAIL: tree is dirty after patch application"
    exit 1
fi

NEW_HEAD=$(git rev-parse HEAD)
echo "OK: patch queue applied cleanly, HEAD is now $NEW_HEAD"

PROVEN_PATCH_SHA="01a9c2f925de8b8636caa0e61192ec6ff62ff9c9"
if [ "$NEW_HEAD" = "$PROVEN_PATCH_SHA" ]; then
    echo "EXACT_PROOF_COMMIT_RECONSTRUCTION=YES (HEAD == $PROVEN_PATCH_SHA)"
else
    echo "EXACT_PROOF_COMMIT_RECONSTRUCTION=NO (HEAD $NEW_HEAD != proof $PROVEN_PATCH_SHA)"
fi
