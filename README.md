# NebulaOS-klipper-mcu

`NebulaOS-klipper-mcu` does not fork or vendor Klipper.

It builds Ender-3 V3 KE (Creality Nebula Pad, GD32F303RET6) MCU firmware from a pinned official
[`Klipper3d/klipper`](https://github.com/Klipper3d/klipper) revision plus a small, explicit patch
series. NebulaOS's host Klipper (`NebulaOS-firmware`) remains a separate, independently pinned
official upstream checkout with **zero host-core patches** — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for why the host and MCU source policies are
deliberately different.

**Status: the MCU artifact this repository builds is OFFLINE VALIDATED, but NOT yet HARDWARE
QUALIFIED.** No firmware built here has been flashed to a real printer. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the NebulaOS workspace's
`_project/missions/2026-08-phase1.7-native-gd32-build.md` for the full closure report.

## How this repository is structured

| Path | Purpose |
|---|---|
| [`upstream.lock`](upstream.lock) | The exact upstream Klipper repo + commit SHA this build pins. Authoritative — the build fails if the fetched checkout doesn't match it exactly. |
| [`compatibility.json`](compatibility.json) | Machine-readable MCU target facts and the host feature-set this firmware is compatible with. |
| [`patches/`](patches/) | The explicit, ordered patch queue (`series`) applied on top of the pinned upstream checkout. Currently one patch: native GD32F303RET6 (Cortex-M4) target support, following the existing `src/stm32/` N32G45x clone precedent. |
| [`configs/`](configs/) | The noninteractive Kconfig seed (`ender3-v3-ke.defconfig`) for the KE target. |
| [`tools/`](tools/) | NebulaOS-owned tooling: the Creality image packer, offline format/target validator, negative-fixture test suite, future flasher (safe-by-default, hardware-gated), and provenance generator. None of this is Klipper source. |
| [`tests/`](tests/) | Offline config-parse regression fixtures run through Klipper's own `scripts/test_klippy.py` harness against this target's build dictionary. |
| [`scripts/`](scripts/) | `fetch-upstream.sh`, `apply-patches.sh`, `build.sh`, `install-toolchain.sh`, `guard-no-vendored-source.sh`, and `ci.sh` (the canonical entrypoint — GitHub Actions is a thin wrapper around it). |
| [`.github/workflows/build-mcu.yml`](.github/workflows/build-mcu.yml) | Runs `scripts/ci.sh` on push/PR/dispatch and uploads the resulting artifacts. Never flashes hardware. |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | What's guaranteed reproducible, what isn't (and why - a host zlib-implementation difference, not this repo's patch queue), and which build's hashes are canonical. |

This repository must **never** contain a vendored copy of Klipper's `klippy/`, `src/`, `lib/`, or
`docs/` trees — `scripts/guard-no-vendored-source.sh` fails CI if it ever does. The upstream Klipper
checkout used to build is fetched fresh into a disposable, gitignored `build/` directory on every
build; it is never committed here.

## Build

```sh
git clone https://github.com/coreflake1/NebulaOS-klipper-mcu.git
cd NebulaOS-klipper-mcu
./scripts/ci.sh
```

This mechanically: reads `upstream.lock`; clones official `Klipper3d/klipper` and checks out the
exact pinned SHA (failing hard on any mismatch); applies `patches/series` as a clean, deterministic
commit; builds twice and verifies the raw binary is byte-identical across both builds; packs the
result into a Creality-format image; runs the offline validator (target checks plus, optionally,
known-good stock fixtures if `STOCK_FIXTURE_DIR` is set — proprietary Creality binaries are never
committed to this repository); runs the 23-case negative-fixture suite; runs the flasher's
fake-transport unit tests; parses the KE's real `[load_cell_probe]` config against the built
dictionary; and emits a provenance manifest. All artifacts land in `artifacts/` (gitignored).

Requires `arm-none-eabi-gcc`/`arm-none-eabi-ld` on `PATH` (or point `TOOLCHAIN_BIN` at a toolchain's
`bin/` directory — `scripts/install-toolchain.sh` downloads and SHA256-verifies the exact pinned
toolchain CI uses).

## Hardware

**No hardware flashing happens in this repository or its CI.** `tools/creality_flash.py` implements
the future flasher, but its `flash()` path is safe-by-default: it refuses to proceed unless the image
independently passes the validator *and* the live bootloader's reported hardware identity matches an
explicit allow-list (default: exactly `mcu0_001_G32`). It has only ever been exercised against a fake
in-memory transport in `tools/test_creality_flash.py`. The first real-hardware operation this project
authorizes is a **read-only** bootloader identity query — see the NebulaOS workspace's Phase 1.8
mission plan.
