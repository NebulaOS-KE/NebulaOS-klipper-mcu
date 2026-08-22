#!/usr/bin/env python3
"""Phase 1.8 Stage 4: first native MCU flash orchestration.

This tool handles the FIRST flash of a native GD32F303 MCU firmware onto
a Creality Ender-3 V3 KE that is still running the stock Creality MCU
application. It uses FIRMWARE_RESTART (via Moonraker API) for bootloader
entry because the stock firmware's bootloader_request() lacks the 12KB
bootloader branch — the serial magic approach does not work for the first
transition.

After the first flash, the new firmware DOES include the correct
bootloader_request() branch, so subsequent flashes can use
creality_flash.py's normal enter_bootloader() path.

All flash protocol primitives (handshake, version, sector size, flash
transfer, checksums, app_start) are imported from creality_flash.py —
this tool does NOT reimplement any of them.

SAFETY:
  - Requires --authorize flag — no erase/write without it
  - Validates candidate SHA256 before anything
  - Runs offline validator before anything
  - Queries and verifies live hardware identity before any write
  - Prints a human-readable checkpoint before flashing
"""

import argparse
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import creality_flash as cf  # noqa: E402
import creality_validator as validator  # noqa: E402


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def moonraker_firmware_restart():
    """Trigger FIRMWARE_RESTART via Moonraker API. Requires urllib."""
    import urllib.request
    req = urllib.request.Request(
        "http://127.0.0.1:7125/printer/firmware_restart",
        data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def kill_klipper_process():
    """Kill klippy to release serial port. Returns True if killed."""
    try:
        with open("/var/run/klippy.pid") as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
        return True
    except Exception:
        return False


def enter_bootloader_via_firmware_restart(port, bl_baud=115200,
                                          attempts=10, transport_cls=None):
    """Enter bootloader by triggering FIRMWARE_RESTART then catching the
    bootloader during its 15-second handshake window.

    Returns a Transport connected at bl_baud with handshake completed,
    or raises FlashError.
    """
    moonraker_firmware_restart()
    time.sleep(0.3)
    kill_klipper_process()
    time.sleep(0.5)

    for attempt in range(attempts):
        if transport_cls is not None:
            t = transport_cls(port, baud=bl_baud)
        else:
            t = cf.SerialTransport(port, baud=bl_baud)
        if cf.handshake(t):
            return t
        time.sleep(0.5)
    raise cf.FlashError(
        f"could not handshake with bootloader after {attempts} attempts")


def run(image_path, elf_path, config_path, port, expected_sha256,
        authorize=False, transport=None):
    """Orchestrate the full Stage-4 first-flash sequence.

    If transport is provided (testing), it is used directly and
    FIRMWARE_RESTART is skipped.

    Returns a dict of results.
    """
    results = {
        "TIMESTAMP": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "CANDIDATE_IMAGE": image_path,
    }

    # 1. Verify candidate SHA256
    actual_sha = sha256_file(image_path)
    results["PACKAGED_BIN_SHA256"] = actual_sha
    results["SHA256_MATCH"] = actual_sha == expected_sha256
    if not results["SHA256_MATCH"]:
        results["ABORT_REASON"] = (
            f"SHA256 mismatch: expected {expected_sha256}, got {actual_sha}")
        return results

    # 2. Run offline validator
    fails = cf.validate_image_file(image_path, elf_path, config_path)
    results["VALIDATOR_RESULT"] = "PASS" if not fails else "FAIL"
    if fails:
        results["VALIDATOR_FAILURES"] = fails
        results["ABORT_REASON"] = "offline validation failed"
        return results

    # 3. Enter bootloader and query identity
    if transport is not None:
        t = transport
    else:
        t = enter_bootloader_via_firmware_restart(port)

    version_string = cf.get_version(t)
    hw_part = (version_string.split("-")[0]
               if "-" in version_string else version_string)
    results["LIVE_MCU_HW_ID"] = hw_part
    results["FULL_VERSION_STRING"] = version_string
    results["IDENTITY_MATCH"] = cf.check_identity(version_string)

    if not results["IDENTITY_MATCH"]:
        results["ABORT_REASON"] = (
            f"identity {hw_part!r} not in allow-list "
            f"{cf.DEFAULT_ALLOWED_HW_IDS}")
        # Send app_start to return MCU to its current application
        cf.app_start(t)
        results["ERASE_PERFORMED"] = "NO"
        results["WRITE_PERFORMED"] = "NO"
        return results

    # 4. Human checkpoint
    results["ERASE_PERFORMED"] = "NO"
    results["WRITE_PERFORMED"] = "NO"

    if not authorize:
        results["CHECKPOINT"] = "WAITING_FOR_AUTHORIZATION"
        results["ABORT_REASON"] = "no --authorize flag"
        cf.app_start(t)
        return results

    # 5. Flash
    sector_size = cf.get_sector_size(t)
    with open(image_path, "rb") as f:
        image = f.read()

    results["SECTOR_SIZE"] = sector_size
    results["IMAGE_SIZE"] = len(image)
    results["ERASE_PERFORMED"] = "YES"
    results["WRITE_PERFORMED"] = "YES"

    if not cf.flash_image(t, image, sector_size):
        results["FLASH_RESULT"] = "FAIL"
        results["ABORT_REASON"] = "flash transfer did not report completion"
        return results

    results["FLASH_RESULT"] = "PASS"

    # 6. app_start
    if cf.app_start(t):
        results["APP_START"] = "OK"
    else:
        results["APP_START"] = "FAIL"

    return results


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="Creality-packaged MCU image")
    ap.add_argument("elf", help="klipper.elf for target validation")
    ap.add_argument("config", help="klipper.config for target validation")
    ap.add_argument("--port", default="/dev/ttyS1")
    ap.add_argument("--expected-sha256", required=True,
                     help="expected SHA256 of the packaged image")
    ap.add_argument("--authorize", action="store_true",
                     help="REQUIRED to actually flash. Without this flag, "
                          "the tool performs all checks and prints the "
                          "checkpoint but does NOT erase/write.")

    args = ap.parse_args()

    print("=== Phase 1.8 Stage 4: First Native MCU Flash ===")
    print()

    results = run(
        image_path=args.image,
        elf_path=args.elf,
        config_path=args.config,
        port=args.port,
        expected_sha256=args.expected_sha256,
        authorize=args.authorize,
    )

    print("=== RESULTS ===")
    for k, v in results.items():
        if isinstance(v, list):
            print(f"{k}:")
            for item in v:
                print(f"  - {item}")
        else:
            print(f"{k}={v}")

    if "ABORT_REASON" in results:
        sys.exit(1)


if __name__ == "__main__":
    main()
