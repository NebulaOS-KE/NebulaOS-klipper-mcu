# MCU firmware on a printer: identity, restore and install

This repository documents how to *build* MCU firmware. This page covers what happens to that
firmware once it is on a printer: how NebulaOS identifies what the board is running, when it
replaces it automatically, when it deliberately does not, and how a user installs their own.

The mechanism spans three repositories, which is why it had no home until now:

| What | Where |
|---|---|
| Building the firmware, the Creality header, compatibility | this repository |
| Identity check and automatic restore at boot | `NebulaOS-firmware` |
| The user-facing install and reinstall controls | `NebulaOS-nebulascreen` |

Written against `NebulaOS-klipper-mcu` `33f5d16`, `NebulaOS-firmware` `832314d` and
`NebulaOS-nebulascreen` `dee0f6f`.

## The thing to understand first

**Both systems reinstall their own MCU firmware, so switching between them is self-correcting.**

Creality's system installs its firmware when it starts from a cold power-on. NebulaOS checks
the board at every boot and reinstalls the native build when it finds a known Creality version
there. Neither direction needs a human, and neither is a dead end.

This is worth stating plainly because it is easy to read the Phase 1.8B decision - removing the
automatic rollback into stock - as implying the opposite. It does not. That decision avoided an
*unrequested* MCU firmware change; it did not mean a stock boot leaves the board permanently
wrong.

## Identity, at boot

`S50nebulaos-mcu-guard` runs before Klipper and delegates to `mcu_lifecycle.py`, which asks the
MCU what application it is running and classifies the answer by its **version string**
(`mcu_known_identities.py`):

| Classification | Recognised as | What happens |
|---|---|---|
| `NATIVE_CANDIDATE_001` | `v0.13.0-742-g01a9c2f92`, with a pinned SHA256 | Healthy. Klipper starts. Nothing is written. |
| `KNOWN_STOCK` | A version in `KNOWN_STOCK_VERSIONS` | `SUPPORTED_HW_KNOWN_STOCK_APP` → `RESTORE_AUTHORIZED`. `mcu_restore.py` reinstalls the native build. |
| `UNKNOWN_APPLICATION` | Anything else | **Never auto-flashed.** Left exactly as it is. |

The guard writes a machine-readable state file under `/run/` and sets an exit code, so later
services and the screen can see the verdict without re-querying the board.

### Why `UNKNOWN_APPLICATION` is the interesting branch

It is what makes the automation safe to leave on. The restore path only undoes the one thing it
can positively identify as not-ours: a known Creality version. A firmware you built from this
repository and installed yourself, or anything else unrecognised, is kept.

So the automation is not "NebulaOS always wants its own firmware there". It is "NebulaOS undoes
the specific change another system makes behind your back". Those are different policies, and
only the second is compatible with letting users install their own builds.

## The restore, and its bounds

`mcu_restore.py` is deliberately narrow rather than best-effort:

- **One bounded attempt.** It does not retry in a loop.
- **SHA256 verification** of the on-device artifact against a pinned value, before use.
- **A hardware identity allow-list**, checked *before* any erase or write, and **again after
  bootloader entry**.

That second check is the one worth noticing. Entering the bootloader changes what the board
reports, so an allow-list checked only beforehand would be trusting a pre-bootloader answer for
a post-bootloader write. Checking twice costs almost nothing and closes that gap.

## Installing firmware yourself

NebulaScreen's MCU page - **Settings → Printer → MCU firmware** - offers:

- **Built-in MCU firmware** - reinstall the version that shipped in the image. Always available,
  needs no file, and is the way back from anything you installed.
- **Install MCU firmware** - install a `.bin` you provide, from a USB stick or uploaded in
  Mainsail to **Machine → config → uploads → mainboard-firmware**.

The flash stops Klipper, enters the bootloader, writes, and restarts Klipper. **The screen tells
the user not to switch the printer off while this runs**, and that is the one genuine caution in
the whole lifecycle - cutting power mid-write is the only normal-use action that can leave the
board needing a computer to recover.

For users, that is documented in the end-user manual's *Mainboard firmware* page.

## What the board is

From `compatibility.json` in this repository:

| | |
|---|---|
| Platform | `gd32f303ret6` |
| Architecture | Cortex-M4 |
| Clock | 120 MHz |
| Flash | 524288 bytes |
| RAM | 65536 bytes |
| Bootloader reserved | 12288 bytes |

The host side of that manifest requires the Klipper feature set `load_cell_probe`,
`trigger_analog` and `hx71x`, and records `host_core_patches_required: false` - the host runs
unmodified upstream Klipper, consistent with how `NebulaOS-klipper-extensions` is composed in
rather than forked.

## Qualification status, as the repository states it

`compatibility.json` carries its own status fields, and they are worth quoting rather than
paraphrasing:

```json
"status": { "offline_validated": true, "hardware_qualified": false }
```

So this repository declares the firmware offline-validated and **not** hardware-qualified. That
is its own assessment, not this page's, and it is a narrower claim than "does not work" - the
native build is what a NebulaOS printer runs, and the restore path above exists precisely
because it does.

Anyone needing to know whether a particular build has been run on a particular printer should
ask the project owner rather than infer it from this field.

## Related

- [Building your own firmware](BUILDING_YOUR_OWN_FIRMWARE.md) - the Creality header at offset
  `0x200`, what NebulaOS accepts, and what is not supported
- [Architecture](ARCHITECTURE.md) - why a patch queue rather than a fork
- [Reproducibility](REPRODUCIBILITY.md) - why artifact hashes can legitimately differ
- `NebulaOS-firmware`'s `docs/reference/ARCHITECTURE.md` - boot, slots and recovery
