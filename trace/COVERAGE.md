| System | Traced / in catalog | Palette verified | ram-only | traced | located | derived | none | errors | Graphics direct | derived | none |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gb | 139 / 139 | 138 | 0 | 1 | 0 | 0 | 0 | 0 | 128 | 11 | 0 |
| gbc | 95 / 95 | 94 | 0 | 0 | 0 | 0 | 1 | 0 | 78 | 16 | 1 |
| genesis | 140 / 140 | 139 | 0 | 0 | 0 | 0 | 1 | 0 | 78 | 62 | 0 |
| nes | 229 / 229 | 229 | 0 | 0 | 0 | 0 | 0 | 0 | 215 | 14 | 0 |
| sms | 49 / 49 | 49 | 0 | 0 | 0 | 0 | 0 | 0 | 46 | 3 | 0 |
| snes | 290 / 290 | 290 | 0 | 0 | 0 | 0 | 0 | 0 | 262 | 28 | 0 |
| all | 942 / 942 | 939 | 0 | 1 | 0 | 0 | 2 | 0 | 807 | 134 | 1 |

## How the verified edits were found

| System | traced | other scene | plain copy | code number | measured | needed the second input script | needed a scene between the main ones |
|---|---|---|---|---|---|---|---|
| gb | 134 | 1 | 1 | 1 | 1 | 1 | 2 |
| gbc | 90 | 0 | 4 | 0 | 0 | 0 | 1 |
| genesis | 132 | 0 | 7 | 0 | 0 | 0 | 5 |
| nes | 229 | 0 | 0 | 0 | 0 | 0 | 0 |
| sms | 49 | 0 | 0 | 0 | 0 | 0 | 1 |
| snes | 286 | 0 | 4 | 0 | 0 | 1 | 0 |
| all | 920 | 1 | 16 | 1 | 1 | 2 | 9 |

## gb: 1 not verified

By cause: inexact source 1

| ROM | Palette | Cause |
|---|---|---|
| Wario Blast Featuring Bomberman! (USA, Europe) (SGB Enhanced) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source). Looked at by hand: one table byte is the final value of all three shade registers, and the program also compares the palette with that same number in six places to end its fades, so changing the table byte alone changes how the game runs. An edit would have to change those compares too. |

## gbc: 1 not verified

By cause: not available 1

| ROM | Palette | Cause |
|---|---|---|
| Kirby - Tilt 'n' Tumble (USA) | none | not available: this cartridge needs a tracing engine that is not included in the packages |

## genesis: 1 not verified

By cause: no picture 1

| ROM | Palette | Cause |
|---|---|---|
| QuackShot Starring Donald Duck (World) (En,Ja) (Rev A) | none | no picture: the game never left a blank or static screen with either input script (it may not run in this engine). Looked at by hand: the game never writes video memory in this engine with this dump, so there is nothing to trace or replay. |

## SNES coprocessor cartridges

| Chip | Hooks cover | ROMs | Palette verified |
|---|---|---|---|
| Cx4 | main CPU only | 2 | 2 |
| DSP | everything | 3 | 3 |
| OBC1 | everything | 1 | 1 |
| S-DD1 | main CPU only | 1 | 1 |
| SA-1 | main CPU only | 4 | 4 |
| SuperFX | main CPU only | 3 | 3 |

- Cx4: Mega Man X2 (USA) (verified); Mega Man X3 (USA) (verified)
- S-DD1: Street Fighter Alpha 2 (USA) (verified)
- SA-1: Jikkyou Oshaberi Parodius (Japan) (verified); Kirby Super Star (USA) (verified); Kirby's Dream Land 3 (USA) (verified); Super Mario RPG - Legend of the Seven Stars (USA) (verified)
- SuperFX: Star Fox (USA) (Rev 2) (verified); Stunt Race FX (USA) (Rev 1) (verified); Super Mario World 2 - Yoshi's Island (USA) (Rev 1) (verified)

<!-- graphics coverage: begin (written by trace/graphics_report.py; do not edit by hand) -->

## Graphics: what a replay confirmed

From `trace/graphics_sweep.py` (one result per ROM; totals by `trace/graphics_report.py`). Every count is an edit that was made in the ROM, replayed in the real engine from a checkpoint of the same run, and found in video memory exactly as planned, compared with the unedited run. Header checksums are repaired first (`graphics_trace.fix_checksums`). Nothing else is counted.

