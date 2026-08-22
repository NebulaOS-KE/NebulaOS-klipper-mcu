#!/bin/bash
# Thin-repo guard: fail if this repository has accidentally started
# vendoring the upstream Klipper source tree instead of fetching it as
# disposable build input. This repo is a patch/build repository, not a
# Klipper fork - see README.md.
set -euo pipefail
cd "$(dirname "$0")/.."

FORBIDDEN_PATHS=(klippy src lib)
FAIL=0

for p in "${FORBIDDEN_PATHS[@]}"; do
    if git ls-files --error-unmatch "$p" >/dev/null 2>&1; then
        echo "FAIL: '$p/' is tracked in this repository - upstream Klipper source must never be vendored here"
        FAIL=1
    fi
done

# This repo's own docs/ and scripts/ directories are expected and allowed
# (small, NebulaOS-authored). Only flag them if they look like a wholesale
# copy of Klipper's own same-named trees, via canary files unique to
# upstream Klipper that this repo should never contain.
if git ls-files --error-unmatch scripts/buildcommands.py >/dev/null 2>&1; then
    echo "FAIL: scripts/buildcommands.py is tracked - looks like a vendored Klipper scripts/ tree"
    FAIL=1
fi
if git ls-files --error-unmatch docs/Config_Reference.md >/dev/null 2>&1; then
    echo "FAIL: docs/Config_Reference.md is tracked - looks like a vendored Klipper docs/ tree"
    FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
    echo "THIN_REPO_GUARD=FAIL"
    exit 1
fi

echo "THIN_REPO_GUARD=PASS (no vendored upstream Klipper source detected)"
