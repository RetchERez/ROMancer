"""Apply ROMancer provenance hooks to an mGBA source tree (argv[1]), Game Boy side only.

Domains match the Gambatte tracing build exactly: vram 0x4000 (both CGB banks),
wram 0x8000 (eight 4 KiB banks), hram 0x80 (FF80-FFFF), oam 0xA0,
palette 0x80 (64 BG bytes then 64 OBJ bytes, FF69/FF6B), dmg_palette 3 (BGP, OBP0, OBP1).

Every SM83 bus access goes through _SM83Step in src/sm83/sm83.c (opcode fetch,
operand fetch and data load), so the CPU read hooks live there and cover both
the GBCartLoad8 active-region fast path and the GBLoad8 slow path.
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])


def edit(rel, old, new, count=1):
    p = root / rel
    t = p.read_text(encoding='utf-8', newline='')
    if '\r\n' in t:
        old, new = old.replace('\n', '\r\n'), new.replace('\n', '\r\n')
    if t.count(old) != count:
        raise SystemExit(f'{rel}: expected {count} of {old!r}, found {t.count(old)}')
    p.write_text(t.replace(old, new), encoding='utf-8', newline='')


T = '#ifdef ROMANCER_TRACE\n{}\n#endif\n'

# ---- memory.h: hook prototypes --------------------------------------------
edit('include/mgba/internal/gb/memory.h', 'void GBMemoryInit(struct GB* gb);\n',
     T.format('struct SM83Core;\n'
              'void GBRTInit(struct GB* gb);\n'
              'void GBRTPalette(unsigned index, uint8_t value);\n'
              'void GBRTDmgPalette(unsigned index, uint8_t value);\n'
              'void GBRTCpuAccess(struct SM83Core* cpu, uint16_t address, uint8_t value, int kind);')
     + 'void GBMemoryInit(struct GB* gb);\n')

# ---- memory.c: state, tag lookup, registration ------------------------------
IMPL = r'''#ifdef ROMANCER_TRACE
#define ROMANCER_TRACE_IMPLEMENTATION
#include "romancer_trace.h"

static rt_domain *_rtVram, *_rtWram, *_rtHram, *_rtOam, *_rtPal, *_rtDmg;
enum { RT_CELLS = 0x4000 + 0x8000 + 0x80 + 0xA0 + 0x80 + 3 };
static uint32_t _rtTag[RT_CELLS], _rtPc[RT_CELLS];
static uint8_t _rtPalData[0x80], _rtDmgData[3];

/* Called at the end of GBReset: every buffer has its final address then. */
void GBRTInit(struct GB* gb) {
	uint32_t* t = _rtTag;
	uint32_t* c = _rtPc;
	int i;
	_rtVram = rt_register("vram", 0x4000, t, c, gb->video.vram); t += 0x4000; c += 0x4000;
	_rtWram = rt_register("wram", 0x8000, t, c, gb->memory.wram); t += 0x8000; c += 0x8000;
	/* mGBA keeps 0x7F HRAM bytes; index 0x7F (IE) is never tagged */
	_rtHram = rt_register("hram", 0x80, t, c, gb->memory.hram); t += 0x80; c += 0x80;
	_rtOam = rt_register("oam", 0xA0, t, c, gb->video.oam.raw); t += 0xA0; c += 0xA0;
	_rtPal = rt_register("palette", 0x80, t, c, _rtPalData); t += 0x80; c += 0x80;
	_rtDmg = rt_register("dmg_palette", 3, t, c, _rtDmgData);
	for (i = 0; i < 64; ++i) {
		_rtPalData[i * 2] = gb->video.palette[i];
		_rtPalData[i * 2 + 1] = gb->video.palette[i] >> 8;
	}
	for (i = 0; i < 3; ++i) {
		_rtDmgData[i] = gb->memory.io[GB_REG_BGP + i];
	}
}

/* ROM file offset behind a CPU address, or RT_PC_NONE (RAM, BIOS, MBC-mediated reads). */
static uint32_t _GBRTRomOffset(const struct GBMemory* memory, uint16_t address) {
	const uint8_t* p;
	if (address >= GB_BASE_VRAM || !memory->rom || !memory->romSize) {
		return RT_PC_NONE;
	}
	if (address < GB_BASE_CART_BANK1) {
		if (memory->mbcReadBank0 || address >= memory->romSize) {
			return RT_PC_NONE;
		}
		p = memory->romBase + (address & (GB_SIZE_CART_BANK0 - 1));
	} else if (address >= GB_BASE_CART_BANK1 + 0x2000 && (memory->mbcType == GB_MBC6 || (memory->mbcType == GB_UNL_NT_NEW && memory->mbcState.ntNew.splitMode))) {
		p = memory->romBank1 + (address & (GB_SIZE_CART_HALFBANK - 1));
	} else {
		if (memory->mbcReadBank1 || address >= memory->romSize) {
			return RT_PC_NONE;
		}
		p = memory->romBank + (address & (GB_SIZE_CART_BANK0 - 1));
	}
	if (!p || p < memory->rom || p >= memory->rom + memory->romSize) {
		return RT_PC_NONE;
	}
	return (uint32_t) (p - memory->rom);
}

/* Tag of the byte a CPU address currently maps to, provided it holds `value`
 * (a blocked or MBC-mediated read returns something else and gets RT_NONE). */
static uint32_t _GBRTTagOf(struct GB* gb, uint16_t address, uint8_t value) {
	struct GBMemory* memory = &gb->memory;
	rt_domain* d;
	uint32_t index;
	if (address < GB_BASE_VRAM) {
		uint32_t off = _GBRTRomOffset(memory, address);
		if (off == RT_PC_NONE || memory->rom[off] != value) {
			return RT_NONE;
		}
		return RT_TAG(RT_ROM, off);
	}
	if (address < GB_BASE_EXTERNAL_RAM) {
		d = _rtVram;
		index = (uint32_t) (gb->video.vramBank - gb->video.vram) + (address & (GB_SIZE_VRAM_BANK0 - 1));
	} else if (address < GB_BASE_WORKING_RAM_BANK0) {
		return RT_NONE; /* cartridge RAM is not traced */
	} else if (address < GB_BASE_WORKING_RAM_BANK1 || (address >= 0xE000 && address < 0xF000)) {
		d = _rtWram;
		index = address & (GB_SIZE_WORKING_RAM_BANK0 - 1);
	} else if (address < GB_BASE_OAM) {
		d = _rtWram;
		index = (uint32_t) (memory->wramBank - memory->wram) + (address & (GB_SIZE_WORKING_RAM_BANK0 - 1));
	} else if (address < GB_BASE_UNUSABLE) {
		d = _rtOam;
		index = address & 0xFF;
	} else if (address >= GB_BASE_HRAM && address < GB_BASE_IE) {
		d = _rtHram;
		index = address & GB_SIZE_HRAM;
	} else {
		return RT_NONE;
	}
	if (!d || index >= d->size || d->data[index] != value) {
		return RT_NONE;
	}
	return rt_tag_at(d, index);
}

static uint32_t _GBRTDmaTag(uint32_t tag, uint8_t value) {
	if (tag != RT_NONE && (value == 0x00 || value == 0xFF)) {
		tag |= RT_WEAK;
	}
	return tag;
}

/* kind: 0 opcode fetch, 1 operand fetch, 2 data load. */
void GBRTCpuAccess(struct SM83Core* cpu, uint16_t address, uint8_t value, int kind) {
	if (!romancer_trace.enabled) {
		return;
	}
	struct GB* gb = (struct GB*) cpu->master;
	if (kind == 0) {
		rt_instruction(_GBRTRomOffset(&gb->memory, address));
		return;
	}
	uint32_t tag = _GBRTTagOf(gb, address, value);
	if (RT_KIND(tag) == RT_ROM) {
		if (kind == 1) {
			rt_read_imm(tag & RT_OFFSET_MASK, value);
		} else {
			rt_read_rom(tag & RT_OFFSET_MASK, value);
		}
	} else {
		rt_read_tagged(tag, value);
	}
}

void GBRTPalette(unsigned index, uint8_t value) {
	_rtPalData[index & 0x7F] = value;
	rt_write(_rtPal, index & 0x7F, value);
}

void GBRTDmgPalette(unsigned index, uint8_t value) {
	if (index < 3) {
		_rtDmgData[index] = value;
		rt_write(_rtDmg, index, value);
	}
}
#endif
'''
edit('src/gb/memory.c', 'static void _pristineCow(struct GB* gba);\n',
     'static void _pristineCow(struct GB* gba);\n\n' + IMPL)

# CPU stores (GBStore8), at the physically stored index.
M = 'src/gb/memory.c'
edit(M, '\t\t\tgb->video.renderer->writeVRAM(gb->video.renderer, (address & (GB_SIZE_VRAM_BANK0 - 1)) | (GB_SIZE_VRAM_BANK0 * gb->video.vramCurrentBank));\n'
        '\t\t\tgb->video.vramBank[address & (GB_SIZE_VRAM_BANK0 - 1)] = value;\n',
     '\t\t\tgb->video.renderer->writeVRAM(gb->video.renderer, (address & (GB_SIZE_VRAM_BANK0 - 1)) | (GB_SIZE_VRAM_BANK0 * gb->video.vramCurrentBank));\n'
     '\t\t\tgb->video.vramBank[address & (GB_SIZE_VRAM_BANK0 - 1)] = value;\n'
     + T.format('\t\t\trt_write(_rtVram, (uint32_t) (gb->video.vramBank - gb->video.vram) + (address & (GB_SIZE_VRAM_BANK0 - 1)), (uint8_t) value);'))
edit(M, '\t\tmemory->wram[address & (GB_SIZE_WORKING_RAM_BANK0 - 1)] = value;\n\t\treturn;\n',
     '\t\tmemory->wram[address & (GB_SIZE_WORKING_RAM_BANK0 - 1)] = value;\n'
     + T.format('\t\trt_write(_rtWram, address & (GB_SIZE_WORKING_RAM_BANK0 - 1), (uint8_t) value);') + '\t\treturn;\n')
edit(M, '\t\tmemory->wramBank[address & (GB_SIZE_WORKING_RAM_BANK0 - 1)] = value;\n\t\treturn;\n',
     '\t\tmemory->wramBank[address & (GB_SIZE_WORKING_RAM_BANK0 - 1)] = value;\n'
     + T.format('\t\trt_write(_rtWram, (uint32_t) (memory->wramBank - memory->wram) + (address & (GB_SIZE_WORKING_RAM_BANK0 - 1)), (uint8_t) value);') + '\t\treturn;\n')
edit(M, '\t\tif (address < GB_BASE_OAM) {\n\t\t\tmemory->wramBank[address & (GB_SIZE_WORKING_RAM_BANK0 - 1)] = value;\n\t\t} else if',
     '\t\tif (address < GB_BASE_OAM) {\n\t\t\tmemory->wramBank[address & (GB_SIZE_WORKING_RAM_BANK0 - 1)] = value;\n'
     + T.format('\t\t\trt_write(_rtWram, (uint32_t) (memory->wramBank - memory->wram) + (address & (GB_SIZE_WORKING_RAM_BANK0 - 1)), (uint8_t) value);') + '\t\t} else if')
edit(M, '\t\t\t\tgb->video.oam.raw[address & 0xFF] = value;\n\t\t\t\tgb->video.renderer->writeOAM(gb->video.renderer, address & 0xFF);\n',
     '\t\t\t\tgb->video.oam.raw[address & 0xFF] = value;\n'
     + T.format('\t\t\t\trt_write(_rtOam, address & 0xFF, (uint8_t) value);')
     + '\t\t\t\tgb->video.renderer->writeOAM(gb->video.renderer, address & 0xFF);\n')
edit(M, '\t\t\tmemory->hram[address & GB_SIZE_HRAM] = value;\n\t\t} else {\n\t\t\tGBIOWrite(gb, GB_REG_IE, value);\n',
     '\t\t\tmemory->hram[address & GB_SIZE_HRAM] = value;\n'
     + T.format('\t\t\trt_write(_rtHram, address & GB_SIZE_HRAM, (uint8_t) value);')
     + '\t\t} else {\n\t\t\tGBIOWrite(gb, GB_REG_IE, value);\n')

# OAM DMA keeps its source tag.
edit(M, '\tgb->video.oam.raw[gb->memory.dmaDest] = b;\n',
     '\tgb->video.oam.raw[gb->memory.dmaDest] = b;\n'
     + T.format('\tif (romancer_trace.enabled) {\n'
                '\t\trt_write_tag(_rtOam, gb->memory.dmaDest, _GBRTDmaTag(_GBRTTagOf(gb, gb->memory.dmaSource, b), b));\n'
                '\t}'))
# GDMA/HDMA: the store goes through GBStore8; overwrite its ring guess with the source tag.
edit(M, '\tgb->cpu->memory.store8(gb->cpu, gb->memory.hdmaDest, b);\n',
     '\tgb->cpu->memory.store8(gb->cpu, gb->memory.hdmaDest, b);\n'
     + T.format('\tif (romancer_trace.enabled && _rtVram) {\n'
                '\t\tuint32_t rtIndex = (uint32_t) (gb->video.vramBank - gb->video.vram) + (gb->memory.hdmaDest & (GB_SIZE_VRAM_BANK0 - 1));\n'
                '\t\tif (gb->video.vram[rtIndex] == b) {\n'
                '\t\t\trt_write_tag(_rtVram, rtIndex, _GBRTDmaTag(_GBRTTagOf(gb, gb->memory.hdmaSource, b), b));\n'
                '\t\t}\n'
                '\t}'))

# ---- gb.c: register domains once every buffer exists -------------------------
edit('src/gb/gb.c', '\tGBIOReset(gb);\n', '\tGBIOReset(gb);\n' + T.format('\tGBRTInit(gb);'))

# ---- sm83.c: opcode fetch, operand fetch, data loads ------------------------
S = 'src/sm83/sm83.c'
edit(S, '#include <mgba/internal/sm83/isa-sm83.h>\n',
     '#include <mgba/internal/sm83/isa-sm83.h>\n\n'
     '#ifdef ROMANCER_TRACE\n'
     'void GBRTCpuAccess(struct SM83Core* cpu, uint16_t address, uint8_t value, int kind);\n'
     '#define RT_CPU(a, v, k) GBRTCpuAccess(cpu, (a), (v), (k))\n'
     '#else\n'
     '#define RT_CPU(a, v, k) ((void) 0)\n'
     '#endif\n')
edit(S, '\t\tcpu->bus = cpu->memory.cpuLoad8(cpu, cpu->pc);\n\t\tcpu->instruction = _sm83InstructionTable[cpu->bus];\n\t\t++cpu->pc;\n',
     '\t\tcpu->bus = cpu->memory.cpuLoad8(cpu, cpu->pc);\n\t\tRT_CPU(cpu->pc, cpu->bus, 0);\n\t\tcpu->instruction = _sm83InstructionTable[cpu->bus];\n\t\t++cpu->pc;\n')
edit(S, '\t\tcpu->bus = cpu->memory.load8(cpu, cpu->index);\n',
     '\t\tcpu->bus = cpu->memory.load8(cpu, cpu->index);\n\t\tRT_CPU(cpu->index, cpu->bus, 2);\n')
edit(S, '\tcase SM83_CORE_READ_PC:\n\t\tcpu->bus = cpu->memory.cpuLoad8(cpu, cpu->pc);\n',
     '\tcase SM83_CORE_READ_PC:\n\t\tcpu->bus = cpu->memory.cpuLoad8(cpu, cpu->pc);\n\t\tRT_CPU(cpu->pc, cpu->bus, 1);\n')
edit(S, '\t\tcpu->bus = cpu->memory.cpuLoad8(cpu, cpu->pc);\n\t\tcpu->instruction = _sm83InstructionTable[cpu->bus];\n\t\tbreak;\n',
     '\t\tcpu->bus = cpu->memory.cpuLoad8(cpu, cpu->pc);\n\t\tRT_CPU(cpu->pc, cpu->bus, 0);\n\t\tcpu->instruction = _sm83InstructionTable[cpu->bus];\n\t\tbreak;\n')

# ---- palettes ----------------------------------------------------------------
edit('src/gb/io.c', '\t\tGBVideoProcessDots(&gb->video, 0);\n\t\tGBVideoWritePalette(&gb->video, address, value);\n\t\tbreak;\n',
     '\t\tGBVideoProcessDots(&gb->video, 0);\n\t\tGBVideoWritePalette(&gb->video, address, value);\n'
     + T.format('\t\tGBRTDmgPalette(address - GB_REG_BGP, value);') + '\t\tbreak;\n')
V = 'src/gb/video.c'
edit(V, '\t\t\t\tvideo->renderer->writePalette(video->renderer, video->bcpIndex >> 1, video->palette[video->bcpIndex >> 1]);\n',
     '\t\t\t\tvideo->renderer->writePalette(video->renderer, video->bcpIndex >> 1, video->palette[video->bcpIndex >> 1]);\n'
     + T.format('\t\t\t\tGBRTPalette(video->bcpIndex, value);'))
edit(V, '\t\t\t\tvideo->renderer->writePalette(video->renderer, 8 * 4 + (video->ocpIndex >> 1), video->palette[8 * 4 + (video->ocpIndex >> 1)]);\n',
     '\t\t\t\tvideo->renderer->writePalette(video->renderer, 8 * 4 + (video->ocpIndex >> 1), video->palette[8 * 4 + (video->ocpIndex >> 1)]);\n'
     + T.format('\t\t\t\tGBRTPalette(0x40 + video->ocpIndex, value);'))

# ---- export the romancer_trace_* API ------------------------------------------
p = root / 'src' / 'platform' / 'libretro' / 'link.T'
t = p.read_text(encoding='utf-8', newline='')
if 'romancer_trace_' not in t:
    if t.count('global: retro_*;') != 1:
        raise SystemExit('link.T: expected one "global: retro_*;"')
    p.write_text(t.replace('global: retro_*;', 'global: retro_*; romancer_trace_*;'), encoding='utf-8', newline='')
print('mgba hooks applied')