- **any tile path**: one picture (8x8 tile) on screen was redrawn by some path: in place, re-packed, or the run-time patch.
- **tile in place**: the tile is ROM bytes and was written where it is.
- **background cell**: one cell of a background map was made to show another tile (see below for how).
- **hard tile re-packed**: the one tile picked as hardest to write in place (computed by the game, most used on screen) was changed by unpacking, editing and packing its data again in the same place.
- **packed block re-packed**: one packed block of the ROM was recognised, unpacked, edited, packed again (in place, or moved with its pointer) and replayed. The tiles tried are picked as `trace/codec_survey.py` picks them: tiles with a picture first, tiles made of stream literals as well as computed ones, in every sampled scene. Counted only when the tile came out as planned, nothing else in the block changed, what follows a bare stream still unpacks as before, and no unrelated byte of video memory changed (a whole second copy of the same edit elsewhere is related, and is counted below).
- **run-time patch**: the fallback routine on the vertical-blank interrupt swapped the tile in; **clean from power-on** when the whole run from power-on then differs only as planned.
- **only this scene**: a private copy of shared tile data, with the one reference moved.

| System | ROMs | traced | any tile path | tile in place | background cell | hard tile re-packed | packed block re-packed | run-time patch | patch clean from power-on | only this scene tried | only this scene |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gb | 139 | 139 | 139 | 126 | 137 | 9 | 29 | 106 | 88 | 87 | 17 |
| gbc | 94 | 94 | 94 | 88 | 94 | 9 | 21 | 76 | 62 | 59 | 15 |
| genesis | 140 | 140 | 138 | 107 | 129 | 4 | 35 | 127 | 89 | 58 | 17 |
| nes | 229 | 229 | 228 | 228 | 227 | 3 | 12 | 18 | 16 | 37 | 1 |
| sms | 49 | 49 | 49 | 43 | 49 | 6 | 21 | 35 | 22 | 12 | 3 |
| snes | 290 | 290 | 288 | 206 | 286 | 42 | 77 | 270 | 222 | 89 | 17 |
| all | 941 | 941 | 936 | 798 | 922 | 73 | 195 | 632 | 499 | 342 | 70 |

### Packed blocks

A block that turns out to be stored as it is (no packing) is a plain write and is counted apart.

| System | block recognised | re-packed, confirmed | of those: moved | of those: a second copy changed too | stored as it is, confirmed | as planned, but unrelated bytes changed | as planned, but the block was not left sound |
|---|---|---|---|---|---|---|---|
| gb | 50 | 29 | 1 | 2 | 13 | 0 | 2 |
| gbc | 42 | 21 | 2 | 1 | 10 | 2 | 2 |
| genesis | 77 | 35 | 19 | 0 | 29 | 4 | 4 |
| nes | 18 | 12 | 0 | 0 | 5 | 0 | 0 |
| sms | 26 | 21 | 1 | 2 | 0 | 1 | 0 |
| snes | 139 | 77 | 4 | 5 | 33 | 10 | 8 |
| all | 352 | 195 | 27 | 10 | 90 | 17 | 16 |

Confirmed re-packs by codec: konami-snes 17, nemesis 16, rnc2 16, hal 15, rle-sega-planes 14, rnc1 14, raw|0Z 12, lzss-00-raw 8, lz~le16.l1.L4lle.b0.m3.s 8, rle-konami 7, kosinski 6, raw|2of4 6, lz-ring256 5, lz5 5, lz~le16.l1.oku.b0.m3.s 4, raw|012Z 4, lzss-20-raw 3, raw|3bpp 3, rle-escape 3, raw|00 2, raw|1of2n 2, raw|1x2n 2, raw|F0 2, raw|Z0 2, rle~l.r0.l0.n.p1 2, rle~l.r0.l0.z.p1 2, lz-konami-md 1, lz2 1, lz2-le 1, lz2|0Z 1, lz3 1, lzss-00-le16 1, packbits 1, raw|01ZZ 1, raw|0ZZZ 1, raw|1of2n-b 1, rle~h.r0.l0.n.p1 1, rle~h.r0.l0.z.p4 1, rle~l.r0.l0.z.p2 1, rnc2|0Z 1, saxman 1.

### Background cells

