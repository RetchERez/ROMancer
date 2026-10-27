"""Original hardware summaries and read-only address-domain classification.

Hardware ranges explain where to investigate; they never identify a game field,
observe mapper state, read a device, translate to a file offset or authorize edits.
"""
from copy import deepcopy

_GB='https://gbdev.io/pandocs/Memory_Map.html'
_NES='https://www.nesdev.org/wiki/CPU_memory_map'
_SNES='https://snes.nesdev.org/wiki/Memory_map'
_MD='https://www.plutiedev.com/memory-map'
_GBA='https://problemkaputt.de/gbatek.htm#gbamemorymap'
_SMS='https://www.smspower.org/Development/MemoryMap'

_SYSTEMS={
 'sms':dict(name='Master System',cpu='Z80',endian='little',domains={'cpu':0xffff,'vram':0x3fff},
   graphics='Mode 4 uses 8×8 tiles with four bitplane bytes per row, 32 bytes per tile and 16 stored indices. Palette selection and sprite assembly are separate data.',
   mapping='CPU cartridge windows are not file offsets. The documented Sega mapper has three 16 KiB slots and an unpaged first 1 KiB; the header alone does not prove this mapper or its active bank state.',
   references=[_SMS,'https://www.smspower.org/Development/Tiles','https://www.smspower.org/Development/ROMHeader','https://www.smspower.org/Development/SN76489']),
 'nes':dict(name='NES',cpu='Ricoh 2A03/2A07 · 6502 family',endian='little',domains={'cpu':0xffff,'ppu':0x3fff},
   graphics='Common 8×8 tiles use 16 bytes: eight low-plane rows, then eight high-plane rows. CHR-RAM graphics may be generated or decompressed during play.',
   mapping='Read the 16-byte header, optional 512-byte trainer, PRG size and mapper. CPU and PPU have separate buses.',
   references=[_NES,'https://www.nesdev.org/wiki/PPU_memory_map','https://www.nesdev.org/wiki/NES_2.0']),
 'snes':dict(name='SNES',cpu='Ricoh 5A22 · 65C816 family',endian='little',domains={'cpu':0xffffff,'vram':0xffff,'apu':0xffff},
   graphics='Common planar 8×8 tiles use 16/32/64 bytes at 2/4/8bpp. Palette, layer mode and color math are separate from tile data.',
   mapping='Establish LoROM/HiROM or a special map and any 512-byte copier header. M/X processor flags change immediate instruction widths.',
   references=[_SNES,'https://snes.nesdev.org/wiki/PPU_registers','https://snes.nesdev.org/wiki/S-SMP']),
 'genesis':dict(name='Genesis',cpu='Motorola 68000 main CPU · Z80 sound CPU',endian='big',domains={'cpu':0xffffff,'vram':0xffff},
   graphics='Common VDP 8×8 tiles use 32 packed-nibble bytes. Tile attributes select palette, flips and priority.',
   mapping='Establish raw linear dump format and cartridge mapping. Base 68000 words and instructions require even alignment; sound RAM uses a separate bus.',
   references=[_MD,'https://www.plutiedev.com/rom-header','https://www.plutiedev.com/tiles-and-palettes']),
 'gb':dict(name='Game Boy',cpu='Sharp SM83 · not a full Z80',endian='little',domains={'cpu':0xffff,'vram':0x1fff},
   graphics='Common 8×8 tiles use 16 bytes with two bitplane bytes per row. DMG palette registers select shades, not RGB555 colors.',
   mapping='Record cartridge type and current bank/mode. MBC1 can change the lower ROM window; external cartridge space can expose RTC or other hardware.',
   references=[_GB,'https://gbdev.io/pandocs/MBCs.html','https://gbdev.io/pandocs/Tile_Data.html']),
 'gbc':dict(name='Game Boy Color',cpu='Sharp SM83 · CGB banked memory',endian='little',domains={'cpu':0xffff,'vram':0x3fff},
   graphics='Tiles use the paired 2bpp format. Two VRAM banks, per-cell attributes and RGB555 palettes affect the composed image.',
   mapping='Record cartridge bank/mode plus VRAM and WRAM banks. CPU addresses alone do not establish physical ROM or video offsets.',
   references=[_GB,'https://gbdev.io/pandocs/Tile_Maps.html','https://gbdev.io/pandocs/Palettes.html']),
 'gba':dict(name='GBA',cpu='ARM7TDMI · ARM and THUMB execution states',endian='little',domains={'cpu':0xffffffff},
   graphics='4bpp/8bpp tiled graphics, bitmap modes and sprite mappings use different layouts. Compression and ownership require separate evidence.',
   mapping='ROM wait-state windows mirror cartridge storage. RAM, palette RAM, VRAM, OAM and I/O have separate regions; cartridge saves can use several protocols.',
   references=[_GBA,'https://problemkaputt.de/gbatek.htm#gbalcdvideocontroller']),
}


