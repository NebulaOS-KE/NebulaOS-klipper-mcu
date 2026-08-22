#!/usr/bin/env python3
"""Pack a raw GD32F303 Klipper application binary into a Creality-compatible
MCU firmware image.

The raw binary (produced by this repo's build with MACH_GD32F303 selected)
already reserves exactly 16 bytes at offset 0x200 for the Creality metadata
header - see src/stm32/gd32_creality_metadata.c and
src/generic/armcm_link.lds.S. This tool only OVERWRITES those 16 bytes; it
never inserts bytes, so the packaged image is always the same length as the
raw input. That in-place design is deliberate: Phase 1.6B found that naively
inserting a 16-byte header into an already-linked binary would shift every
byte after it and corrupt the image.

Header layout (offset 0x200, 16 bytes total), reverse-engineered and
verified against four stock Creality MCU images in Phase 1.6B:

    0x200  4   type       ASCII, e.g. "mcu0"
    0x204  1   separator  "_"
    0x205  3   version    ASCII 3-digit version, e.g. "001"
    0x208  1   separator  "_"
    0x209  3   reserved   ASCII, always "000"
    0x20C  2   crc16      CRC-16/XMODEM, little-endian
    0x20E  2   length     total packaged file size, little-endian

CRC-16/XMODEM (poly 0x1021, init 0x0000, no reflect, no xorout) is computed
over the ENTIRE packaged file with bytes 0x20C-0x20F (the CRC and length
fields themselves) held at zero.

The Creality length field is 16 bits, so any packaged image over 65535
bytes cannot be represented and must not be produced.
"""

import argparse
import struct
import sys

METADATA_OFFSET = 0x200
METADATA_SIZE = 0x10
CRC_LEN_OFFSET = 0x20C
LENGTH_OFFSET = 0x20E
MAX_IMAGE_SIZE = 65535


class PackError(Exception):
    pass


def crc16_xmodem(data: bytes) -> int:
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def pack(raw: bytes, type_code: str = "mcu0", version: str = "001",
         reserved: str = "000") -> bytes:
    if len(type_code) != 4:
        raise PackError(f"type code must be exactly 4 ASCII chars, got {type_code!r}")
    if len(version) != 3:
        raise PackError(f"version must be exactly 3 ASCII chars, got {version!r}")
    if len(reserved) != 3:
        raise PackError(f"reserved must be exactly 3 ASCII chars, got {reserved!r}")
    if len(raw) < METADATA_OFFSET + METADATA_SIZE:
        raise PackError(
            f"raw binary ({len(raw)} bytes) is smaller than the metadata "
            f"window end (0x{METADATA_OFFSET + METADATA_SIZE:x}) - this is "
            "not a GD32F303 build with the metadata reservation patch")

    image = bytearray(raw)

    header_text = f"{type_code}_{version}_{reserved}".encode("ascii")
    assert len(header_text) == 12
    image[METADATA_OFFSET:METADATA_OFFSET + 12] = header_text

    total_len = len(image)
    if total_len > MAX_IMAGE_SIZE:
        raise PackError(
            f"packaged image is {total_len} bytes, exceeds the Creality "
            f"16-bit length field limit of {MAX_IMAGE_SIZE} bytes - "
            "refusing to produce an unflashable image")

    struct.pack_into("<H", image, LENGTH_OFFSET, total_len)

    masked = bytearray(image)
    masked[CRC_LEN_OFFSET:CRC_LEN_OFFSET + 4] = b"\x00\x00\x00\x00"
    crc = crc16_xmodem(bytes(masked))
    struct.pack_into("<H", image, CRC_LEN_OFFSET, crc)

    # Invariant: packing must never change the file length.
    assert len(image) == len(raw), "packer must not insert or remove bytes"

    return bytes(image)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw_bin", help="raw klipper.bin (with reserved metadata window)")
    ap.add_argument("output", help="path to write the packaged Creality image")
    ap.add_argument("--type", default="mcu0", help="4-char type code (default: mcu0)")
    ap.add_argument("--version", default="001", help="3-digit metadata version (default: 001)")
    ap.add_argument("--reserved", default="000", help="3-char reserved field (default: 000)")
    args = ap.parse_args()

    with open(args.raw_bin, "rb") as f:
        raw = f.read()

    try:
        image = pack(raw, args.type, args.version, args.reserved)
    except PackError as e:
        print(f"PACK FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "wb") as f:
        f.write(image)

    print(f"Wrote {args.output}: {len(image)} bytes, "
          f"type={args.type} version={args.version}")


if __name__ == "__main__":
    main()
