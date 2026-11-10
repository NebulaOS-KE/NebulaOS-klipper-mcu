# NebulaOS-klipper-mcu

> Part of [NebulaOS](https://github.com/NebulaOS-KE/NebulaOS): open firmware for the Creality Ender-3 V3 KE. The project map, releases and downloads are there.

`NebulaOS-klipper-mcu` does not fork or vendor Klipper.

It builds Ender-3 V3 KE (Creality Nebula Pad, GD32F303RET6) MCU firmware from a pinned official
[`Klipper3d/klipper`](https://github.com/Klipper3d/klipper) revision plus a small, explicit patch
series. NebulaOS's host Klipper (`NebulaOS-firmware`) remains a separate, independently pinned
official upstream checkout with **zero host-core patches** — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for why the host and MCU source policies are
deliberately different.

**Status: the MCU artifact this repository builds is OFFLINE VALIDATED, and this repository
claims no HARDWARE QUALIFICATION for it** - `compatibility.json` records
`"hardware_qualified": false`, and that assessment is the project owner's to make, not a
document's. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the NebulaOS workspace's
`_project/missions/2026-08-phase1.7-native-gd32-build.md` for the full closure report.

Read that as *no qualification claim*, not as *never run*. What has happened on real hardware is
recorded in `NebulaOS-firmware`, not here: the build from this repository's patch queue
(candidate-001, `mcu_repo_commit` `3aefd28`, patch commit `01a9c2f9`) is the MCU firmware a
NebulaOS printer runs; it was flashed and queried live during its 2026-08-28 qualification run,
which found three real bugs no mocked test could have caught; and the boot-time path that
reinstalls it was exercised again on the development printer on 2026-11-05. The record is in that
repository's `docs/MCU_LIFECYCLE_GUARD.md`, `mcu_restore.py` and `S50nebulaos-mcu-guard`, and
[`docs/MCU_FIRMWARE_LIFECYCLE.md`](docs/MCU_FIRMWARE_LIFECYCLE.md) here explains the mechanism.

## Building your own firmware: read this first

> **Firmware for the KE must carry Creality's 16-byte header at offset 0x200.** The board keeps
> Creality's bootloader, and it refuses any image without that header. Upstream Klipper (and forks
> without this repository's patch) has program code at 0x200, so it **cannot** be made to fit.
> Build from this repository: its patch reserves the 16 bytes, and NebulaOS fills them in when you
> install a plain `out/klipper.bin` from the touchscreen (**Settings → Printer → MCU firmware**).
>
> Details, the settings you must keep, and what NebulaOS checks before installing:
> [`docs/BUILDING_YOUR_OWN_FIRMWARE.md`](docs/BUILDING_YOUR_OWN_FIRMWARE.md).

## What happens to the firmware on a printer

[MCU firmware lifecycle](docs/MCU_FIRMWARE_LIFECYCLE.md) covers how NebulaOS identifies what the
board is running, when it reinstalls the native build automatically, why a firmware you installed
yourself is never overwritten, and how a user installs their own. Short version: both systems
restore their own MCU firmware at boot, so switching between NebulaOS and Creality's system is
self-correcting in both directions.

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
| [`docs/BUILDING_YOUR_OWN_FIRMWARE.md`](docs/BUILDING_YOUR_OWN_FIRMWARE.md) | The 0x200 header requirement, the settings to keep, and what NebulaOS accepts when you install your own build from the touchscreen. |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | What's guaranteed reproducible, what isn't (and why - a host zlib-implementation difference, not this repo's patch queue), and which build's hashes are canonical. |

This repository must **never** contain a vendored copy of Klipper's `klippy/`, `src/`, `lib/`, or
`docs/` trees — `scripts/guard-no-vendored-source.sh` fails CI if it ever does. The upstream Klipper
checkout used to build is fetched fresh into a disposable, gitignored `build/` directory on every
build; it is never committed here.

## Build

```sh
git clone https://github.com/NebulaOS-KE/NebulaOS-klipper-mcu.git
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
explicit allow-list (default: exactly `mcu0_001_G32`). **This copy** has only ever been exercised
against a fake in-memory transport in `tools/test_creality_flash.py`, and no NebulaOS automation
runs it: a printer runs the copy deployed by `NebulaOS-firmware` at `/opt/nebulaos/tools/`.

**Those two copies have diverged, and this one is the older.** The deployed copy was taken
verbatim from `tools/` at commit `c793e77` (its `provenance.json` sidecar records the hash this
file still has), and has since gained two fixes that only real hardware could surface: opening
the port with DTR and RTS held low, the way pyserial 3.5 actually supports — the keyword-argument
form raises `ValueError`, so the guard could not open the port at all on ke-dev on 2026-10-03 —
and a `close()` on the transport, without which the post-flash identify refused a port the
flasher itself was still holding and every successful restore was reported as a failure
(ke-dev, 2026-11-05). Neither fix is in this file. Do not use `tools/creality_flash.py` against
a printer expecting the deployed behaviour; read `NebulaOS-firmware`'s copy as the live one.
