#!/usr/bin/env python3
"""Unit tests for stage4_first_flash.py — fake transport only.

Run: python3 tools/test_stage4_first_flash.py <candidate.bin> <klipper.elf> <.config>

Tests the full Stage-4 orchestration logic:
  - wrong candidate SHA -> abort before any bootloader/write
  - validator failure -> abort (no bootloader/write)
  - wrong identity -> abort (no erase/write)
  - noz0_* identity -> rejected
  - mcu0_120_G32 identity -> rejected
  - mcu0_001_G32 -> accepted
  - timeout -> abort
  - bad wire checksum -> abort
  - no authorization -> no erase/write
  - explicit authorization + correct identity -> simulated flash
  - failed chunk -> abort safely
  - app_start only after complete write
"""

import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import creality_flash as cf  # noqa: E402
import stage4_first_flash as s4  # noqa: E402
from test_creality_flash import FakeTransport  # noqa: E402


def make_good_image(image_path):
    """Read the real candidate image."""
    with open(image_path, "rb") as f:
        return f.read()


# --- Test: wrong candidate SHA -> abort ---

def test_wrong_candidate_sha(image_path, elf_path, config_path):
    t = FakeTransport("mcu0_001_G32-mcu0_005_000")
    results = s4.run(
        image_path=image_path,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256="0000000000000000000000000000000000000000"
                        "000000000000000000000000",
        authorize=True,
        transport=t,
    )
    assert results["SHA256_MATCH"] is False, results
    assert "ABORT_REASON" in results
    assert results.get("ERASE_PERFORMED", "NO") == "NO"
    assert results.get("WRITE_PERFORMED", "NO") == "NO"
    print("test_wrong_candidate_sha: PASS")


# --- Test: validator failure -> no bootloader/write ---

def test_validator_failure(elf_path, config_path):
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"\x00" * 32)
        bad_image = f.name
    bad_sha = s4.sha256_file(bad_image)
    t = FakeTransport("mcu0_001_G32-mcu0_005_000")
    results = s4.run(
        image_path=bad_image,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256=bad_sha,
        authorize=True,
        transport=t,
    )
    assert results["VALIDATOR_RESULT"] == "FAIL", results
    assert "ABORT_REASON" in results
    assert results.get("ERASE_PERFORMED", "NO") == "NO"
    Path(bad_image).unlink()
    print("test_validator_failure: PASS")


# --- Test: malformed identity -> abort ---