def reference_for(system_id):
    if type(system_id) is not str or system_id not in _SYSTEMS:raise ValueError('unsupported reference system')
    return {'ok':True,'system_id':system_id,**deepcopy(_SYSTEMS[system_id]),
            'endian_note':'CPU convention only; game data can use custom encodings.',
            'checks':['Keep file offset, CPU address and video-memory offset separate.',
                      'A changing RAM value does not identify its ROM initializer or writer.',
                      'Unexecuted bytes and repeated FF/00 runs do not prove unused space.',
                      'Confirm exact source bytes, review a separate build, then test the affected behavior.'],
            'game_semantics_verified':False,'write_authorized':False}


def _cpu(system,address):
    if system=='sms':
        if address<0xc000:return 'cartridge','Cartridge or attached-device window','Establish the cartridge mapper and active banks before resolving any ROM file offset. Boot/device overlays are separate.',True
        if address<0xe000:return 'ram','System work RAM','8 KiB work RAM. Runtime values do not identify ROM initialization data or the instruction that changes them.',False
        return 'ram-mirror','System RAM mirror and device controls','Mirrors 8 KiB work RAM. On the documented Sega mapper, writes at 0xFFFC–0xFFFF also control cartridge mapping; reads return RAM. Do not assume the mapper from a header.',False
    if system in ('gb','gbc'):
        if address<0x8000:return 'rom-window','Cartridge ROM window','Establish mapper mode and physical bank. Boot ROM overlays can affect startup reads.',True
        if address<0xa000:return 'graphics','Video RAM','CGB selects a VRAM bank; access also depends on display timing.',False
        if address<0xc000:return 'cartridge','External cartridge window','May expose RAM, RTC registers or mapper-specific hardware; do not assume a battery-save byte.',True
        if address<0xe000:return 'ram','Work RAM','CGB upper WRAM window is banked. A runtime variable is not a ROM file offset.',False
        if address<0xfe00:return 'ram-mirror','Work RAM echo','Mirrored RAM can display the same underlying variable at another CPU address.',False
        if address<0xfea0:return 'graphics','Sprite attribute memory (OAM)','Runtime sprite entries do not establish metasprite storage in ROM.',False
        if address<0xff00:return 'unusable','Unusable region','Hardware behavior varies; this is not available scratch storage.',False
        if address<0xff80 or address==0xffff:return 'io','Hardware register','Reads and writes can have device side effects; this tool only describes the range.',False
        return 'ram','High RAM','Runtime CPU-local storage, separate from cartridge ROM.',False
    if system=='nes':
        if address<0x2000:return 'ram-mirror' if address>=0x800 else 'ram','Internal RAM','The 2 KiB RAM repeats through CPU 0x1FFF.',False
        if address<0x4000:return 'io','PPU register port','Eight CPU-facing registers repeat here. These numbers are not PPU memory addresses.',False
        if address<=0x4017:return 'io','Audio/controller register','Register behavior depends on the exact address and access direction.',False
        if address<0x4020:return 'reserved','CPU test/reserved region','Not general writable memory.',False
        if address<0x8000:return 'cartridge','Cartridge-dependent window','May contain expansion hardware, mapper registers or PRG RAM.',True
        return 'rom-window','PRG cartridge window','Use the actual mapper, selected bank, header and trainer to find file bytes.',True
    if system=='snes':
        bank=address>>16;within=address&0xffff
        if bank in (0x7e,0x7f):return 'ram','Work RAM','128 KiB WRAM is separate from ROM and audio RAM.',False
        if bank<0x40 or 0x80<=bank<0xc0:
            if within<0x2000:return 'ram-mirror','Low WRAM mirror','Mirrors the first 8 KiB of work RAM.',False
            if 0x2100<=within<=0x213f:return 'io','PPU register port','VRAM, OAM and palette data are accessed through ports; register latch state matters.',False
            if 0x2140<=within<=0x217f:return 'io','Audio communication port or mirror','Four ports repeat through this range and exchange commands with SPC700; they are not its 64 KiB audio RAM.',False
            if 0x2180<=within<=0x2183:return 'io','WRAM access port','Port address/state selects work RAM; it is not a linear ROM mapping.',False
            if within in (0x4016,0x4017) or 0x4200<=within<=0x421f or 0x4300<=within<=0x437f:return 'io','CPU/controller/DMA register','Read/write direction, interrupt state and DMA timing matter.',False
        return 'cartridge','Cartridge or board-dependent window','LoROM/HiROM, SRAM and enhancement hardware determine the actual device. Declare a checked map before resolving file bytes.',True
    if system=='genesis':
        if address<0x400000:return 'rom-window','Initial cartridge window','A raw linear dump and ordinary cartridge map may resolve directly; header checks alone do not prove board behavior.',True
        if 0xa00000<=address<=0xa0ffff:return 'coprocessor-window','Z80 bus window','Main CPU access requires correct bus arbitration. This is not a ROM file address.',False
        if 0xa10000<=address<=0xa1001f or 0xa11100<=address<=0xa11101 or 0xa11200<=address<=0xa11201:return 'io','System or Z80 control register','Canonical Z80 bus request is 0xA11100; reset is 0xA11200. Access direction and bus state matter.',False
        if 0xc00000<=address<=0xdfffff:
            if address&0x20:return 'unusable','VDP decoding gap','These mirrored VDP decoding offsets can hang the bus; this is not video storage.',False
            return 'io','VDP port or mirror','VDP commands select video storage; ports are separate from VRAM addresses.',False
        if address>=0xe00000:return ('ram' if address>=0xff0000 else 'ram-mirror'),'Work RAM or mirror','64 KiB main work RAM repeats in this decoded region; 0xFF0000 is the canonical base.',False
        return 'cartridge','Board-dependent or unmapped area','Cartridge wiring and hardware determine behavior; do not treat gaps as free RAM.',True
    if address<0x4000:return 'boot-rom','BIOS region','BIOS addresses refer to separate system firmware, not cartridge file bytes.',False
    if 0x02000000<=address<0x03000000:return ('ram' if address<0x02040000 else 'ram-mirror'),'External work RAM or mirror','256 KiB EWRAM repeats in this region. Runtime data is separate from cartridge storage.',False
    if 0x03000000<=address<0x04000000:return ('ram' if address<0x03008000 else 'ram-mirror'),'Internal work RAM or mirror','32 KiB IWRAM repeats in this region. Runtime data is separate from cartridge storage.',False
    if 0x04000000<=address<0x04000400:return 'io','I/O address region','Display, sound, timers, DMA and input have address-specific behavior; some addresses are unimplemented.',False
    if 0x05000000<=address<0x08000000:return 'graphics','Palette, video or sprite memory and mirrors','Palette/OAM repeat every 1 KiB. VRAM repeats every 128 KiB with its upper 32 KiB mirroring the previous 32 KiB. This does not identify the source ROM resource.',False
    if 0x08000000<=address<0x0e000000:return 'rom-window','Cartridge wait-state window','Establish source bounds and cartridge behavior; some games map EEPROM through cartridge accesses.',True
    if 0x0e000000<=address<0x10000000:return 'cartridge','Cartridge storage window','Save RAM/Flash behavior depends on the cartridge; a save state is a different format.',True
    return 'unclassified','Unclassified region','This bounded classifier does not resolve every hardware mirror or game-specific device here.',False


