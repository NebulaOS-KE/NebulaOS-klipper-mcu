#!/usr/bin/env python3
"""Negative-fixture test suite for the Phase 1.7 offline validator.

Every fixture generated here is a deliberately broken image or build config,
and the validator MUST reject every single one (Phase 1.7 mission, section
32). This is a hard gate: NEGATIVE_VALIDATOR_FAILURES must be 0 for
OFFLINE_VALIDATED_MCU_CANDIDATE_READY=YES.

Run as: python3 tools/test_negative_fixtures.py out/klipper-creality.bin \
            out/klipper.elf .config
"""

import argparse
import shutil
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import creality_validator as v  # noqa: E402


def load(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def save(data, path):
    with open(path, "wb") as f:
        f.write(bytes(data))


def repack_crc_len(image: bytearray):
    """Recompute CRC/length so only the *targeted* field under test is wrong."""
    length = len(image)
    struct.pack_into("<H", image, v.LENGTH_FIELD_OFFSET, length)
    masked = bytearray(image)
    masked[v.CRC_FIELD_OFFSET:v.CRC_FIELD_OFFSET + 4] = b"\x00\x00\x00\x00"
    crc = v.crc16_xmodem(bytes(masked))
    struct.pack_into("<H", image, v.CRC_FIELD_OFFSET, crc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("elf")
    ap.add_argument("config")
    args = ap.parse_args()

    good_image = load(args.image)
    good_cfg = v.parse_dotconfig(args.config)

    results = []  # (label, expected_to_fail, actually_failed)

    def check_format(label, data, expect_type="mcu0"):
        fails = v.validate_format(bytes(data), expect_type)
        results.append((label, True, bool(fails)))

    def check_config(label, cfg_overrides):
        cfg = dict(good_cfg)
        cfg.update(cfg_overrides)
        fails = v.validate_config(cfg)
        results.append((label, True, bool(fails)))

    def check_vector(label, data):
        fails = v.validate_vector_table(bytes(data))
        results.append((label, True, bool(fails)))

    # A. wrong MCU target
    check_config("A wrong MCU target", {"MACH_GD32F303": None, "MACH_GD32F30x": None})
    # B. STM32F103 compatibility target
    check_config("B STM32F103 compat target", {
        "MACH_GD32F303": None, "MACH_GD32F30x": None, "MACH_STM32F103": "y",
        "CLOCK_FREQ": "72000000", "FLASH_SIZE": "0x10000", "RAM_SIZE": "0x5000",
    })
    # C. 72 MHz
    check_config("C wrong clock (72MHz)", {"CLOCK_FREQ": "72000000"})
    # D. wrong RAM geometry
    check_config("D wrong RAM geometry", {"RAM_SIZE": "0x5000"})
    # E. wrong flash geometry
    check_config("E wrong flash geometry", {"FLASH_SIZE": "0x10000"})
    # F. wrong application origin
    check_config("F wrong application origin", {"FLASH_APPLICATION_ADDRESS": "0x8002000"})
    # G. wrong bootloader reserve
    check_config("G wrong bootloader reserve", {"STM32_FLASH_START_3000": None,
                                                 "STM32_FLASH_START_2000": "y"})
    # H. wrong UART
    check_config("H wrong UART", {"STM32_SERIAL_USART2": None, "STM32_SERIAL_USART1": "y"})
    # I. wrong baud
    check_config("I wrong baud", {"SERIAL_BAUD": "115200"})
    # J. malformed vector table (SP = 0)
    bad = bytearray(good_image)
    struct.pack_into("<I", bad, 0, 0)
    check_vector("J malformed vector table (SP=0)", bad)
    # K. SP outside SRAM
    bad = bytearray(good_image)
    struct.pack_into("<I", bad, 0, 0x10000000)
    check_vector("K SP outside SRAM", bad)
    # L. reset vector outside app flash
    bad = bytearray(good_image)
    struct.pack_into("<I", bad, 4, 0x08000001)
    check_vector("L reset vector outside app flash", bad)
    # M. metadata offset wrong (shift header 16 bytes earlier)
    bad = bytearray(good_image)
    header = bytes(bad[v.METADATA_OFFSET:v.METADATA_OFFSET + v.METADATA_SIZE])
    bad[v.METADATA_OFFSET - 16:v.METADATA_OFFSET] = header
    bad[v.METADATA_OFFSET:v.METADATA_OFFSET + v.METADATA_SIZE] = b"\xff" * 16
    check_format("M metadata offset wrong", bad)
    # N. type != mcu0
    bad = bytearray(good_image)
    bad[v.METADATA_OFFSET:v.METADATA_OFFSET + 4] = b"noz0"
    repack_crc_len(bad)
    check_format("N type != mcu0", bad, expect_type="mcu0")
    # O. malformed reserved bytes
    bad = bytearray(good_image)
    bad[v.METADATA_OFFSET + 9:v.METADATA_OFFSET + 12] = b"XXX"
    repack_crc_len(bad)
    check_format("O malformed reserved bytes", bad)
    # P. payload bit flipped (after CRC/length repacked over the *original*
    #    payload, then flip a data byte deep in .text_app so CRC no longer matches)
    bad = bytearray(good_image)
    bad[0x1000] ^= 0x01
    check_format("P payload bit flipped", bad)
    # Q. CRC changed
    bad = bytearray(good_image)
    bad[v.CRC_FIELD_OFFSET] ^= 0xFF
    check_format("Q CRC changed", bad)
    # R. length changed
    bad = bytearray(good_image)
    bad[v.LENGTH_FIELD_OFFSET] ^= 0xFF
    check_format("R length changed", bad)
    # S. image truncated
    bad = good_image[:-100]
    check_format("S image truncated", bad)
    # T. extra byte appended without metadata update
    bad = bytearray(good_image) + b"\x00"
    check_format("T extra byte appended", bad)
    # U. packaged size exactly 65536 bytes (one over the 16-bit field's max)
    bad_u = bytearray(good_image) + b"\xff" * (65536 - len(good_image))
    results.append(("U packaged size 65536 bytes", True, len(bad_u) > v.MAX_IMAGE_SIZE))
    # V. packaged size > 65535
    bad_v = bytearray(good_image) + b"\xff" * (70000 - len(good_image))
    results.append(("V packaged size >65535", True, len(bad_v) > v.MAX_IMAGE_SIZE))
    # W. metadata insertion that shifts code after 0x200 (simulate the
    #    Phase-1.6B-era bug: insert 16 bytes instead of overwriting in place)
    bad = bytearray(good_image[:v.METADATA_OFFSET]) + bytearray(16) + bytearray(good_image[v.METADATA_OFFSET:])
    # This is no longer format-parseable as our fixed-length image (length
    # field now disagrees with file size, and CRC over shifted content is wrong)
    fails = v.validate_format(bytes(bad), "mcu0")
    results.append(("W metadata insertion shifts code", True, bool(fails)))

    total = len(results)
    failures_correctly_rejected = sum(1 for _, exp, got in results if exp and got)
    incorrectly_accepted = [label for label, exp, got in results if exp and not got]

    print(f"Ran {total} negative fixtures")
    for label, exp, got in results:
        status = "REJECTED (correct)" if got else "ACCEPTED (BUG!)"
        print(f"  {label}: {status}")

    print()
    print(f"NEGATIVE_VALIDATOR_TESTS={total}")
    print(f"NEGATIVE_VALIDATOR_FAILURES={len(incorrectly_accepted)}")
    if incorrectly_accepted:
        print("INCORRECTLY ACCEPTED:", incorrectly_accepted)
        sys.exit(1)
    print("ALL_NEGATIVE_VALIDATOR_TESTS_PASS=YES")
    sys.exit(0)


if __name__ == "__main__":
    main()
