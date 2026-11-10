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

Written against `NebulaOS-klipper-mcu` `6648b97`, `NebulaOS-firmware` `b95b156` and
`NebulaOS-nebulascreen` `84db432`.

**This describes the release too.** NebulaOS 1.0.2 ships firmware `3bdf3ff` (tag `v1.0.2`) and
`main` has moved on since, but not one of the files behind this page differs between `3bdf3ff`
and `b95b156` - so everything below is equally true of a 1.0.2 printer. Where a NebulaOS version
would matter, this page says so.

This repository builds the firmware from upstream Klipper `58bd67db` (`upstream.lock`), which is
the same Klipper revision 1.0.2 runs on the host. That is a coincidence worth knowing but not a
rule: the host and the MCU are pinned independently, and nothing requires them to agree.

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
| `NATIVE_CANDIDATE_001` | `v0.13.0-742-g01a9c2f92`, with a pinned SHA256 | Healthy. Klipper starts. Nothing is written, and the bootloader is never entered. |
| `KNOWN_STOCK` | An exact string in `KNOWN_STOCK_VERSIONS` | `SUPPORTED_HW_KNOWN_STOCK_APP` → `RESTORE_AUTHORIZED`. `mcu_restore.py` reinstalls the native build. |
| `UNKNOWN_APPLICATION` | Anything else | **Never auto-flashed.** Left exactly as it is. |

The comparison is an exact string match - no prefix, no regex. `KNOWN_STOCK_VERSIONS` holds one
string (`38d96adc-dirty-20231016_135251-longer-virtual-machine`), observed on one printer, and
the module states that limitation itself: a plausible-looking but different Creality-style
version must classify as `UNKNOWN_APPLICATION` until a human adds it, because a wrong guess here
authorises a flash.

The guard writes a machine-readable state file under `/run/` and sets an exit code, so later
services and the screen can see the verdict without re-querying the board.

### The other identity: which board this is

What is running and what the board *is* are separate questions, and the project learned that the
hard way: the bootloader's hardware ID reads the same whether the native build or stock Creality
firmware is installed, so a bootloader-only check could never prove the native build was there.

Application identity is therefore asked first, and it is non-invasive - the same handshake
Klipper performs anyway. Only when the answer is not recognised does `mcu_lifecycle.py` enter the
bootloader and read the **hardware** ID, which must equal exactly `mcu0_001_G32`
(`MCU_EXPECTED_HW_ID`, and `creality_flash.DEFAULT_ALLOWED_HW_IDS`):

| Hardware ID | State | What happens |
|---|---|---|
| matches | `SUPPORTED_HW_UNKNOWN_APP` | Warning in the log, Klipper starts, nothing written |
| answers with a different ID | `UNSUPPORTED_HW` | **Klipper is not started** (the guard exits 1). Nothing written |
| does not answer at all | `MCU_UNREACHABLE` | Warning, Klipper starts, and the screen shows *switch the printer off and on again* |

That probe is read-only, and it always tries `app_start()` afterwards on every path, because
leaving the board sitting in its bootloader is the one outcome it must not cause; if even that
fails, the bootloader's own window times out and it returns to the application by itself.

### Why `UNKNOWN_APPLICATION` is the interesting branch

It is what makes the automation safe to leave on. The restore path only undoes the one thing it
can positively identify as not-ours: a known Creality version. A firmware you built from this
repository and installed yourself, or anything else unrecognised, is kept.

So the automation is not "NebulaOS always wants its own firmware there". It is "NebulaOS undoes
the specific change another system makes behind your back". Those are different policies, and
only the second is compatible with letting users install their own builds.

## The restore, and its bounds

`mcu_restore.py` is deliberately narrow rather than best-effort:

- **One bounded attempt.** No retry loop around the restore itself; the bootloader handshake
  alone retries, ten times at half-second intervals after a half-second settle.
- **SHA256 verification** of the on-device artifact (`/opt/nebulaos/mcu-candidates/candidate-001.bin`)
  against the pinned value in `mcu_known_identities.py`, before anything hardware-level happens.
- **The hardware-ID allow-list checked after bootloader entry and before any erase or write.**
- **Post-flash verification**: a successful transfer is not the proof. The application identity
  is read again and must classify as `NATIVE_CANDIDATE_001`, or the result is `FLASH_FAILED`.

The order is the point. Entering the bootloader changes what the board reports, so an allow-list
checked only beforehand would be trusting a pre-bootloader answer for a post-bootloader write;
and a flash that reports completion has still not shown that the board runs what was written.

A restore that does not reach `RESTORED_AND_VERIFIED` - `CANDIDATE_ARTIFACT_MISSING`,
`CANDIDATE_HASH_BAD` or `FLASH_FAILED` - **stops the boot: Klipper is not started.** There is no
fallback to stock. The printer is left with the diagnostics rather than running against an MCU
whose state nobody established.

### What the state file says afterwards

A verified restore is reported as the board is *now*, not as it was found: `MCU_LIFECYCLE_STATE`
becomes `SUPPORTED_HW_NATIVE_APP`, `MCU_APPLICATION_CLASS` `NATIVE_CANDIDATE_001`,
`MCU_HW_ID_STATUS` `MATCH`, and what it ran before is preserved in `MCU_LIFECYCLE_DETAIL` as
`restored_from_known_stock (was <version>)`. `MCU_RESTORE_RESULT` and `MCU_RESTORE_DETAIL` carry
the restore's own verdict.

### The one failure a user can fix

After Creality's system has restarted into NebulaOS **by software**, which its USB updater does,
the mainboard will not accept new firmware until the power is actually cut. NebulaOS retries at
every start, so one power cycle is the whole fix, and the guard says exactly that on the screen:
*the mainboard firmware could not be installed; switch the printer off, wait 10 seconds and
switch it on again*.

The notice is written for every `FLASH_FAILED` **except** the two whose cause a power cycle
cannot change: a board that is not a KE (`hardware_identity_mismatch`) and a built-in firmware
file that could not even be checked (`candidate_validation_error`, an unexpected error reading
it). A missing or hash-mismatched candidate is not `FLASH_FAILED` at all - it is
`CANDIDATE_ARTIFACT_MISSING` or `CANDIDATE_HASH_BAD`, and gets no notice either. Telling a user
to power-cycle their way out of a wrong board would cost them three attempts and their
confidence in every later message.

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

### Both controls are KE-only

The screen's **Install MCU firmware** and **Reinstall built-in MCU firmware**, `nebulaos-mcu`,
and the automatic restore above all assume the KE's mainboard: the Creality header at offset
`0x200`, the hardware ID `mcu0_001_G32`, and Creality's serial bootloader on `/dev/ttyS1`. They
must not be used for any other board, and they refuse to: an image without the header is
rejected before the board is touched, and a board that answers with another hardware ID is never
written to.

People running a Nebula Pad on a different Creality printer therefore flash their mainboard the
way that board is normally flashed - almost always an SD card. What is known about those builds,
including which `make menuconfig` settings other people have used, is collected in the wiki page
[Other printers (experimental, untested)](https://github.com/NebulaOS-KE/NebulaOS/wiki/Other-Printers-Experimental).
Nothing there has been tested with NebulaOS, and note the hardware-ID table above: on a board
whose own bootloader answers with a different ID, this guard **blocks the Klipper start** rather
than warning.

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
- The wiki's [Other printers (experimental, untested)](https://github.com/NebulaOS-KE/NebulaOS/wiki/Other-Printers-Experimental)
  - community mainboard builds for other Nebula Pad printers, none of them tested here