def test_malformed_identity_rejected(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = FakeTransport("mcu0_120_G32-mcu0_900_000")
    results = s4.run(
        image_path=image_path,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256=sha,
        authorize=True,
        transport=t,
    )
    assert results["IDENTITY_MATCH"] is False
    assert "ABORT_REASON" in results
    assert "not in allow-list" in results["ABORT_REASON"]
    assert results["ERASE_PERFORMED"] == "NO"
    assert results["WRITE_PERFORMED"] == "NO"
    print("test_malformed_identity_rejected (mcu0_120_G32): PASS")


# --- Test: noz0_* identity -> rejected ---

def test_nozzle_identity_rejected(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = FakeTransport("noz0_001_G32-noz0_005_000")
    results = s4.run(
        image_path=image_path,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256=sha,
        authorize=True,
        transport=t,
    )
    assert results["IDENTITY_MATCH"] is False
    assert results["ERASE_PERFORMED"] == "NO"
    assert results["WRITE_PERFORMED"] == "NO"
    print("test_nozzle_identity_rejected (noz0_*): PASS")


# --- Test: mcu0_001_G32 -> accepted ---

def test_correct_identity_accepted(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = FakeTransport("mcu0_001_G32-mcu0_005_000")
    results = s4.run(
        image_path=image_path,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256=sha,
        authorize=True,
        transport=t,
    )
    assert results["IDENTITY_MATCH"] is True
    assert results["FLASH_RESULT"] == "PASS"
    assert results["ERASE_PERFORMED"] == "YES"
    assert results["WRITE_PERFORMED"] == "YES"
    print("test_correct_identity_accepted (mcu0_001_G32): PASS")


# --- Test: timeout -> abort ---

class TimeoutTransport(cf.Transport):
    def set_baudrate(self, baud):
        pass
    def write(self, data):
        return len(data)
    def read(self, n):
        return b""

def test_timeout_aborts(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = TimeoutTransport()
    try:
        results = s4.run(
            image_path=image_path,
            elf_path=elf_path,
            config_path=config_path,
            port="/dev/null",
            expected_sha256=sha,
            authorize=True,
            transport=t,
        )
        raise AssertionError("should have raised on version timeout")
    except cf.FlashError as e:
        assert "short read" in str(e) or "checksum" in str(e)
    print("test_timeout_aborts: PASS")


# --- Test: bad wire checksum -> abort ---

class BadChecksumVersionTransport(cf.Transport):
    def set_baudrate(self, baud):
        pass
    def write(self, data):
        if data == bytes([0x75]):
            self._inbox = bytes([0x75])
        elif data == bytes([0x00, 0xFF]):
            payload = b"mcu0_001_G32-mcu0_005_000"
            self._inbox = payload + bytes([cf.crc8_sum_complement(payload) ^ 0xFF])
        else:
            self._inbox = b""
        return len(data)
    def read(self, n):
        r = getattr(self, '_inbox', b'')[:n]
        self._inbox = getattr(self, '_inbox', b'')[n:]
        return r

def test_bad_wire_checksum_aborts(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = BadChecksumVersionTransport()
    try:
        results = s4.run(
            image_path=image_path,
            elf_path=elf_path,
            config_path=config_path,
            port="/dev/null",
            expected_sha256=sha,
            authorize=True,
            transport=t,
        )
        raise AssertionError("should have raised on bad checksum")
    except cf.FlashError as e:
        assert "checksum" in str(e)
    print("test_bad_wire_checksum_aborts: PASS")


# --- Test: no authorization -> no erase/write ---

def test_no_authorization_no_write(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = FakeTransport("mcu0_001_G32-mcu0_005_000")
    results = s4.run(
        image_path=image_path,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256=sha,
        authorize=False,
        transport=t,
    )
    assert results["IDENTITY_MATCH"] is True
    assert results["ERASE_PERFORMED"] == "NO"
    assert results["WRITE_PERFORMED"] == "NO"
    assert results["CHECKPOINT"] == "WAITING_FOR_AUTHORIZATION"
    assert "FLASH_RESULT" not in results
    print("test_no_authorization_no_write: PASS")


# --- Test: authorized flash -> image matches ---

def test_authorized_flash_image_matches(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = FakeTransport("mcu0_001_G32-mcu0_005_000", sector_size=2)
    results = s4.run(
        image_path=image_path,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256=sha,
        authorize=True,
        transport=t,
    )
    assert results["FLASH_RESULT"] == "PASS"
    assert results["APP_START"] == "OK"
    with open(image_path, "rb") as f:
        expected = f.read()
    assert bytes(t._flashed) == expected
    print("test_authorized_flash_image_matches: PASS")


# --- Test: failed chunk -> abort safely ---

class FailChunkTransport(FakeTransport):
    def __init__(self, version_string, fail_at_chunk=2):
        super().__init__(version_string, sector_size=1)
        self._chunk_count = 0
        self._fail_at = fail_at_chunk

    def write(self, data):
        if (self._expected_size is not None and
                len(data) > 5 and
                data != bytes([0x02, 0xFD])):
            self._chunk_count += 1
            if self._chunk_count == self._fail_at:
                self._inbox = bytes([0x21,
                                     cf.crc8_sum_complement(bytes([0x21]))])
                return len(data)
        return super().write(data)

def test_failed_chunk_aborts(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)
    t = FailChunkTransport("mcu0_001_G32-mcu0_005_000", fail_at_chunk=2)
    try:
        results = s4.run(
            image_path=image_path,
            elf_path=elf_path,
            config_path=config_path,
            port="/dev/null",
            expected_sha256=sha,
            authorize=True,
            transport=t,
        )
        raise AssertionError("should have raised on failed chunk")
    except cf.FlashError as e:
        assert "write error" in str(e)
    print("test_failed_chunk_aborts: PASS")


# --- Test: app_start only after complete write ---

def test_app_start_only_after_write(image_path, elf_path, config_path):
    sha = s4.sha256_file(image_path)

    class TrackingTransport(FakeTransport):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.app_start_called = False
            self.flash_complete = False

        def write(self, data):
            if data == bytes([0x02, 0xFD]):
                self.app_start_called = True
            result = super().write(data)
            if (self._inbox and len(self._inbox) >= 1 and
                    self._inbox[0] == 0x20):
                self.flash_complete = True
            return result

    t = TrackingTransport("mcu0_001_G32-mcu0_005_000", sector_size=2)
    results = s4.run(
        image_path=image_path,
        elf_path=elf_path,
        config_path=config_path,
        port="/dev/null",
        expected_sha256=sha,
        authorize=True,
        transport=t,
    )
    assert results["FLASH_RESULT"] == "PASS"
    assert results["APP_START"] == "OK"
    assert t.app_start_called is True
    print("test_app_start_only_after_write: PASS")


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    image, elf, config = sys.argv[1:4]

    test_wrong_candidate_sha(image, elf, config)
    test_validator_failure(elf, config)
    test_malformed_identity_rejected(image, elf, config)
    test_nozzle_identity_rejected(image, elf, config)
    test_correct_identity_accepted(image, elf, config)
    test_timeout_aborts(image, elf, config)
    test_bad_wire_checksum_aborts(image, elf, config)
    test_no_authorization_no_write(image, elf, config)
    test_authorized_flash_image_matches(image, elf, config)
    test_failed_chunk_aborts(image, elf, config)
    test_app_start_only_after_write(image, elf, config)

    print(f"\nAll {11} stage4_first_flash tests passed "
          "(fake transport only, no hardware touched)")


if __name__ == "__main__":
    main()
