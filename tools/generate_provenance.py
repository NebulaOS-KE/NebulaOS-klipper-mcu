#!/usr/bin/env python3
"""Generate the Phase 1.7 provenance manifest for a built MCU candidate.

Captures exact source/tool/artifact identity so the candidate's origin can
be independently reproduced and checked - not a substitute for the 3-digit
Creality metadata version field (which cannot carry this much detail), but
its sidecar (Phase 1.7 mission, section 26).
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_files(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(Path(p).read_bytes())
    return h.hexdigest()


def run(cmd):
    return subprocess.check_output(cmd, text=True).strip()


def git(repo, *args):
    return run(["git", "-C", repo] + list(args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="NebulaOS-klipper-mcu checkout")
    ap.add_argument("--elf", required=True)
    ap.add_argument("--raw-bin", required=True)
    ap.add_argument("--packaged-bin", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--upstream-sha", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    patch_files = [
        "src/stm32/Kconfig", "src/stm32/Makefile", "src/stm32/stm32f1.c",
        "src/stm32/gd32_creality_metadata.c", "src/generic/armcm_link.lds.S",
        "src/Kconfig",
    ]

    manifest = {
        "mission": "NebulaOS Phase 1.7 - native GD32F303 MCU candidate",
        "upstream_repo": "https://github.com/Klipper3d/klipper.git",
        "upstream_sha": args.upstream_sha,
        "patch_commit": git(args.repo, "log", "-1", "--format=%H"),
        "patch_commit_subject": git(args.repo, "log", "-1", "--format=%s"),
        "patch_files": patch_files,
        "patch_series_sha256": sha256_files(str(Path(args.repo) / f) for f in patch_files),
        "build_config_sha256": sha256_file(args.config),
        "toolchain": {
            "gcc": run(["arm-none-eabi-gcc", "--version"]).splitlines()[0],
            "binutils_ld": run(["arm-none-eabi-ld", "--version"]).splitlines()[0],
            "python": sys.version.split()[0],
        },
        "artifacts": {
            "elf_sha256": sha256_file(args.elf),
            "raw_bin_sha256": sha256_file(args.raw_bin),
            "packaged_bin_sha256": sha256_file(args.packaged_bin),
            "raw_bin_size": Path(args.raw_bin).stat().st_size,
            "packaged_bin_size": Path(args.packaged_bin).stat().st_size,
        },
        "hardware_flash_performed": False,
        "offline_validated_only": True,
    }

    with open(args.output, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Wrote provenance manifest to {args.output}")


if __name__ == "__main__":
    main()
