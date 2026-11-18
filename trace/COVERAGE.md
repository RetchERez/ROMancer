| System | Traced / in catalog | Palette verified | ram-only | traced | located | derived | none | errors | Graphics direct | derived | none |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gb | 139 / 139 | 138 | 0 | 1 | 0 | 0 | 0 | 0 | 128 | 11 | 0 |
| gbc | 95 / 95 | 95 | 0 | 0 | 0 | 0 | 0 | 0 | 79 | 16 | 0 |
| genesis | 140 / 140 | 139 | 0 | 0 | 0 | 0 | 1 | 0 | 78 | 62 | 0 |
| nes | 229 / 229 | 229 | 0 | 0 | 0 | 0 | 0 | 0 | 215 | 14 | 0 |
| sms | 49 / 49 | 49 | 0 | 0 | 0 | 0 | 0 | 0 | 46 | 3 | 0 |
| snes | 290 / 290 | 290 | 0 | 0 | 0 | 0 | 0 | 0 | 262 | 28 | 0 |
| all | 942 / 942 | 940 | 0 | 1 | 0 | 0 | 1 | 0 | 808 | 134 | 0 |

## How the verified edits were found

| System | traced | other scene | plain copy | code number | measured | needed the second input script | needed a scene between the main ones |
|---|---|---|---|---|---|---|---|
| gb | 134 | 1 | 1 | 1 | 1 | 1 | 2 |
| gbc | 91 | 0 | 4 | 0 | 0 | 0 | 1 |
| genesis | 132 | 0 | 7 | 0 | 0 | 0 | 5 |
| nes | 229 | 0 | 0 | 0 | 0 | 0 | 0 |
| sms | 49 | 0 | 0 | 0 | 0 | 0 | 1 |
| snes | 286 | 0 | 4 | 0 | 0 | 1 | 0 |
| all | 921 | 1 | 16 | 1 | 1 | 2 | 9 |

## gb: 1 not verified

By cause: inexact source 1

| ROM | Palette | Cause |
|---|---|---|
| Wario Blast Featuring Bomberman! (USA, Europe) (SGB Enhanced) | traced | inexact source: the traced bytes move the color but not to the planned value (shared code value or partial source). Looked at by hand: one table byte is the final value of all three shade registers, and the program also compares the palette with that same number in six places to end its fades, so changing the table byte alone changes how the game runs. An edit would have to change those compares too. |

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
