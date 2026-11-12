# Toolchain

`scripts/install-toolchain.sh` downloads and SHA256-verifies a specific Arm GNU Toolchain release for
use in CI and by anyone reproducing the build exactly:

```
MCU_BUILD_ENVIRONMENT=ubuntu-latest GitHub Actions runner (workflow-managed) or any Linux x86_64 host
MCU_TOOLCHAIN_VERSION=Arm GNU Toolchain 15.2.Rel1 (gcc 15.2.1, binutils/ld 2.45.1)
MCU_TOOLCHAIN_PROVENANCE=https://developer.arm.com/-/media/Files/downloads/gnu/15.2.rel1/binrel/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi.tar.xz
MCU_TOOLCHAIN_SHA256=597893282ac8c6ab1a4073977f2362990184599643b4c5ee34870a8215783a16
```

This is not a byte-identical match to the toolchain used during the original Phase 1.7 proof session
(`arm-none-eabi-gcc (Fedora 15.2.0-4.fc44) 15.2.0` / `GNU ld (Fedora 2.45-3.fc44) 2.45`, the host's
system-installed Fedora package) — that exact distro build isn't practically reproducible on a generic
CI runner. What *is* pinned and enforced is the same **major.minor GCC series (15.2)** and the same
**major.minor binutils series (2.45)**, plus an exact, SHA256-verified upstream Arm release archive
rather than an unpinned `apt install`. Per Phase 1.7 Final Closure mission's stop conditions: never
silently change the toolchain's *major* version between local and CI builds; a minor patch-level
difference between a distro package and Arm's own upstream release build is disclosed here rather than
hidden.

Local builds outside CI may use any locally installed `arm-none-eabi-gcc`/`arm-none-eabi-ld` on
`PATH`, or explicitly opt into the pinned toolchain via:

```sh
TOOLCHAIN_BIN=$(./scripts/install-toolchain.sh) 
export TOOLCHAIN_BIN
./scripts/ci.sh
```
