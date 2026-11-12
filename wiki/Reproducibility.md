# Reproducibility

## What's guaranteed

Two clean builds **on the same host/environment** from the same `upstream.lock` + `patches/series`
produce a byte-identical `klipper.elf`/`klipper.bin`/`klipper-creality.bin`. `scripts/ci.sh` proves
this on every run (builds twice, fails if they don't match). This has been independently confirmed
across two fully independent rebuilds (delete + refetch + reapply + rebuild from scratch) on the
NebulaOS dev machine, and across two independent GitHub Actions runs.

## What's *not* guaranteed, and why: compressed dictionary size varies by host zlib

The MCU firmware embeds its own command dictionary (the data a host queries at connect time to learn
the exact command/argument set this specific build supports) as a zlib-compressed blob, generated at
build time by `scripts/buildcommands.py`:

```python
datadict = json.dumps(data, separators=(',', ':'), sort_keys=True)   # deterministic input
zdatadict = bytearray(zlib.compress(datadict.encode(), 9))            # NOT deterministic in length
# ... embedded directly as command_identify_data[] in the compiled firmware
```

`datadict` (the uncompressed JSON) is itself fully deterministic - fixed key order, fixed separators,
derived only from the pinned upstream source + patch queue + `.config`. But `zlib.compress()`'s
*output length* at the same nominal compression level (9) can differ by a handful of bytes between
different builds of the zlib library, because deflate implementations aren't required to produce
identical compressed output for identical input across versions/forks - only identical *decompressed*
output. Since `command_identify_data[]`'s size is `ARRAY_SIZE`d directly into the firmware, this
propagates into the final linked binary's exact byte count and hash, even though nothing about the
patch queue, upstream pin, or `.config` differs.

This project hit exactly this: the NebulaOS dev machine's system Python links against **zlib-ng**
(Fedora's accelerated drop-in zlib replacement - `python3 -c "import zlib; print(zlib.ZLIB_VERSION)"`
reports `1.3.1.zlib-ng`), while GitHub Actions' `actions/setup-python`-provisioned interpreter links
against standard zlib. Both compress the *same* input dictionary correctly, just to slightly
different lengths (40056 bytes raw locally vs. 40048 bytes raw in CI, consistently and reproducibly
within each environment across multiple independent runs). The decompressed dictionary content - the
part that actually matters for host/MCU protocol compatibility - is identical either way.

## What this means for canonical hashes

**GitHub Actions' build (`.github/workflows/build-mcu.yml`, pinned to `actions/setup-python@v5`
`python-version: 3.12.14` plus the SHA256-pinned Arm GNU Toolchain from
`scripts/install-toolchain.sh`) is this project's canonical build environment for the KE MCU
target**, and its artifact hashes are the ones recorded in provenance and compared against future
builds/PRs. A local build on a different host is expected to be internally reproducible (two clean
builds on that same host will match each other) but is **not** guaranteed to byte-match CI's
artifact, for the zlib reason above, not because of any patch or configuration drift. If you need to
verify a local build against a CI-produced hash, compare the *decompressed* dictionaries
(`out/klipper.dict`) and the non-dictionary-derived facts (`.config` hash, patch-series hash, ELF
symbol/section layout) rather than the raw binary hash.

This is a property of upstream Klipper's own build process, not something `patches/series` in this
repository introduces or could fix without patching Klipper's own `scripts/buildcommands.py` to use a
different (or no) compression scheme - out of scope for a hardware-support patch queue.
