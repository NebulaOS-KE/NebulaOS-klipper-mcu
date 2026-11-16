# Community mainboard firmwares

> **Community boards are not supported by NebulaOS.** They're built from published, working
> recipes so you can try them easily. There is no guarantee and no support. If you get one
> working, or find something wrong in a recipe, tell us so everyone else gets the fix.

Each `community/<board>/<chip>.defconfig` is one recipe: the Klipper build settings for one
mainboard chip. `scripts/build-community.sh` builds every recipe from the official Klipper in
`upstream.lock` - plain upstream, no patch (these boards keep their own SD-card bootloader) -
twice, checks both builds are byte-identical and that the image starts where the recipe's
`# expect:` line says, and writes the `.bin`, the full `klipper.config`, `SHA256SUMS` and
`build-info.txt`. CI: `.github/workflows/build-community.yml` (manual, on a release, and on a
pull request that changes a recipe).

The firmwares users download are built by **every NebulaOS release**: its release build runs this
script with `KLIPPER_SHA=` the Klipper that release runs, and attaches the `.bin` files to the
release. A new recipe here is in the next NebulaOS release automatically.

| Recipe | Chip | Boards | Bootloader | Status |
|---|---|---|---|---|
| `ender-3-v3-se/gd32f303` | GigaDevice GD32F303 | Ender-3 V3 SE: every C13, some C14 | 28 KiB | community proven |
| `ender-3-v3-se/stm32f401` | ST STM32F401 | Ender-3 V3 SE: some C14 | 64 KiB | untested with NebulaOS |

How to install one, the printer configuration and the test steps:
[NebulaOS `community/ender-3-v3-se`](https://github.com/NebulaOS-KE/NebulaOS/tree/main/community/ender-3-v3-se).

The Ender-3 V3 KE firmware is not here: it is this repository's main build (`scripts/ci.sh`).
