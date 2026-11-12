# NebulaOS-klipper-mcu

The mainboard firmware. This repository builds Ender-3 V3 KE MCU firmware (Creality Nebula Pad,
GD32F303RET6) from a **pinned official [`Klipper3d/klipper`](https://github.com/Klipper3d/klipper)
revision plus a small, explicit patch series**. It does not fork or vendor Klipper, and
`scripts/guard-no-vendored-source.sh` fails CI if a copy of Klipper's `klippy/`, `src/`, `lib/`
or `docs/` ever appears here.

This wiki is the developer documentation. The end-user page about mainboard firmware is in the
[NebulaOS manual](https://github.com/NebulaOS-KE/NebulaOS/wiki/Mainboard-Firmware).

## Which code this describes

| | |
|---|---|
| This repository | `6648b97` (tip of `main`) |
| Lifecycle described against | firmware `b95b156`, with the 1.0.2 boundary (`3bdf3ff`) stated where it bites |
| What a printer runs | the vendored build **candidate-001** in NebulaOS-firmware (`scripts/build/overlay/opt/nebulaos/mcu-candidates/candidate-001.bin`), from this repository's patch queue - `mcu_repo_commit` `3aefd28`, patch commit `01a9c2f9` |
| Upstream base | the same official Klipper commit the host runs, `58bd67db` at 1.0.2 |

## Status, stated precisely

The artifact this repository builds is **offline validated**, and this repository claims **no
hardware qualification** for it: `compatibility.json` records `"hardware_qualified": false`, and
that assessment is the project owner's to make, not a document's.

Read that as *no qualification claim*, **not** as *never run*. What has happened on real
hardware is recorded in `NebulaOS-firmware`, not here: the candidate-001 build is the MCU
firmware a NebulaOS printer runs, it was flashed and queried live during its 2026-08-28
qualification run - which found three real bugs no mocked test could have caught - and the
boot-time path that reinstalls it was exercised again on the development printer on 2026-11-05.

## The pages

- **[MCU firmware lifecycle](MCU-Firmware-Lifecycle)** - what happens to the firmware once it is
  on a printer: how NebulaOS identifies what the board is running, when it reinstalls the native
  build automatically, why firmware you installed yourself is never overwritten, the restore's
  bounds, and the one real failure mode
- **[Building your own firmware](Building-Your-Own-Firmware)** - the Creality 16-byte header at
  offset `0x200`, the settings you must keep, and what NebulaOS checks before installing
- **[Architecture](Architecture)** - why the host and MCU source policies are deliberately
  different, and why this is a patch queue rather than a fork
- **[Reproducibility](Reproducibility)** - what is guaranteed byte-identical, what is not and
  why, and which build's hashes are canonical
- **[Toolchain](Toolchain)** - the pinned Arm GNU Toolchain release and how it is verified

## Before you build your own: the header

**Firmware for the KE must carry Creality's 16-byte header at offset `0x200`.** The board keeps
Creality's bootloader and refuses any image without it. Upstream Klipper - and any fork without
this repository's patch - has program code at `0x200`, so it **cannot** be made to fit. Build
from this repository: its patch reserves those 16 bytes, and NebulaOS fills them in when you
install a plain `out/klipper.bin` from the touchscreen. Details:
[Building your own firmware](Building-Your-Own-Firmware).

## Building

```sh
git clone https://github.com/NebulaOS-KE/NebulaOS-klipper-mcu.git
cd NebulaOS-klipper-mcu
./scripts/ci.sh
```

`scripts/ci.sh` is the canonical entry point - GitHub Actions is a thin wrapper around it. It
reads `upstream.lock`, clones official Klipper and checks out the exact pinned SHA (failing hard
on any mismatch), applies `patches/series` as a clean deterministic commit, **builds twice and
verifies the raw binary is byte-identical across both builds**, packs the result into a
Creality-format image, runs the offline validator, the 23-case negative-fixture suite and the
flasher's fake-transport unit tests, parses the KE's real `[load_cell_probe]` config against the
built dictionary, and emits a provenance manifest. Artifacts land in `artifacts/` (gitignored).

Needs `arm-none-eabi-gcc`/`arm-none-eabi-ld` on `PATH`, or `TOOLCHAIN_BIN` pointing at one - see
[Toolchain](Toolchain).

## No hardware flashing happens here

Not in this repository and not in its CI. `tools/creality_flash.py` is safe by default: its
`flash()` path refuses to proceed unless the image independently passes the validator **and**
the live bootloader's reported hardware identity matches an explicit allow-list (by default
exactly `mcu0_001_G32`). This copy has only ever been exercised against a fake in-memory
transport in `tools/test_creality_flash.py`.

**And it is the older of two copies.** A printer runs the copy deployed by `NebulaOS-firmware`
at `/opt/nebulaos/tools/`, which was taken verbatim from `tools/` at commit `c793e77` and has
since gained two fixes that only real hardware could surface: opening the port with DTR and RTS
held low the way pyserial 3.5 actually supports (the keyword-argument form raises `ValueError`,
so the guard could not open the port at all - ke-dev, 2026-10-03), and a `close()` on the
transport, without which the post-flash identify refused a port the flasher was still holding
and every successful restore was reported as a failure (ke-dev, 2026-11-05). Neither fix is in
this repository's copy. Read the firmware's copy as the live one.

## This is KE-only

Everything here is specific to the Ender-3 V3 KE's mainboard. Other printers are not supported;
see the manual's
[Other printers (experimental, untested)](https://github.com/NebulaOS-KE/NebulaOS/wiki/Other-Printers-Experimental).

## Related

- [NebulaOS-firmware wiki](https://github.com/NebulaOS-KE/NebulaOS-firmware/wiki) - the image,
  the MCU guard that runs before Klipper, and the restore
- [Repository map](https://github.com/NebulaOS-KE/NebulaOS-firmware/wiki/Repository-Map)