def classify_address(system_id,address,domain='cpu'):
    ref=reference_for(system_id)
    if type(domain) is not str or domain not in ref['domains']:raise ValueError('unsupported address domain for this system')
    if type(address) is not int or not 0<=address<=ref['domains'][domain]:raise ValueError('address is outside this domain')
    if domain=='cpu':kind,label,note,mapping=_cpu(system_id,address)
    elif domain=='apu':
        kind,label,note,mapping=('io','SPC700 hardware register','Audio-CPU registers 0xF0–0xFF include communication ports 0xF4–0xF7, separate from main CPU 0x2140–0x2143.',False) if 0xf0<=address<=0xff else ('audio-ram','SPC700 audio address space','Audio RAM has a possible boot-ROM overlay at 0xFFC0–0xFFFF. Echo buffers, driver and samples need separate allocation evidence.',False)
    elif domain=='ppu':
        if address<0x2000:label='Pattern-table address space';note='CHR ROM/RAM and mapper selection determine what is displayed.'
        elif address<0x3f00:label='Nametable address space';note='Mirroring and board wiring select underlying nametable storage.'
        else:label='Palette address space';note='Palette aliases and rendering emphasis affect the displayed colors.'
        kind,mapping='graphics',False
    else:kind,label,note,mapping='graphics','Physical video-memory offset','Video storage is separate from file offsets. Bank, tile layout and palette ownership require additional evidence.',False
    return {'ok':True,'system_id':system_id,'domain':domain,'address':address,'kind':kind,'label':label,'note':note,
            'requires_mapping':mapping,'file_offset':None,'bank_state_observed':False,'game_semantics_verified':False,
            'write_authorized':False,'references':ref['references']}
