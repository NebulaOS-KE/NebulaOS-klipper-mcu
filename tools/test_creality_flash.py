#!/usr/bin/env python3
"""Unit tests for creality_flash.py protocol logic, using a fake in-memory
transport - no serial hardware involved. Per Phase 1.7 mission section 48,
this is the ONLY way this flasher may be exercised during this mission.

Run: python3 tools/test_creality_flash.py <candidate.bin> <klipper.elf> <.config>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import creality_flash as cf  # noqa: E402


class FakeTransport(cf.Transport):
    """Simulates a Creality bootloader: handshake, version, sector size,
    and a full flash+app-start cycle, entirely in memory."""
    def __init__(self, version_string: str, sector_size: int = 1):
        self.baud = None
        self.version_string = version_string.encode("latin1")
        self.sector_size = sector_size
        self._inbox = b""
        self._flashed = bytearray()
        self._expected_size = None

    def set_baudrate(self, baud):
        self.baud = baud

    def write(self, data: bytes) -> int:
        if data == cf.MAGIC:
            return len(data)  # bootloader doesn't ack the magic itself
        if data == bytes([0x75]):
            self._inbox = bytes([0x75])
        elif data == bytes([0x00, 0xFF]):
            payload = self.version_string
            self._inbox = payload + bytes([cf.crc8_sum_complement(payload)])
        elif data == bytes([0x03, 0xFC]):
            payload = bytes([self.sector_size])
            self._inbox = payload + bytes([cf.crc8_sum_complement(payload)])
        elif data == bytes([0x02, 0xFD]):
            self._inbox = bytes([0x75, cf.crc8_sum_complement(bytes([0x75]))])
        elif data == bytes([0x01, 0xFE]):
            self._flashed = bytearray()
            self._inbox = bytes([0x75, cf.crc8_sum_complement(bytes([0x75]))])
        elif len(data) == 5 and self._expected_size is None:
            size = struct.unpack("<I", data[:4])[0]
            if data[4] != cf.crc8_sum_complement(data[:4]):
                return 0
            self._expected_size = size
            self._inbox = bytes([0x75, cf.crc8_sum_complement(bytes([0x75]))])
        else:
            # a firmware chunk: last byte is the checksum
            chunk, chksum = data[:-1], data[-1]
            if chksum != cf.crc8_sum_complement(chunk):
                self._inbox = bytes([0x1F, cf.crc8_sum_complement(bytes([0x1F]))])
                return len(data)
            self._flashed += chunk
            if len(self._flashed) >= self._expected_size:
                self._inbox = bytes([0x20, cf.crc8_sum_complement(bytes([0x20]))])
            else:
                self._inbox = bytes([0x75, cf.crc8_sum_complement(bytes([0x75]))])
        return len(data)

    def read(self, n: int) -> bytes:
        r, self._inbox = self._inbox[:n], self._inbox[n:]
        return r


def test_identify_and_check_identity():
    t = FakeTransport("mcu0_001_G32-mcu0_900_000")
    version = cf.identify(t)
    assert version == "mcu0_001_G32-mcu0_900_000", version
    assert cf.check_identity(version) is True
    assert t.baud == 115200, "identify must leave the port at bootloader baud"
    print("test_identify_and_check_identity: PASS")


def test_wrong_identity_rejected():
    t = FakeTransport("mcu0_007_G21-mcu0_900_000")  # different hw revision/family
    version = cf.identify(t)
    assert cf.check_identity(version) is False
    print("test_wrong_identity_rejected: PASS")


def test_flash_refuses_on_bad_image(tmp_path_str):
    bad_image = Path(tmp_path_str) / "bad.bin"
    bad_image.write_bytes(b"\x00" * 32)  # far too short, fails format validation
    t = FakeTransport("mcu0_001_G32-mcu0_900_000")
    try:
        cf.flash(t, str(bad_image))
        raise AssertionError("flash() should have refused a bad image")
    except cf.FlashError as e:
        assert "failed offline validation" in str(e)
    print("test_flash_refuses_on_bad_image: PASS")


def test_flash_refuses_on_wrong_identity(good_image_path):
    t = FakeTransport("mcu0_007_G21-mcu0_900_000")
    try:
        cf.flash(t, good_image_path)
        raise AssertionError("flash() should have refused a non-allow-listed identity")
    except cf.FlashError as e:
        assert "not in allow-list" in str(e)
    print("test_flash_refuses_on_wrong_identity: PASS")


def test_full_flash_cycle_on_fake_transport(good_image_path):
    t = FakeTransport("mcu0_001_G32-mcu0_900_000", sector_size=2)
    cf.flash(t, good_image_path)  # must not raise
    with open(good_image_path, "rb") as f:
        expected = f.read()
    assert bytes(t._flashed) == expected, "fake transport did not receive the exact image bytes"
    print("test_full_flash_cycle_on_fake_transport: PASS")


class _TimeoutTransport(cf.Transport):
    """Simulates a serial read timeout: every read returns nothing."""
    def set_baudrate(self, baud):
        pass
    def write(self, data: bytes) -> int:
        return len(data)
    def read(self, n: int) -> bytes:
        return b""


def test_handshake_timeout_does_not_hang():
    t = _TimeoutTransport()
    assert cf.handshake(t) is False
    print("test_handshake_timeout_does_not_hang: PASS")


class _BadChecksumTransport(cf.Transport):
    """Always answers the version query with a corrupted checksum byte."""
    def set_baudrate(self, baud):
        pass
    def write(self, data: bytes) -> int:
        return len(data)
    def read(self, n: int) -> bytes:
        payload = b"mcu0_001_G32-mcu0_900_000"
        return payload + bytes([cf.crc8_sum_complement(payload) ^ 0xFF])


def test_malformed_version_checksum_rejected():
    t = _BadChecksumTransport()
    try:
        cf.get_version(t)
        raise AssertionError("get_version should reject a bad checksum")
    except cf.FlashError as e:
        assert "checksum" in str(e)
    print("test_malformed_version_checksum_rejected: PASS")


def main():
    import tempfile
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    image, elf, config = sys.argv[1:4]

    test_identify_and_check_identity()
    test_wrong_identity_rejected()
    with tempfile.TemporaryDirectory() as d:
        test_flash_refuses_on_bad_image(d)
    test_flash_refuses_on_wrong_identity(image)
    test_full_flash_cycle_on_fake_transport(image)
    test_handshake_timeout_does_not_hang()
    test_malformed_version_checksum_rejected()
    print("\nAll creality_flash unit tests passed (fake transport only, no hardware touched)")


if __name__ == "__main__":
    main()