The edit is the smallest there is: one cell, tile number plus one. Every layer of the scene is looked at, and when the scene chosen for the tile edit has no cell that can be changed, the other sampled scenes of the same run are (frames 450, 900, 1350 and 1800 of the scripted play).

- **in place**: the cell's tile number is a ROM byte (or a value in code) and was written there.
- **re-packed**: the map is packed in the ROM with a codec ROMancer knows.
- **stored piece**: the game builds the cell from a block definition, a table it adds a base to, or a literal inside packed data. The ROM bytes at and around the traced source were tried one at a time; the place counts only when the cell then held exactly the planned value and nothing outside the background maps changed. Every other cell built from the same piece changes with it (the "other cells" column counts the ROMs where that happened, by any path).
- **on a blank tile**: of the confirmed edits, those made on a cell that shows a tile of one flat color, because no sampled scene had a stored cell with a picture in it (a cleared screen). They are counted in "confirmed" and "in place".
- **also from power-on**: of the confirmed edits, those where the whole recorded run, replayed from power-on with the edited ROM, also ends with the cell as planned. A separate fact from "confirmed" (which is the replay from a checkpoint before the scene), except for a stored piece: because that place is found by trying, it is counted only when it holds from power-on too with nothing outside the background maps changed.

| System | traced | confirmed | in place | re-packed | moved and re-packed | stored piece | in another scene than the tile edit | other cells change too | on a blank tile | also from power-on | not confirmed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gb | 139 | 137 | 130 | 0 | 0 | 7 | 12 | 68 | 1 | 137 | 2 |
| gbc | 94 | 94 | 94 | 0 | 0 | 0 | 4 | 38 | 1 | 94 | 0 |
| genesis | 140 | 129 | 108 | 0 | 0 | 21 | 40 | 67 | 2 | 119 | 11 |
| nes | 229 | 227 | 227 | 0 | 0 | 0 | 4 | 140 | 0 | 227 | 2 |
| sms | 49 | 49 | 48 | 0 | 0 | 1 | 4 | 13 | 0 | 49 | 0 |
| snes | 290 | 286 | 278 | 0 | 0 | 8 | 39 | 154 | 0 | 285 | 4 |
| all | 941 | 922 | 885 | 0 | 0 | 37 | 103 | 480 | 4 | 911 | 19 |

Background cells confirmed in the v1.1.0 results (938 ROMs swept, first layer of one scene, in place only): gb 121, gbc 83, genesis 75, nes 190, sms 42, snes 169 (all 680).

### Background cell not confirmed (19)

- **no effect** (10: gb 1, genesis 4, nes 2, snes 3): cells trace to ROM bytes or code values, but the replay with those bytes changed did not show the planned cell (drawn before the first checkpoint that replays, a coincidence of values, or code that is shared), and the computed cells could not be changed either.
- **computed** (4: genesis 4): every pictured cell is computed by the game (unpacked or built at run time); no packed form ROMancer knows and no stored piece near the traced source gave the planned cell.
- **not from power-on** (3: gb 1, genesis 2): a ROM byte near the traced source gives the planned cell when the scene is replayed from shortly before it, but not when the run is replayed from power-on (the byte is used for more than this background), and no other cell was confirmed.
- **nothing drawn** (1: genesis 1): no sampled scene has a background cell that shows a picture and was written while tracing (blank or untouched maps).
- **no layer** (1: snes 1): no background layer is drawn in any sampled scene (or the registers that place the layers were not captured).

