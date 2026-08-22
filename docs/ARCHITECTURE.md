# Architecture

## Host and MCU Klipper source policies are different, on purpose

NebulaOS runs two independently pinned Klipper checkouts that are never the same checkout and never
depend on each other:

**Host (`NebulaOS-firmware`, running on the Nebula Pad's Linux side):**

```
HOST_KLIPPER_SOURCE_MODEL = OFFICIAL_UPSTREAM_PLUS_EXTERNAL_EXTRAS
HOST_KLIPPER_CORE_PATCHES = 0
HOST_KLIPPER_FORK = NO
```

An ordinary, unmodified `Klipper3d/klipper` checkout at a pinned commit, with NebulaOS's own Klippy
extras (PRTouch, Z-compensation, TMC status, etc., in `NebulaOS-klipper-extensions`) composed
alongside it at boot — never patched into Klipper's own core files. Host patches are **forbidden** by
current architecture.

**MCU (this repository, `NebulaOS-klipper-mcu`):**

```
MCU_KLIPPER_SOURCE_MODEL = OFFICIAL_UPSTREAM_PLUS_EXPLICIT_PATCH_QUEUE
MCU_FULL_UPSTREAM_SOURCE_VENDORED = NO
MCU_LONG_LIVED_KLIPPER_FORK = NO
```

A pinned official `Klipper3d/klipper` commit (`upstream.lock`), fetched fresh on every build into a
disposable directory, with an explicit, reviewable patch queue (`patches/series`) applied on top to
add hardware support Klipper doesn't have upstream (the GD32F303RET6 target). MCU hardware-support
patches are **expected and allowed** — this is fundamentally different from the host, which runs
Klipper's own portable Python control layer and has no hardware-specific reason to diverge from
upstream.

This repository is never used as the Nebula Pad's host Klipper source. It exists to produce one
artifact: a flashable MCU firmware image for the KE's GD32F303RET6 controller.

## Why a patch queue and not a fork

A long-lived fork accumulates drift from upstream fixes/features and becomes progressively harder to
rebase. A small, explicit, upstream-relative patch queue (currently one patch, 6 files, 79
insertions/3 deletions) stays reviewable, rebasable onto newer upstream pins, and makes exactly what
NebulaOS changed about Klipper's MCU firmware auditable in one diff. `scripts/guard-no-vendored-source.sh`
enforces this mechanically in CI: it fails the build if `klippy/`, `src/`, `lib/`, or `docs/` from
upstream Klipper are ever committed into this repository.

## Build reconstruction, and why artifact hashes can legitimately change

Klipper embeds `git describe --always --tags --long --dirty` of `HEAD` into its compiled firmware as
a version string (`scripts/buildcommands.py:git_version()`). This means the compiled binary's exact
bytes depend not just on source content, but on the exact commit graph reachable from the checkout's
`HEAD` at build time.

`scripts/apply-patches.sh` reconstructs the patch commit deterministically — same tree, same parent,
same author *and* committer identity/date (both read from the patch file itself, not the applying
environment's clock or git config) — so two independent builds of the same `upstream.lock` +
`patches/series` produce a byte-identical raw `klipper.bin`. It logs whether the reconstructed commit
SHA exactly matches Phase 1.7's original proof commit (`01a9c2f925de8b8636caa0e61192ec6ff62ff9c9`).

The very first Phase 1.7 proof artifacts, however, were built from a working tree whose `HEAD` also
included two additional NebulaOS-tooling-only commits layered on top of the source patch (this
repository's predecessor was a full Klipper clone with NebulaOS tooling committed directly into it).
Those tooling commits touched no Klipper source file, but they *did* shift `HEAD`'s SHA, which shifted
the embedded `git describe` version string, which changes the compiled binary's hash — even though the
Klipper source semantics are identical. This thin repository's disposable build checkout intentionally
stops at the patch commit alone (tooling now lives here, in the thin repo, never as extra commits in
the built Klipper tree), so its canonical artifact hashes differ from the original Phase 1.7 proof
hashes by design. See `_project/missions/2026-08-phase1.7-native-gd32-build.md` in the NebulaOS
workspace for the exact before/after hash comparison and the full explanation.

A second, independent source of cross-host hash variance was found while standing up GitHub Actions
CI: the embedded command dictionary's compressed size depends on the host Python's zlib build. See
[`docs/REPRODUCIBILITY.md`](REPRODUCIBILITY.md) for the full explanation and which build's hashes are
canonical.

## Future channel model

Documented, not yet built as automation:

- **stable** — a pinned official upstream commit/release + a qualified patch series + a
  hardware-qualified artifact. This is what `upstream.lock` and `patches/series` represent today
  (offline-validated; hardware qualification is Phase 1.8+).
- **dev** — a newer pinned upstream/master commit + the same or rebased patch queue + a CI artifact,
  not yet hardware-qualified.

A future nightly workflow may test current upstream `master`, but floating `master` is never the
canonical stable build, and `upstream.lock` is not updated automatically.
