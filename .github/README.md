# ROMancer v1.1.1

**[Download for Windows x64](https://github.com/RetchERez/ROMancer/releases/download/v1.1.1/ROMancer-v1.1.1-Windows.zip)** · **[Download for Linux x86-64](https://github.com/RetchERez/ROMancer/releases/download/v1.1.1/ROMancer-v1.1.1-Linux-x86_64.tar.gz)**

By **RetchEWretched**. Edit ROMs, preview changes, playtest builds, and export patches offline.

## New in v1.1

- **Scenes & colors editor.** Record moments of the game, change a color, and the **Also changes** strip replays every recorded scene that uses the same data in the real engine, so you see what else changes before you save. Works on all six systems without a game-specific definition.
- **Tile and background editing.** In the same editor, redraw a picture pixel by pixel or paint pictures into background cells. Packed graphics are re-packed when ROMancer recognises the packing; otherwise the build gets a small run-time patch, shown both in the scene and from power-on.
- **Accurate catalog.** The catalog now lists 942 cartridge dumps that match the No-Intro reference lists exactly, under their No-Intro names. Fan translations, re-release dumps and entries that did not boot were removed.

Measured across the catalog (938 of 942 entries have a result): a color edit was confirmed by replay on 906 ROMs and a picture edit on 916. Per-ROM results are in [trace/COVERAGE.md](../trace/COVERAGE.md); limits are in the [release notes](https://github.com/RetchERez/ROMancer/releases/tag/v1.1.1).

## Get started on Windows

1. In File Explorer, right-click **ROMancer-v1.1.1-Windows.zip** and choose **Extract All**.
2. Pick a destination and click **Extract**. Open the extracted folder.
3. Double-click **ROMancer.exe**. Keep it next to the **ROMancer Files** folder.

The ZIP includes the runtime, emulator engines, tracing engines for Scenes & colors, and offline user guide. Try an included practice ROM or choose **New project** to import your own. Open **Help → User guide** for a walkthrough. The launcher is unsigned, so Windows may show a SmartScreen warning.

[User guide (PDF)](https://github.com/RetchERez/ROMancer/releases/download/v1.1.1/ROMancer-v1.1.1-User-Guide.pdf) · [All 942 ROM revisions](../knowledge/ROM-CATALOG.md) · [Tested games](https://github.com/RetchERez/ROMancer/releases/download/v1.1.1/TESTED-GAMES.txt) · [Release and checksums](https://github.com/RetchERez/ROMancer/releases/tag/v1.1.1)

## Get started on Linux

```
tar xf ROMancer-v1.1.1-Linux-x86_64.tar.gz
./ROMancer-v1.1.1-Linux-x86_64/ROMancer.sh
```

Python, the emulator engines and the tracing engines are included; nothing is installed system-wide. Needs glibc 2.28 or newer (Ubuntu 20.04+, Debian 10+, Fedora 29+, SteamOS 3) and a web browser. Run `./ROMancer.sh --install-desktop` to add a menu entry. Native debugger captures are Windows-only.

## Editors in action

### Mega Drive palette editor

Change palette colors and replay the same scene to see their effect. In **Sonic the Hedgehog**, six palette edits turn Green Hill Zone’s grass and palms purple and pink. The saved build reproduced the editor’s gameplay preview pixel for pixel.

![ROMancer comparing the original and recolored Green Hill Zone, with palette swatches and a gameplay difference view](screenshots/sonic-green-hill-palette.png)

### Graphics & fonts

Assemble tiles and paint the full sprite. Here, Rastan’s first humanoid enemy is being redrawn as a single blob alongside the original.

![ROMancer sprite editor showing the original Rastan enemy beside the edited blob](../user-guide/screenshots/51-rastan-enemy-editor.png)

### Text & layout

Edit dialogue, see how many bytes it needs, and preview a move to reserved space for longer text.

![ROMancer text editor comparing a short greeting with longer dialogue and previewing the text move](../user-guide/screenshots/241-longer-dialogue-pointer-preview.png)

### Hex editor

Select a byte and see its ASCII character. Staged edits are underlined and can be reviewed before creating a separate build.

![ROMancer hex editor showing one staged byte, its ASCII preview, and the review controls](../user-guide/screenshots/266-hex-selection-and-staged-edit.png)

### Playtest and save states

Play your ROM or a saved build, capture scenes, and resume from a save state. Here, **Top Gear 3000** has been restored mid-race in the built-in SNES playtest.

![ROMancer Playtest showing a restored Top Gear 3000 race with the save-state controls visible](screenshots/top-gear-3000-playtest.png)

## Supported systems

NES, SNES, Genesis / Mega Drive, Master System, Game Boy, and Game Boy Color. The [full ROM catalog](../knowledge/ROM-CATALOG.md) lists every recognized revision with CRC32 and SHA-256. Open **ROM Catalog.html** from the extracted ZIP to search and filter offline. All 942 cataloged revisions passed the byte-edit, undo/redo, build, and BPS workflow. Structured editors use checked definitions for the selected revision. The tested games list shows the game-specific edits and playtest routes verified. Visual level editing is coming soon.

[Build and technical documentation](../README.txt) · [MIT license](../LICENSE)