| System | ROM | Cause |
|---|---|---|
| gb | Tetris Blast (USA, Europe) (SGB Enhanced) | no effect (8 stored and 6 computed cells tried in 4 scenes) |
| gb | Mega Man IV (USA) | not from power-on (8 stored and 16 computed cells tried in 4 scenes) |
| genesis | Landstalker (USA) | computed (0 stored and 8 computed cells tried in 4 scenes) |
| genesis | Red Zone (USA, Europe) | computed (0 stored and 14 computed cells tried in 4 scenes) |
| genesis | Rings of Power (USA, Europe) | computed (0 stored and 12 computed cells tried in 4 scenes) |
| genesis | Sonic The Hedgehog (USA, Europe) | computed (0 stored and 7 computed cells tried in 4 scenes) |
| genesis | James Pond - Underwater Agent (USA, Europe) | no effect (29 stored and 20 computed cells tried in 4 scenes) |
| genesis | James Pond II - Codename - Robocod (USA, Europe) | no effect (14 stored and 11 computed cells tried in 4 scenes) |
| genesis | Out of This World (USA) | no effect (6 stored and 4 computed cells tried in 4 scenes) |
| genesis | Sonic & Knuckles + Sonic The Hedgehog 3 (USA) (Lock-On) | no effect (1 stored and 7 computed cells tried in 4 scenes) |
| genesis | Desert Strike - Return to the Gulf (USA, Europe) | not from power-on (0 stored and 14 computed cells tried in 4 scenes) |
| genesis | Punisher, The (USA) | not from power-on (5 stored and 14 computed cells tried in 4 scenes) |
| genesis | QuackShot Starring Donald Duck (World) (En,Ja) (Rev A) | nothing drawn |
| nes | Batman - Return of the Joker (USA) | no effect (3 stored and 7 computed cells tried in 4 scenes) |
| nes | Pinball Quest (USA) | no effect (8 stored and 8 computed cells tried in 4 scenes) |
| snes | Ken Griffey Jr.'s Winning Run (USA) | no effect (16 stored and 4 computed cells tried in 3 scenes) |
| snes | Ultima - Runes of Virtue II (USA) | no effect (9 stored and 16 computed cells tried in 4 scenes) |
| snes | Ultimate Mortal Kombat 3 (USA) | no effect (15 stored and 8 computed cells tried in 3 scenes) |
| snes | Soldiers of Fortune (USA) | no layer |

### Not available (1)

Swept with a tracing engine that is not shipped, so not counted anywhere above.

| System | ROM | Engine |
|---|---|---|
| gbc | Kirby - Tilt 'n' Tumble (USA) | mgba_gbc_trace_libretro.dll |

<!-- graphics coverage: end -->

## PNG out and back in

Measured with `trace/png_sweep.py` on 942 of the 942 catalog ROMs. For each ROM, scenes were recorded, the scene with the most pictures on screen was saved as PNG (the pictures and every background layer), each PNG was read straight back, then up to 6 pictures on screen were drawn on in the pictures PNG and it was loaded. A picture counts as confirmed only when a replay of the real game shows it as drawn.

| What | ROMs |
|---|---|
| Scenes recorded | 939 of 942 |
| Pictures saved as PNG | 939 |
| ... as a palette PNG with the colors of the scene | 939 |
| ... read straight back with nothing reported as changed (as saved, and converted to plain RGB) | 939 |
| At least one background layer saved as PNG | 939 |
| ... every saved layer read straight back unchanged | 939 |
| Loaded an edited pictures PNG | 939 |
| ... at least one drawn picture confirmed by replay | 897 |
| ... every drawn picture confirmed | 769 |
| ... and the change also holds when the game is played from power-on | 854 |
| Loaded an edited background PNG | 902 |
| ... at least one drawn picture confirmed | 800 |

Pictures drawn on across all ROMs: 5,315; confirmed: 4,729.

| System | Loaded | Some confirmed | All confirmed |
|---|---|---|---|
| NES | 229 | 209 | 194 |
| Super NES | 289 | 281 | 256 |
| Mega Drive | 139 | 133 | 113 |
| Master System | 49 | 49 | 42 |
| Game Boy | 139 | 135 | 99 |
| Game Boy Color | 94 | 90 | 65 |

How the confirmed pictures were changed: written in place 2,018, swapped in by a patch 1,653, written in place inside packed data 565, packed again 427, packed again and moved 66.

### No drawn picture confirmed: 42

