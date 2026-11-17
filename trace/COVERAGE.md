| System | Traced / in catalog | Palette verified | ram-only | traced | located | derived | none | errors | Graphics direct | derived | none |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gb | 139 / 139 | 132 | 2 | 2 | 2 | 1 | 0 | 0 | 128 | 11 | 0 |
| gbc | 94 / 95 | 89 | 3 | 1 | 0 | 1 | 0 | 0 | 78 | 16 | 0 |
| genesis | 139 / 140 | 126 | 0 | 5 | 4 | 3 | 1 | 0 | 77 | 62 | 0 |
| nes | 228 / 229 | 227 | 1 | 0 | 0 | 0 | 0 | 0 | 214 | 14 | 0 |
| sms | 48 / 49 | 47 | 0 | 0 | 0 | 0 | 1 | 0 | 45 | 3 | 0 |
| snes | 290 / 290 | 285 | 1 | 1 | 1 | 0 | 2 | 0 | 263 | 27 | 0 |
| all | 938 / 942 | 906 | 7 | 9 | 7 | 5 | 4 | 0 | 805 | 133 | 0 |

In the catalog but not swept (4): Castlevania (USA); Deja Vu I & II - The Casebooks of Ace Harding (USA); Immortal, The (USA, Europe); Rastan (USA, Europe, Brazil) (En)

## gb: 7 not verified

By cause: computed 3, not on screen 2, inexact source 1, no effect 1

| ROM | Palette | Cause |
|---|---|---|
| Contra - The Alien Wars (USA) (SGB Enhanced) | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Legend of the River King GB (USA) (SGB Enhanced) | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Super Mario Land 2 - 6 Golden Coins (USA, Europe) (Rev 2) | derived | computed: palette is decompressed or generated and no nearby ROM byte moved it |
| Kirby's Dream Land (USA, Europe) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Wario Blast Featuring Bomberman! (USA, Europe) (SGB Enhanced) | traced | no effect: editing the traced bytes did not change the color (data already copied before the first checkpoint, or a value coincidence) |
| DuckTales 2 (USA) | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |
| Monster Max (Europe) (En,Fr,De,Es,It,Nl) | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## gbc: 5 not verified

By cause: not on screen 3, inexact source 1, computed 1

| ROM | Palette | Cause |
|---|---|---|
| Mega Man Xtreme 2 (USA, Europe) | derived | computed: palette is decompressed or generated and no nearby ROM byte moved it |
| Resident Evil Gaiden (USA) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Metal Gear Solid (USA) | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |
| Shantae (USA) | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |
| Wendy - Every Witch Way (USA, Europe) | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## genesis: 13 not verified

By cause: computed 7, inexact source 4, no picture 1, no effect 1

| ROM | Palette | Cause |
|---|---|---|
| Aladdin (USA) | derived | computed: palette is decompressed or generated and no nearby ROM byte moved it |
| Combat Cars (USA, Europe) | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Donald in Maui Mallard (Europe) (Rev A) | derived | computed: palette is decompressed or generated and no nearby ROM byte moved it |
| Gynoug (Europe) | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| James Pond 3 (USA, Europe) | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Mutant League Football (USA, Europe) | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Streets of Rage (World) (En,Ja) (Rev A) | derived | computed: palette is decompressed or generated and no nearby ROM byte moved it |
| Mazin Saga - Mutant Fighter (USA) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Mortal Kombat 3 (USA) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Puggsy (USA) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Ultimate Mortal Kombat 3 (USA) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source) |
| Golden Axe (World) (Rev A) | traced | no effect: editing the traced bytes did not change the color (data already copied before the first checkpoint, or a value coincidence) |
| QuackShot Starring Donald Duck (World) (En,Ja) (Rev A) | none | no picture: the game never left a blank or static screen with the scripted input |

## nes: 1 not verified

By cause: not on screen 1

| ROM | Palette | Cause |
|---|---|---|
| Mafat Conspiracy, The (USA) | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## sms: 1 not verified

By cause: no picture 1

| ROM | Palette | Cause |
|---|---|---|
| Sonic Chaos (Europe, Brazil) (En) | none | no picture: the game never left a blank or static screen with the scripted input |

## snes: 5 not verified

By cause: coprocessor 2, not on screen 1, no effect 1, computed 1

| ROM | Palette | Cause |
|---|---|---|
| Urban Strike (USA) | located | computed: palette is decompressed or generated; the ROM bytes that drive it were measured but are not plain colors |
| Kirby's Dream Land 3 (USA) | none | coprocessor: the SA-1 chip prepares these colors itself; only the main CPU is traced |
| Super Mario World 2 - Yoshi's Island (USA) (Rev 1) | none | coprocessor: the SuperFX chip prepares these colors itself; only the main CPU is traced |
| Flintstones, The - The Treasure of Sierra Madrock (USA) | traced | no effect: editing the traced bytes did not change the color (data already copied before the first checkpoint, or a value coincidence) |
| Jurassic Park (USA) (Rev 1) | ram-only | not on screen: edited colors reached palette RAM, but no sampled scene draws with them |

## SNES coprocessor cartridges

| Chip | Hooks cover | ROMs | Palette verified |
|---|---|---|---|
| Cx4 | main CPU only | 2 | 2 |
| DSP | everything | 3 | 3 |
| OBC1 | everything | 1 | 1 |
| S-DD1 | main CPU only | 1 | 1 |
| SA-1 | main CPU only | 4 | 3 |
| SuperFX | main CPU only | 3 | 2 |

- Cx4: Mega Man X2 (USA) (verified); Mega Man X3 (USA) (verified)
- S-DD1: Street Fighter Alpha 2 (USA) (verified)
- SA-1: Jikkyou Oshaberi Parodius (Japan) (verified); Kirby Super Star (USA) (verified); Kirby's Dream Land 3 (USA) (none); Super Mario RPG - Legend of the Seven Stars (USA) (verified)
- SuperFX: Star Fox (USA) (Rev 2) (verified); Stunt Race FX (USA) (Rev 1) (verified); Super Mario World 2 - Yoshi's Island (USA) (Rev 1) (none)
