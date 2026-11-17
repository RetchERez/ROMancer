"""Apply ROMancer provenance hooks to a Gambatte source tree (argv[1]).

Domain data is always the machine's real state:

* vram, wram, oam, hram and dmg_palette (BGP, OBP0, OBP1 at FF47-FF49) point
  straight at the core's own memory, which savestates save and restore.
* palette (64 BG bytes then 64 OBJ bytes, FF69/FF6B) is a view copied from the
  LCD's palette memory after every palette write, at the end of every
  GB::runFor (so after every retro_run), and whenever the whole machine state
  is replaced. Gambatte keeps the two halves in separate arrays and reuses
  bytes of them for the DMG registers, so they cannot be exposed in place.
  On DMG hardware the view is all zero (there is no CGB palette memory); on
  CGB hardware running a DMG game it shows the colors the picture is drawn
  with (the boot ROM's compatibility palette).

Tags are not part of a savestate. Whenever the machine state is replaced
(power-on after a game loads, retro_reset, retro_unserialize) every tag, the
read ring and the write counter are cleared: the bytes now come from the state,
not from writes this build watched, and a tag left over from another timeline
or another game would be a false claim. Tracing stays enabled or disabled as
it was. Callers that want provenance after a loadstate replay from it with
tracing on (provenance.verify_edit does).
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]) / 'libgambatte' / 'src'
# The edits are not idempotent: a second run would duplicate hooks before an anchor finally failed.
for _rel in ('gambatte-memory.h', 'gambatte-memory.cpp', 'gambatte.cpp', 'video.h', 'cpu.cpp'):
    if 'ROMANCER_TRACE' in (root / _rel).read_text(encoding='utf-8', newline=''):
        raise SystemExit(f'{_rel}: already patched; start from pristine source')


def edit(rel, old, new, count=1):
    p = root / rel
    t = p.read_text(encoding='utf-8', newline='')
    if '\r\n' in t:
        old, new = old.replace('\n', '\r\n'), new.replace('\n', '\r\n')
    if t.count(old) != count:
        raise SystemExit(f'{rel}: expected {count} of {old!r}, found {t.count(old)}')
    p.write_text(t.replace(old, new), encoding='utf-8', newline='')


T = '#ifdef ROMANCER_TRACE\n{}\n#endif\n'

# Cartridge: expose the ROM base and end.
edit('mem/cartridge.h', '         unsigned char * vramdata() const\n',
     '         const unsigned char * romBase() const { return memptrs_.romdata(); }\n'
     '         const unsigned char * romEnd() const { return memptrs_.romdataend(); }\n'
     '         unsigned rtWramSize() const { return (unsigned)(memptrs_.wramdataend() - memptrs_.wramdata(0)); }\n'
     '         unsigned char * vramdata() const\n')

HOOKS = r'''
#ifdef ROMANCER_TRACE
public:
	rt_domain *rtVram_, *rtWram_, *rtHram_, *rtOam_, *rtPal_, *rtDmg_;
	enum { RT_CELLS = 0x4000 + 0x8000 + 0x80 + 0xA0 + 0x80 + 3 };
	uint32_t rtTag_[RT_CELLS], rtPc_[RT_CELLS];
	unsigned char rtPalData_[0x80];
	void rtInit() {
		uint32_t *t = rtTag_, *c = rtPc_;
		rtVram_ = rt_register("vram", 0x4000, t, c, cart_.vramdata()); t += 0x4000; c += 0x4000;
		/* DMG carts allocate 8 KB of work RAM, CGB carts 32 KB: never expose bytes past the allocation. */
		rtWram_ = rt_register("wram", cart_.rtWramSize(), t, c, cart_.wramdata(0)); t += 0x8000; c += 0x8000;
		rtHram_ = rt_register("hram", 0x80, t, c, ioamhram_ + 0x180); t += 0x80; c += 0x80;
		rtOam_ = rt_register("oam", 0xA0, t, c, ioamhram_); t += 0xA0; c += 0xA0;
		rtPal_ = rt_register("palette", 0x80, t, c, rtPalData_); t += 0x80; c += 0x80;
		/* BGP, OBP0, OBP1: the registers themselves, so a loadstate restores them. */
		rtDmg_ = rt_register("dmg_palette", 3, t, c, ioamhram_ + 0x147);
		rtStateReplaced();
	}
	/* Copy the LCD's palette memory into the palette domain's view. */
	void rtSync() {
		for (unsigned i = 0; i < 0x80; ++i) rtPalData_[i] = lcd_.rtCgbPaletteByte(i);
	}
	/* Power-on, reset or loadstate replaced every byte: no tag describes it any more. */
	void rtStateReplaced() {
		romancer_trace_reset();
		rtSync();
	}
	/* Tag for the byte behind a host pointer, or RT_NONE. */
	uint32_t rtTagOfPtr(const unsigned char *q) const {
		if (q >= cart_.romBase() && q < cart_.romEnd()) return RT_TAG(RT_ROM, q - cart_.romBase());
		if (q >= cart_.vramdata() && q < cart_.vramdata() + 0x4000) return rt_tag_at(rtVram_, q - cart_.vramdata());
		if (q >= cart_.wramdata(0) && q < cart_.wramdata(0) + cart_.rtWramSize()) return rt_tag_at(rtWram_, q - cart_.wramdata(0));
		if (q >= ioamhram_ && q < ioamhram_ + 0xA0) return rt_tag_at(rtOam_, q - ioamhram_);
		if (q >= ioamhram_ + 0x180 && q < ioamhram_ + 0x200) return rt_tag_at(rtHram_, q - ioamhram_ - 0x180);
		return RT_NONE;
	}
	const unsigned char *rtPtr(unsigned p) const {
		if (p < 0x8000) return cart_.romdata(p >> 14) + p;
		if (p < 0xA000) return cart_.vrambankptr() + p;
		if (p >= 0xC000 && p < 0xFE00) return cart_.wramdata(p >> 12 & 1) + (p & 0xFFF);
		if (p >= 0xFE00 && p < 0xFEA0) return ioamhram_ + (p - 0xFE00);
		if (p >= 0xFF80 && p < 0xFFFF) return ioamhram_ + (p - 0xFE00);
		return 0;
	}
	uint32_t rtRomOffset(unsigned p) const {
		if (p >= 0x8000) return RT_PC_NONE;
		return (uint32_t)(cart_.romdata(p >> 14) + p - cart_.romBase());
	}
	void rtRead(unsigned p, unsigned value) {
		if (!romancer_trace.enabled) return;
		const unsigned char *q = rtPtr(p);
		uint32_t tag = q ? rtTagOfPtr(q) : RT_NONE;
		if (RT_KIND(tag) == RT_ROM) rt_read_rom(tag & RT_OFFSET_MASK, value);
		else rt_read_tagged(tag, value);
	}
	void rtFetch(unsigned p, unsigned value, bool opcode) {
		if (!romancer_trace.enabled) return;
		if (opcode) { rt_instruction(rtRomOffset(p)); return; }
		if (p < 0x8000) rt_read_imm(rtRomOffset(p), value);
		else rtRead(p, value);
	}
	/* A store into a traced host byte. */
	void rtStore(unsigned char *q, unsigned value) {
		if (!romancer_trace.enabled) return;
		if (q >= cart_.vramdata() && q < cart_.vramdata() + 0x4000) rt_write(rtVram_, q - cart_.vramdata(), value);
		else if (q >= cart_.wramdata(0) && q < cart_.wramdata(0) + cart_.rtWramSize()) rt_write(rtWram_, q - cart_.wramdata(0), value);
		else if (q >= ioamhram_ && q < ioamhram_ + 0xA0) rt_write(rtOam_, q - ioamhram_, value);
		else if (q >= ioamhram_ + 0x180 && q < ioamhram_ + 0x200) rt_write(rtHram_, q - ioamhram_ - 0x180, value);
	}
	/* A write to FF69/FF6B. The LCD ignores it while it is drawing, so tag it only if it landed. */
	void rtPalette(unsigned index, unsigned value) {
		unsigned now = lcd_.rtCgbPaletteByte(index);
		rtPalData_[index] = now;
		if (now == (value & 0xFF)) rt_write(rtPal_, index, value);
	}
#endif
'''
edit('gambatte-memory.h', '#ifdef HAVE_NETWORK\n\tvoid startSerialTransfer', HOOKS + '#ifdef HAVE_NETWORK\n\tvoid startSerialTransfer')
edit('gambatte-memory.h', '#include "interrupter.h"', '#include "interrupter.h"\n' + T.format('#include "romancer_trace.h"'))

# Fast write paths.
edit('gambatte-memory.h', '\t\tif (cart_.wmem(p >> 12)) {\n\t\t\tcart_.wmem(p >> 12)[p] = data;\n',
     '\t\tif (cart_.wmem(p >> 12)) {\n\t\t\tcart_.wmem(p >> 12)[p] = data;\n' + T.format('\t\t\trtStore(cart_.wmem(p >> 12) + p, data);'))
edit('gambatte-memory.h', '\t\tif (p - 0x80u < 0x7Fu) {\n\t\t\tioamhram_[p + 0x100] = data;\n',
     '\t\tif (p - 0x80u < 0x7Fu) {\n\t\t\tioamhram_[p + 0x100] = data;\n' + T.format('\t\t\trtStore(ioamhram_ + p + 0x100, data);'))

# Slow write paths.
MEM = 'gambatte-memory.cpp'
edit(MEM, '\t\t\t\tcart_.vrambankptr()[p] = data;\n',
     '\t\t\t\tcart_.vrambankptr()[p] = data;\n' + T.format('\t\t\t\trtStore(cart_.vrambankptr() + p, data);'))
# This store is the body of an unbraced else: brace it so the hook stays inside.
edit(MEM, '\t\t} else\n\t\t\tcart_.wramdata(p >> 12 & 1)[p & 0xFFF] = data;\n',
     '\t\t} else {\n\t\t\tcart_.wramdata(p >> 12 & 1)[p & 0xFFF] = data;\n'
     + T.format('\t\t\trtStore(cart_.wramdata(p >> 12 & 1) + (p & 0xFFF), data);') + '\t\t}\n')
edit(MEM, '\t\t\t\tlcd_.oamChange(cc);\n\t\t\t\tioamhram_[p - 0xFE00] = data;\n',
     '\t\t\t\tlcd_.oamChange(cc);\n\t\t\t\tioamhram_[p - 0xFE00] = data;\n' + T.format('\t\t\t\trtStore(ioamhram_ + (p - 0xFE00), data);'))
edit(MEM, '\t} else\n\t\tioamhram_[p - 0xFE00] = data;\n}',
     '\t} else {\n\t\tioamhram_[p - 0xFE00] = data;\n' + T.format('\t\trtStore(ioamhram_ + (p - 0xFE00), data);') + '\t}\n}')
# OAM DMA keeps its source tag.
edit(MEM, '\t\t\tif (oamDmaSrc) ioamhram_[oamDmaPos_] = oamDmaSrc[oamDmaPos_];\n',
     '\t\t\tif (oamDmaSrc) {\n\t\t\t\tioamhram_[oamDmaPos_] = oamDmaSrc[oamDmaPos_];\n'
     + T.format('\t\t\t\trt_write_tag(rtOam_, oamDmaPos_, rtTagOfPtr(oamDmaSrc + oamDmaPos_));') + '\t\t\t}\n')
# Palettes.
for reg, idx in (('dmgBgPaletteChange', 0), ('dmgSpPalette1Change', 1), ('dmgSpPalette2Change', 2)):
    edit(MEM, f'\t\t\tlcd_.{reg}(data, cc);\n',
         f'\t\t\tlcd_.{reg}(data, cc);\n' + T.format(f'\t\trt_write(rtDmg_, {idx}, data);'))
edit(MEM, '\t\t\tlcd_.cgbBgColorChange(index, data, cc);\n',
     '\t\t\tlcd_.cgbBgColorChange(index, data, cc);\n' + T.format('\t\t\trtPalette(index, data);'))
edit(MEM, '\t\t\tlcd_.cgbSpColorChange(index, data, cc);\n',
     '\t\t\tlcd_.cgbSpColorChange(index, data, cc);\n' + T.format('\t\t\trtPalette(0x40 + index, data);'))
# The LCD's palette memory, one byte at a time, as FF69/FF6B address it.
edit('video.h', '      void setDmgMode(bool mode) { ppu_.setDmgMode(mode); }\n',
     T.format('      /* Byte `index` of CGB palette memory (0-0x3F BG, 0x40-0x7F OBJ) as the picture uses it now.\n'
              '       * In DMG mode on CGB hardware bgpData_[0] and objpData_[0..1] hold BGP/OBP0/OBP1 and the\n'
              '       * colors live in dmgColorsGBC_ (BG palette 0, OBJ palettes 0 and 1). */\n'
              '      unsigned rtCgbPaletteByte(unsigned index) const {\n'
              '         if (!ppu_.cgb()) return 0;\n'
              '         if (ppu_.inDmgMode()) {\n'
              '            if (index < 8) return dmgColorsGBC_[index];\n'
              '            if (index - 0x40u < 16) return dmgColorsGBC_[8 + (index - 0x40u)];\n'
              '         }\n'
              '         return index < 0x40 ? bgpData_[index] : objpData_[(index - 0x40u) & 0x3F];\n'
              '      }')
     + '      void setDmgMode(bool mode) { ppu_.setDmgMode(mode); }\n')
# Every way the whole state is replaced (GB::load, GB::reset, GB::loadState) ends in Memory::loadState.
edit(MEM, '\tif (!isCgb())\n\t\tstd::memset(cart_.vramdata() + 0x2000, 0, 0x2000);\n}\n',
     '\tif (!isCgb())\n\t\tstd::memset(cart_.vramdata() + 0x2000, 0, 0x2000);\n' + T.format('\trtStateReplaced();') + '}\n')
# The frontend can only look between calls: bring the palette view up to date when a run ends.
edit('gambatte.cpp', '\tconst long cyclesSinceBlit = p_->cpu.runFor(samples * 2);\n',
     '\tconst long cyclesSinceBlit = p_->cpu.runFor(samples * 2);\n' + T.format('\tp_->cpu.mem_.rtSync();'))
# GDMA/HDMA: push the source byte so the VRAM store matches it.
edit(MEM, '\t\t\t\t\tnontrivial_write(0x8000 | (dmaDest++ & 0x1FFF), data, cc);\n',
     T.format('\t\t\t\t\trtRead(src, data);') + '\t\t\t\t\tnontrivial_write(0x8000 | (dmaDest++ & 0x1FFF), data, cc);\n')

# Register domains after every successful ROM load; this unit owns the state.
p = root / MEM
t = p.read_text(encoding='utf-8', newline='')
found = re.findall(r'int Memory::loadROM\(.*?\n\}\r?\n', t, re.S)
if len(found) != 1:
    raise SystemExit(f'{MEM}: expected 1 Memory::loadROM, found {len(found)}')
body = found[0]
last = body.rfind('return 0;')
if last < 0:
    raise SystemExit('loadROM has no success return')
nl = '\r\n' if '\r\n' in t else '\n'
t = t.replace(body, body[:last] + T.format('   rtInit();').replace('\n', nl) + '   ' + body[last:])
t = T.format('#define ROMANCER_TRACE_IMPLEMENTATION\n#include "romancer_trace.h"').replace('\n', nl) + t
p.write_text(t, encoding='utf-8', newline='')

# CPU: data reads, opcode fetches, operand fetches.
CPU = 'cpu.cpp'
edit(CPU, '#define READ(dest, addr) do { (dest) = mem_.read(addr, cycleCounter); cycleCounter += 4; } while (0)',
     '#ifdef ROMANCER_TRACE\n#define RT_R(a, v) mem_.rtRead((a), (v))\n#define RT_F(a, v, o) mem_.rtFetch((a), (v), (o))\n'
     '#else\n#define RT_R(a, v) ((void)0)\n#define RT_F(a, v, o) ((void)0)\n#endif\n'
     '#define READ(dest, addr) do { unsigned rt_a_ = (addr); (dest) = mem_.read(rt_a_, cycleCounter); RT_R(rt_a_, (dest)); cycleCounter += 4; } while (0)')
edit(CPU, '#define PC_READ(dest) do { (dest) = mem_.read(pc, cycleCounter); pc = (pc + 1) & 0xFFFF; cycleCounter += 4; } while (0)',
     '#define PC_READ(dest) do { (dest) = mem_.read(pc, cycleCounter); RT_F(pc, (dest), false); pc = (pc + 1) & 0xFFFF; cycleCounter += 4; } while (0)\n'
     '#define OP_READ(dest) do { (dest) = mem_.read(pc, cycleCounter); RT_F(pc, (dest), true); pc = (pc + 1) & 0xFFFF; cycleCounter += 4; } while (0)')
edit(CPU, '#define FF_READ(dest, addr) do { (dest) = mem_.ff_read(addr, cycleCounter); cycleCounter += 4; } while (0)',
     '#define FF_READ(dest, addr) do { unsigned rt_a_ = 0xFF00 | ((addr) & 0xFF); (dest) = mem_.ff_read((addr), cycleCounter); RT_R(rt_a_, (dest)); cycleCounter += 4; } while (0)\n'
     '#define CB_READ(dest) do { (dest) = mem_.read(pc, cycleCounter); pc = (pc + 1) & 0xFFFF; cycleCounter += 4; } while (0)')
# Main opcode fetch starts an instruction; the CB-prefix byte is part of the opcode, never data.
edit(CPU, '\n\t\t\tPC_READ(opcode);\n', '\n\t\t\tOP_READ(opcode);\n')
edit(CPU, '\n\t\t\t\tPC_READ(opcode);\n', '\n\t\t\t\tCB_READ(opcode);\n')
p = Path(sys.argv[1]) / 'libgambatte' / 'libretro' / 'link.T'
t = p.read_text(encoding='utf-8', newline='')
if 'romancer_trace_' not in t:
    if t.count('global: retro_*;') != 1:
        raise SystemExit('link.T: expected one "global: retro_*;"')
    p.write_text(t.replace('global: retro_*;', 'global: retro_*; romancer_trace_*;'), encoding='utf-8', newline='')
print('gambatte hooks applied')