| ROM | System | Why |
|---|---|---|
| Donkey Kong Land (USA, Europe) (SGB Enhanced) | gb | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: Two bytes of this tile come from one ROM byte a |
| Monster Max (Europe) (En,Fr,De,Es,It,Nl) | gb | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. ROM b |
| Parodius (Europe) | gb | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: A ROM byte behind this tile also feeds a byte t |
| Pop'n TwinBee (Europe) | gb | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
|  - Dark Duel Stories (USA) | gbc | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Croc 2 (USA, Europe) | gbc | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: A ROM byte behind this tile also feeds a byte t |
| Harry Potter and the Sorcerer's Stone (USA, Europe) (En,Fr,De,Es,It,Nl,Pt,Sv,No,Da,Fi) | gbc | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Metal Gear Solid (USA) | gbc | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Elemental Master (USA) | genesis | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: A ROM byte behind this tile also feeds a byte t |
| Flicky (USA, Europe) | genesis | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| James Pond - Underwater Agent (USA, Europe) | genesis | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| James Pond 3 (USA, Europe) | genesis | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| James Pond II - Codename - Robocod (USA, Europe) | genesis | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Red Zone (USA, Europe) | genesis | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Alfred Chicken (USA) | nes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. The p |
| Batman Returns (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Donkey Kong Classics (USA, Europe) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Double Dragon III - The Sacred Stones (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Dragon Fighter (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Dragon Warrior (USA) (Rev 1) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Flintstones, The - The Rescue of Dino & Hoppy (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Gemfire (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Jetsons, The - Cogswell's Caper (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| KickMaster (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Kirby's Adventure (USA) (Rev 1) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Krion Conquest, The (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Mafat Conspiracy, The (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Monster in My Pocket (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| StarTropics (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Tecmo Super Bowl (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Town & Country Surf Designs - Thrilla's Surfari (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Ufouria - The Saga (Europe) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Whomp 'Em (USA) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Wrath of the Black Manta (USA) (Rev 1) | nes | ROMancer wrote this picture into the ROM, but replaying the game did not show a change in this scene, so it was left out. |
| Cybernator (USA) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Fatal Fury Special (USA) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Out of This World (USA) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Pilotwings (USA) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: A ROM byte behind this tile also feeds a byte t |
| Soul Blazer (USA) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: The overlay edits whole tiles stored as consecu |
| Stunt Race FX (USA) (Rev 1) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |
| Super Mario World 2 - Yoshi's Island (USA) (Rev 1) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. The o |
| Ultimate Mortal Kombat 3 (USA) | snes | ROMancer could not find a way to change this picture that the real game confirmed, so nothing is changed. It is unpacked or drawn by the game while it runs. What was tried: no known packing reproduces this picture. the p |

### Not measured: 3

| ROM | Why |
|---|---|
| QuackShot Starring Donald Duck (World) (Rev A) | no scene was recorded |
| Top Gear 3000 (USA) | ValueError: This scene holds no pictures to save. |
| Kirby - Tilt 'n' Tumble (USA) | no scene was recorded |

## Level maps

Measured with `trace/level_blocks.py` on 42 well-known games. For each one the game played by itself (the menu presses of Record more scenes, then walking right and jumping) while a level was recorded, the map was put together, and one whole block of the level was painted onto a place that showed another block, through the level map. A change counts only when a replay of the real game from the start of the recording showed the painted block in video memory and the painted places then looked different on the map. The play is automatic, so a game whose menus it does not get through, or that needs more than walking right, is measured on whatever screen it reached.

| What | Games |
|---|---|
| A level map was put together | 39 of 42 |
| The level is built from blocks that are copied from a table in the ROM | 21 |
| A block was changed in the level's own list of blocks, confirmed by replay | 16 |
| Otherwise the block itself was changed (every place that uses it), confirmed by replay | 3 |

Places that looked different afterwards are counted over the whole map. A count equal to the size of the block means only that place changed. A larger count means the game uses the changed entry in more places, or that the change sent the automatic play another way (it walks into the new block), so later captures show other things.

| Game | System | Map (cells) | Blocks | Result | Places that looked different |
|---|---|---|---|---|---|
| Adventure Island (USA) | NES | 196 by 25 | 4 by 4 | In the level's own list of blocks | 151 |
| Alex Kidd in Miracle World (World) (Sega Ages) | Master System | 32 by 40 |  | Map only |  |
| Batman - The Video Game (USA) | NES | 125 by 29 | 4 by 2 | In the level's own list of blocks | 298 |
| Bionic Commando (USA) | NES | 116 by 28 |  | Map only |  |
| Blaster Master (USA) | NES | 180 by 29 | 2 by 2, in larger blocks of 4 by 4 | In the level's own list of blocks | 168 |
| Castlevania (USA) | NES | 204 by 23 | 4 by 4 | In the level's own list of blocks | 16 |
| Castlevania - The Adventure (USA | Game Boy | 92 by 18 |  | Map only |  |
| Castlevania II - Belmont's Revenge (USA, Europe | Game Boy |  |  | No map |  |
| Castlevania II - Simon's Quest (USA) | NES | 203 by 28 |  | Map only |  |
| Castlevania III - Dracula's Curse (USA) | NES | 104 by 90 | 4 by 4, in larger blocks of 8 by 8 | In the level's own list of blocks | 16 |
| Contra (USA) | NES | 270 by 27 | 4 by 4 | In the level's own list of blocks | 160 |
| Double Dragon (USA) | NES | 32 by 28 |  | Map only |  |
| DuckTales (USA | Game Boy | 84 by 14 | 2 by 2 | The block itself, everywhere it is used | 112 |
| DuckTales (USA) | NES | 196 by 24 | 2 by 2, in larger blocks of 4 by 4 | In the level's own list of blocks | 186 |
| Faxanadu (USA) (Rev 1) | NES | 112 by 10 | 2 by 2 | The block itself, everywhere it is used | 8 |
| Ghosts'n Goblins (USA) | NES | 246 by 23 | 2 by 2 | In the level's own list of blocks | 780 |
| Kid Icarus (USA, Europe) (Rev 1) | NES | 32 by 27 | 2 by 2 | In the level's own list of blocks | 24 |
| Kirby's Adventure (USA) (Rev 1) | NES | 31 by 28 | 2 by 2 | Blocks found, no change confirmed |  |
| Kirby's Dream Land (USA, Europe | Game Boy | 79 by 16 |  | Map only |  |
| Legend of Zelda, The (USA) (Rev 1) | NES | 32 by 28 |  | Map only |  |
| Legend of Zelda, The - Link's Awakening (USA, Europe) (Rev 2 | Game Boy | 20 by 18 | 2 by 2 | In the level's own list of blocks | 4 |
| Mega Man (USA) | NES | 35 by 17 |  | Map only |  |
| Mega Man - Dr. Wily's Revenge (USA | Game Boy | 20 by 18 |  | Map only |  |
| Mega Man 2 (USA) | NES | 104 by 28 |  | Map only |  |
| Mega Man 3 (USA) | NES | 81 by 28 | 2 by 2, in larger blocks of 4 by 4 | In the level's own list of blocks | 4 |
| Mega Man X (USA) (Rev 1) | Super NES | 348 by 28 |  | Map only |  |
| Metroid (USA) | NES | 145 by 20 | 2 by 2 | In the level's own list of blocks | 24 |
| Metroid II - Return of Samus (World | Game Boy | 88 by 19 | 2 by 2 | In the level's own list of blocks | 4 |
| Ninja Gaiden (USA) | NES | 139 by 23 | 2 by 2, in larger blocks of 4 by 4 | In the level's own list of blocks | 128 |
| Sonic The Hedgehog (USA, Europe | Mega Drive | 750 by 92 |  | Map only |  |
| Sonic The Hedgehog (USA, Europe, Brazil) | Master System | 32 by 28 | 4 by 4 | In the level's own list of blocks | 12 |
| Sonic The Hedgehog 2 (World) (Rev B | Mega Drive | 494 by 63 |  | Map only |  |
| Super Castlevania IV (USA) | Super NES | 101 by 24 |  | Map only |  |
| Super Mario Bros. (World) | NES | 126 by 12 | 2 by 2 | Blocks found, no change confirmed |  |
| Super Mario Bros. 2 (USA) (Rev 1) | NES | 74 by 64 | 2 by 2, in larger blocks of 4 by 4 | The block itself, everywhere it is used | 34 |
| Super Mario Bros. 3 (USA) (Rev 1) | NES | 788 by 27 | 2 by 2 | In the level's own list of blocks | 57 |
| Super Mario Land (World) (Rev 1 | Game Boy | 88 by 16 |  | Map only |  |
| Super Mario World (USA) | Super NES | 172 by 54 |  | Map only |  |
| Super Metroid (Japan, USA) (En,Ja) | Super NES | 140 by 28 |  | Map only |  |
| Wonder Boy (USA, Europe, Brazil) (Rev 1) | Master System |  |  | No map |  |
| Wonder Boy III - The Dragon's Trap (USA, Europe) | Master System | 112 by 28 |  | Map only |  |
| Zelda II - The Adventure of Link (USA) | NES |  |  | No map |  |
