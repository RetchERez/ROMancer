| System | Traced / in corpus | Palette verified | ram-only | traced | located | derived | none | errors | Graphics direct | derived | none |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gb | 149 / 149 | 142 | 2 | 2 | 2 | 1 | 0 | 0 | 136 | 13 | 0 |
| gbc | 101 / 101 | 96 | 3 | 1 | 0 | 1 | 0 | 0 | 83 | 18 | 0 |
| genesis | 0 / 150 | | | | | | | | | | |
| nes | 273 / 273 | 271 | 1 | 0 | 0 | 0 | 1 | 0 | 257 | 16 | 0 |
| sms | 0 / 50 | | | | | | | | | | |
| snes | 325 / 325 | 318 | 1 | 1 | 2 | 0 | 3 | 0 | 293 | 31 | 1 |

## gb: 7 not verified

By cause: computed 3, not on screen 2, inexact source 1, no effect 1

| ROM | Palette | Cause |
|---|---|---|
| Contra - The Alien Wars (USA) (SGB Enhanced).gb | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Legend of the River King GB (USA) (SGB Enhanced).gb | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Super Mario Land 2 - 6 Golden Coins (USA, Europe) (Rev 2).gb | derived | computed: palette is decompressed or generated and no nearby ROM byte moved it |
| Kirby's Dream Land (USA, Europe).gb | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Wario Blast Featuring Bomberman! (USA, Europe) (SGB Enhanced).gb | traced | no effect: editing the traced bytes did not change the color (data already copied before the first checkpoint, or a value coincidence) |
| DuckTales 2 (USA).gb | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |
| Monster Max (Europe) (En,Fr,De,Es,It,Nl).gb | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## gbc: 5 not verified

By cause: not on screen 3, inexact source 1, computed 1

| ROM | Palette | Cause |
|---|---|---|
| Mega Man Xtreme 2 (USA, Europe).gbc | derived | computed: palette is decompressed or generated and no nearby ROM byte moved it |
| Resident Evil Gaiden (USA).gbc | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Metal Gear Solid (USA).gbc | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |
| Shantae (USA).gbc | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |
| Wendy - Every Witch Way (USA, Europe).gbc | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## nes: 2 not verified

By cause: not on screen 1, no picture 1

| ROM | Palette | Cause |
|---|---|---|
| Kid Dracula (World) (Castlevania Anniversary Collection).nes | none | no picture: the game never left a blank or static screen with the scripted input |
| Mafat Conspiracy, The (USA).nes | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## snes: 7 not verified

By cause: coprocessor 3, not on screen 1, no effect 1, no picture 1, computed 1

| ROM | Palette | Cause |
|---|---|---|
| Urban Strike (USA).sfc | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Kirby's Dream Land 3 (USA).sfc | none | coprocessor: the SA-1 chip prepares these colors itself; only the main CPU is traced |
| Star Fox 2 (USA, Europe).sfc | located | coprocessor: the SuperFX chip prepares these colors itself; only the main CPU is traced |
| Super Mario World 2 - Yoshi's Island (USA) (Rev 1).sfc | none | coprocessor: the SuperFX chip prepares these colors itself; only the main CPU is traced |
| Flintstones, The - The Treasure of Sierra Madrock (USA).sfc | traced | no effect: editing the traced bytes did not change the color (data already copied before the first checkpoint, or a value coincidence) |
| Fire Emblem - Thracia 776 (Japan) [T-En by Cirosan v1.04] [Add by Miacis v1.08].sfc | none | no picture: the game never left a blank or static screen with the scripted input |
| Jurassic Park (USA) (Rev 1).sfc | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## SNES coprocessor cartridges

| Chip | Hooks cover | ROMs | Palette verified |
|---|---|---|---|
| Cx4 | main CPU only | 2 | 2 |
| DSP | everything | 3 | 3 |
| OBC1 | everything | 1 | 1 |
| S-DD1 | main CPU only | 2 | 2 |
| SA-1 | main CPU only | 5 | 4 |
| SuperFX | main CPU only | 4 | 2 |

- Cx4: Mega Man X2 (USA).sfc (verified); Mega Man X3 (USA).sfc (verified)
- S-DD1: Star Ocean (Japan) [T-En by DeJap v1.0].sfc (verified); Street Fighter Alpha 2 (USA).sfc (verified)
- SA-1: Dragon Ball Z - Hyper Dimension (Japan) [T-En by Twilight Translations v1.00].sfc (verified); Jikkyou Oshaberi Parodius (Japan).sfc (verified); Kirby Super Star (USA).sfc (verified); Kirby's Dream Land 3 (USA).sfc (none); Super Mario RPG - Legend of the Seven Stars (USA).sfc (verified)
- SuperFX: Star Fox (USA) (Rev 2).sfc (verified); Star Fox 2 (USA, Europe).sfc (located); Stunt Race FX (USA) (Rev 1).sfc (verified); Super Mario World 2 - Yoshi's Island (USA) (Rev 1).sfc (none)
