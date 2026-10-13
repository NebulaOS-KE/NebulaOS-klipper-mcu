# Building your own MCU firmware for the Ender-3 V3 KE

You can build your own Klipper firmware for the KE's mainboard (GD32F303RET6) and install it from
the NebulaOS touchscreen (**Settings → Printer → MCU firmware**): put the `.bin` on a USB stick, or
upload it in Mainsail to `config/firmware/mcu`.

**There is one hard requirement. Read this before you build.**

## The requirement: the Creality header at offset 0x200

The KE's mainboard keeps Creality's bootloader. It is never replaced, and it is what makes
installing from the printer possible. That bootloader **only accepts an image that carries a
16-byte Creality header at offset 0x200 of the application image**:

| Offset | Size | Field | Example |
|---|---|---|---|
| 0x200 | 4 | board type, ASCII | `mcu0` |
| 0x204 | 1 | separator | `_` |
| 0x205 | 3 | version, ASCII | `900` |
| 0x208 | 1 | separator | `_` |
| 0x209 | 3 | reserved, ASCII | `000` |
| 0x20C | 2 | CRC-16/XMODEM over the whole file, with 0x20C–0x20F counted as zero, little-endian | |
| 0x20E | 2 | total file size, little-endian | |

Creality's own firmware carries the same header. Without it the bootloader refuses the image.

### Why a firmware from an arbitrary Klipper source does not work

In a normal (upstream) Klipper build for this chip, the interrupt vector table at the start of the
image is about 0x150 bytes long, and **offset 0x200 already holds program code**. The header cannot
be inserted there (every byte after it would shift and the image would break), and it cannot be
written over the code either. NebulaOS refuses such a file with *"not built for this printer's
mainboard"* rather than install something that cannot run.

### How this repository solves it

The patch in `patches/0001-stm32-add-native-gd32f303-ke-support.patch` adds
`src/stm32/gd32_creality_metadata.c` and a linker section in `src/generic/armcm_link.lds.S` that
**reserve exactly those 16 bytes at app+0x200**, filled with `0xFF`, between the vector table and
the rest of the firmware. The linker asserts that the vector table ends before 0x200 and that the
reserved window is exactly 16 bytes.

So a plain `make` in a tree built by this repository gives an image with an empty header slot.

## What NebulaOS accepts

| File | What it is | What NebulaOS does |
|---|---|---|
| `out/klipper.bin` from a tree built by this repository | the **raw** build, header slot still `0xFF` | fills in the header itself (`mcu0`, version `900`, CRC, length) and installs it. You never need the packer |
| `klipper-creality.bin` from `scripts/ci.sh` / `tools/creality_packer.py` | the **packed** image, header filled in | checks the header and installs it |
| anything else | upstream Klipper, other forks without the reservation, another board's firmware | refused, with the reason on screen |

Before anything touches the board, NebulaOS also checks:
- the size: at most **65535 bytes**, because the header's length field is 16 bits;
- the CRC;
- the vector table: the stack pointer must be in the 64 KB SRAM and the reset vector in app flash
  from 0x08003000;
- the **Klipper release** the firmware was built from, read from the firmware's own data
  dictionary.

## Building

Use this repository; don't start from upstream Klipper:

```sh
git clone https://github.com/coreflake1/NebulaOS-klipper-mcu.git
cd NebulaOS-klipper-mcu
./scripts/ci.sh            # fetches the pinned Klipper, applies the patch, builds and packs
```

To change the build configuration (features, sensors), run `make menuconfig` in the patched build
tree, but **keep these settings, or the board cannot start the firmware**:

| Setting | Value | Why |
|---|---|---|
| Micro-controller | GD32F303 (`CONFIG_MACH_GD32F303`) | the KE's chip; also what enables the header reservation |
| Bootloader offset | 12 KiB, app at 0x08003000 (`CONFIG_STM32_FLASH_START_3000`) | where Creality's bootloader starts the application, and where the header is expected relative to it |
| Clock reference | 8 MHz crystal | the KE board |
| Communication | USART2, 230400 baud | the link to the Nebula Pad that NebulaOS's Klipper uses |

## Compatibility with NebulaOS's Klipper

The firmware must speak the same protocol as the Klipper running on the printer.
- **Same Klipper release** (for example v0.13.0) as NebulaOS's own MCU firmware: fine, even from a
  different commit.
- **Another release**: NebulaOS shows a warning before installing. Klipper will then most likely
  refuse to connect to the board.

Either way, **Settings → Printer → MCU firmware → Reinstall NebulaOS firmware** puts the built-in,
known-good firmware back.

## What is not supported

- **Firmware without the header reservation**, including upstream Klipper and forks that don't carry
  the equivalent of `gd32_creality_metadata.c`. A stub-loader approach that would allow any source
  was considered and deferred: less space, an unproven way back for the next flash, and little gain
  over building from here.
- **Replacing Creality's bootloader** (SWD/debug probe). NebulaOS never does this; it needs hardware
  access and can leave the board unusable.
