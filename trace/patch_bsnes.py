"""Apply ROMancer provenance hooks to a bsnes-mercury source tree (argv[1]).

Hooks cover the S-CPU (65816) bus, general DMA / HDMA and the balanced-profile
PPU ports ($2104 OAM, $2118/$2119 VRAM, $2122 CGRAM) plus the $2180 WRAM port.
Domains: palette (CGRAM 512), vram (64 KB), oam (544), wram (128 KB); all use
the core's own arrays as `data`. Everything is under ROMANCER_TRACE, so the
untraced build is unchanged. Only PROFILE=balanced (sfc/alt/ppu-balanced) is
hooked; the accuracy/performance PPUs are not.

Coprocessor boards (SA-1, SuperFX, S-DD1, SPC7110, Cx4) serve the S-CPU's ROM
reads through the chip's own bus handler instead of a plain mapping. Those
reads are followed through MappedRAM::read: the byte the handler returned is
tagged with its offset in the chip's ROM buffer when the value matches, and as
derived when the handler changed it on the way (S-DD1 / SPC7110 decompression).

TODO: what the coprocessor itself computes is still not traced: the SA-1 and
SuperFX CPUs' own ROM reads carry no tag, and SA-1 I-RAM / BW-RAM and SuperFX
RAM are not domains, so data they prepare reaches the S-CPU untagged.
DSP-1..4 / ST010 games work, since the S-CPU reads their ROM through the
normal cartridge mapping.
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])
# --chip-readers-only upgrades a tree patched by an earlier version of this script.
skip = '--chip-readers-only' in sys.argv


def edit(rel, old, new, count=1):
    if skip:
        return
    p = root / rel
    t = p.read_text(encoding='utf-8', newline='')
    if '\r\n' in t:
        old, new = old.replace('\n', '\r\n'), new.replace('\n', '\r\n')
    if t.count(old) != count:
        raise SystemExit(f'{rel}: expected {count} of {old!r}, found {t.count(old)}')
    p.write_text(t.replace(old, new), encoding='utf-8', newline='')


T = '#ifdef ROMANCER_TRACE\n{}\n#endif\n'

# ---- shared state: sfc/sfc.hpp ------------------------------------------
RTRACE = r'''#ifdef ROMANCER_TRACE
  #define RT_SFC(x) x
  /* Tracing state shared by the CPU, DMA and PPU hooks (sfc/memory/memory.cpp owns it). */
  struct RTrace {
    rt_domain *pal = nullptr, *vram = nullptr, *oam = nullptr, *wram = nullptr;
    bool dma = false;          /* a DMA/HDMA write is in progress */
    uint32_t dma_tag = 0;      /* tag of the byte that DMA write carries */
    uint32_t pending = 0;      /* tag for the next OAM/CGRAM store */
    uint32_t oam_latch = 0, cg_latch = 0;  /* tags of the latched low bytes */
    enum { CELLS = 512 + 0x10000 + 544 + 0x20000 };
    uint32_t tag[CELLS], pc[CELLS];
    void init();
    /* Tag for a value arriving at a PPU / WRAM port now. */
    inline uint32_t src(uint8 v) const {
      if(!romancer_trace.enabled) return RT_NONE;
      return dma ? dma_tag : rt_tag_for(v);
    }
    /* The stored value differs from the source byte (masked): keep the offset, drop exactness. */
    static inline uint32_t derive(uint32_t t) {
      unsigned k = RT_KIND(t);
      return (k == RT_ROM || k == RT_IMM) ? (RT_TAG(RT_DERIVED, t) | (t & RT_WEAK)) : t;
    }
    inline void store(rt_domain *d, unsigned i, uint32_t t) {
      if(!romancer_trace.enabled || !d || i >= d->size) return;
      d->tag[i] = t;
      d->pc[i] = dma ? RT_PC_NONE : romancer_trace.pc;
      romancer_trace.writes++;
    }
    inline uint32_t rom_offset(const uint8 *p) const;  /* RT_PC_NONE unless p is in cartridge ROM */
    inline int wram_index(const uint8 *p) const;       /* -1 unless p is in S-CPU WRAM */
    inline uint32_t tag_of(const uint8 *p) const;      /* RT_ROM, the WRAM tag, or RT_NONE */
  };
  extern RTrace rtrace;
#else
  #define RT_SFC(x)
#endif
'''
edit('sfc/sfc.hpp', '#include <libco/libco.h>\n',
     '#include <libco/libco.h>\n' + T.format('#include "romancer_trace.h"'))
edit('sfc/sfc.hpp', '  #include <sfc/memory/memory.hpp>\n', RTRACE + '  #include <sfc/memory/memory.hpp>\n')
edit('sfc/sfc.hpp', '  #include <sfc/ppu/counter/counter-inline.hpp>\n', '''  #include <sfc/ppu/counter/counter-inline.hpp>
#ifdef ROMANCER_TRACE
  inline uint32_t RTrace::rom_offset(const uint8 *p) const {
    const uint8 *b = cartridge.rom.data();
    return (p && b && p >= b && p < b + cartridge.rom.size()) ? (uint32_t)(p - b) : RT_PC_NONE;
  }
  inline int RTrace::wram_index(const uint8 *p) const {
    return (p && p >= cpu.wram && p < cpu.wram + sizeof cpu.wram) ? (int)(p - cpu.wram) : -1;
  }
  inline uint32_t RTrace::tag_of(const uint8 *p) const {
    uint32_t r = rom_offset(p);
    if(r != RT_PC_NONE) return RT_TAG(RT_ROM, r);
    int w = wram_index(p);
    return w >= 0 ? rt_tag_at(wram, w) : RT_NONE;
  }
#endif
''')

# ---- bus: remember each mapping's backing buffer --------------------------
edit('sfc/memory/memory.hpp', '  uint8 lookup[16 * 1024 * 1024];\n', '''#ifdef ROMANCER_TRACE
  uint8* rt_ptr[256];  /* backing buffer of each reader id (fastptr), or NULL */
  /* Host byte behind a bus address when it is plain memory (ROM, RAM, WRAM). */
  inline const uint8* rt_resolve(unsigned addr) const {
    addr &= 0xffffff;
    if(fast_read[addr >> fast_page_size_bits]) return fast_read[addr >> fast_page_size_bits] + addr;
    const uint8* b = rt_ptr[lookup[addr]];
    return b ? b + target[addr] : nullptr;
  }
#endif
  uint8 lookup[16 * 1024 * 1024];
''')
# Function-mapped regions (coprocessor handlers) leave fastptr uninitialized: trust it only for fast mappings.
RT_PTR = '  rt_ptr[id] = (fastmode != Cartridge::Mapping::fastmode_slow) ? fastptr : nullptr;'
edit('sfc/memory/memory.cpp', '  unsigned id = idcount++;\n',
     '  unsigned id = idcount++;\n' + T.format(RT_PTR))
edit('sfc/memory/memory.cpp', '#include <sfc/sfc.hpp>\n',
     T.format('#define ROMANCER_TRACE_IMPLEMENTATION') + '#include <sfc/sfc.hpp>\n')
edit('sfc/memory/memory.cpp', 'Bus bus;\n', '''Bus bus;
#ifdef ROMANCER_TRACE
RTrace rtrace;
void RTrace::init() {
  uint32_t *t = tag, *c = pc;
  pal = rt_register("palette", 512, t, c, ppu.cgram); t += 512; c += 512;
  vram = rt_register("vram", 0x10000, t, c, ppu.vram); t += 0x10000; c += 0x10000;
  oam = rt_register("oam", 544, t, c, ppu.oam); t += 544; c += 544;
  wram = rt_register("wram", 0x20000, t, c, cpu.wram);
  dma = false;
}
#endif
''')

# Register domains whenever the system powers on (every successful load).
edit('sfc/system/system.cpp', '  reset();\n}\n\nvoid System::reset() {\n',
     '  reset();\n' + T.format('  rtrace.init();') + '}\n\nvoid System::reset() {\n')

# ---- 65816: operand / opcode fetch flag -----------------------------------
edit('processor/r65816/r65816.hpp', '  regs_t regs;\n',
     '  regs_t regs;\n' + T.format('  unsigned rt_fetch = 0;  /* 1 = operand fetch, 3 = opcode fetch */'))
edit('processor/r65816/memory.hpp', '''alwaysinline uint8 op_readpc() {
  return op_read((regs.pc.b << 16) + regs.pc.w++);
}''', '''alwaysinline uint8 op_readpc() {
#ifdef ROMANCER_TRACE
  rt_fetch |= 1;
  uint8 rt_v = op_read((regs.pc.b << 16) + regs.pc.w++);
  rt_fetch = 0;
  return rt_v;
#else
  return op_read((regs.pc.b << 16) + regs.pc.w++);
#endif
}''')
edit('sfc/cpu/cpu.cpp', '  (this->*opcode_table[op_readpc()])();\n',
     T.format('  rt_fetch = 2;') + '  (this->*opcode_table[op_readpc()])();\n')

# ---- S-CPU bus reads / writes ---------------------------------------------
edit('sfc/cpu/cpu.hpp', 'privileged:\n', '''#ifdef ROMANCER_TRACE
  uint32_t rt_next_tag = 0, rt_pipe_tag = 0;  /* DMA source tags, following the write pipeline */
  void rtRead(unsigned addr, uint8 v);
  void rtWrite(unsigned addr, uint8 v);
  uint32_t rtDmaSource(unsigned addr);
#endif
privileged:
''')
edit('sfc/cpu/memory/memory.cpp', '  regs.mdr = bus.read(addr);\n',
     '  regs.mdr = bus.read(addr);\n' + T.format('  if(romancer_trace.enabled) rtRead(addr, regs.mdr);'))
edit('sfc/cpu/memory/memory.cpp', '  bus.write(addr, regs.mdr = data);\n',
     '  bus.write(addr, regs.mdr = data);\n' + T.format('  if(romancer_trace.enabled) rtWrite(addr, data);'))
edit('sfc/cpu/memory/memory.cpp', 'unsigned CPU::speed(unsigned addr) const {\n', '''#ifdef ROMANCER_TRACE
void CPU::rtRead(unsigned addr, uint8 v) {
  const uint8* p = bus.rt_resolve(addr);
  uint32_t rom = rtrace.rom_offset(p);
  if(rt_fetch & 2) { rt_instruction(rom); return; }
  if(rom != RT_PC_NONE) {
    if(rt_fetch) rt_read_imm(rom, v); else rt_read_rom(rom, v);
    return;
  }
  uint32_t t = rtrace.tag_of(p);
  if(!p && (addr & 0x40ffff) == 0x2180) t = rt_tag_at(rtrace.wram, (status.wram_addr - 1) & 0x1ffff);  //WMDATA read
  rt_read_tagged(t, v);
}

void CPU::rtWrite(unsigned addr, uint8 v) {
  int w = rtrace.wram_index(bus.rt_resolve(addr));
  if(w >= 0) ::rt_write(rtrace.wram, w, v);
}

uint32_t CPU::rtDmaSource(unsigned addr) {
  if(!romancer_trace.enabled || !dma_addr_valid(addr)) return RT_NONE;
  return rtrace.tag_of(bus.rt_resolve(addr));
}
#endif

unsigned CPU::speed(unsigned addr) const {
''')

# $2180 WMDATA writes (CPU or DMA) land in WRAM through the port.
edit('sfc/cpu/mmio/mmio.cpp', '  bus.write(0x7e0000 | status.wram_addr++, data);\n',
     T.format('  rtrace.store(rtrace.wram, status.wram_addr & 0x1ffff, rtrace.src(data));')
     + '  bus.write(0x7e0000 | status.wram_addr++, data);\n')

# ---- DMA / HDMA: carry each byte's source tag through the two-stage pipe ---
edit('sfc/cpu/dma/dma.cpp', '  if(pipe.valid) bus.write(pipe.addr, pipe.data);\n', '''#ifdef ROMANCER_TRACE
  if(pipe.valid) {
    rtrace.dma = true;
    rtrace.dma_tag = rt_pipe_tag;
    bus.write(pipe.addr, pipe.data);  //A->B: PPU/WMDATA hooks pick up dma_tag
    int w = rtrace.wram_index(bus.rt_resolve(pipe.addr));  //B->A into WRAM
    if(w >= 0) rtrace.store(rtrace.wram, w, rt_pipe_tag);
    rtrace.dma = false;
  }
  rt_pipe_tag = rt_next_tag;
  rt_next_tag = RT_NONE;
#else
  if(pipe.valid) bus.write(pipe.addr, pipe.data);
#endif
''')
edit('sfc/cpu/dma/dma.cpp', '    regs.mdr = dma_read(abus);\n    dma_add_clocks(4);\n',
     '    regs.mdr = dma_read(abus);\n' + T.format('    rt_next_tag = rtDmaSource(abus);') + '    dma_add_clocks(4);\n')
edit('sfc/cpu/dma/dma.cpp', '    regs.mdr = dma_transfer_valid(bbus, abus) ? bus.read(0x2100 | bbus) : 0x00;\n',
     T.format('    rt_next_tag = (romancer_trace.enabled && bbus == 0x80) ? rt_tag_at(rtrace.wram, status.wram_addr & 0x1ffff) : RT_NONE;')
     + '    regs.mdr = dma_transfer_valid(bbus, abus) ? bus.read(0x2100 | bbus) : 0x00;\n')

# ---- PPU (balanced) stores ------------------------------------------------
PM = 'sfc/alt/ppu-balanced/memory/memory.cpp'
edit(PM, 'vram[addr] = data;\n', 'vram[addr] = data; RT_SFC(rtrace.store(rtrace.vram, addr, rtrace.src(data)));\n', 4)
edit(PM, 'vram[addr] = cpu.regs.mdr;\n',
     'vram[addr] = cpu.regs.mdr; RT_SFC(rtrace.store(rtrace.vram, addr, rtrace.src(cpu.regs.mdr)));\n')
edit(PM, 'oam[addr] = data;\n', 'oam[addr] = data; RT_SFC(rtrace.store(rtrace.oam, addr, rtrace.pending));\n', 2)
edit(PM, 'oam[regs.ioamaddr] = data;\n',
     'oam[regs.ioamaddr] = data; RT_SFC(rtrace.store(rtrace.oam, regs.ioamaddr, rtrace.pending));\n')
edit(PM, 'cgram[addr] = data;\n', 'cgram[addr] = data; RT_SFC(rtrace.store(rtrace.pal, addr, rtrace.pending));\n', 2)
edit(PM, 'cgram[regs.icgramaddr] = data & 0x7f;\n',
     'cgram[regs.icgramaddr] = data & 0x7f; RT_SFC(rtrace.store(rtrace.pal, regs.icgramaddr, RTrace::derive(rtrace.pending)));\n')

# Port latches: the low byte is stored when the high byte arrives, with the tag it had when latched.
MM = 'sfc/alt/ppu-balanced/mmio/mmio.cpp'
edit(MM, '''void PPU::mmio_w2104(uint8 data) {
  if((regs.oam_addr & 1) == 0) regs.oam_latchdata = data;

  if(regs.oam_addr & 0x0200) {
    oam_mmio_write(regs.oam_addr, data);
  } else if((regs.oam_addr & 1) == 1) {
    oam_mmio_write((regs.oam_addr & ~1) + 0, regs.oam_latchdata);
    oam_mmio_write((regs.oam_addr & ~1) + 1, data);
  }
''', '''void PPU::mmio_w2104(uint8 data) {
  RT_SFC(uint32_t rt_t = rtrace.src(data); if((regs.oam_addr & 1) == 0) rtrace.oam_latch = rt_t;)
  if((regs.oam_addr & 1) == 0) regs.oam_latchdata = data;

  if(regs.oam_addr & 0x0200) {
    RT_SFC(rtrace.pending = rt_t;)
    oam_mmio_write(regs.oam_addr, data);
  } else if((regs.oam_addr & 1) == 1) {
    RT_SFC(rtrace.pending = rtrace.oam_latch;)
    oam_mmio_write((regs.oam_addr & ~1) + 0, regs.oam_latchdata);
    RT_SFC(rtrace.pending = rt_t;)
    oam_mmio_write((regs.oam_addr & ~1) + 1, data);
  }
''')
edit(MM, '''void PPU::mmio_w2122(uint8 value) {
  if(!(regs.cgram_addr & 1)) {
    regs.cgram_latchdata = value;
  } else {
    cgram_mmio_write((regs.cgram_addr & 0x01fe),     regs.cgram_latchdata);
    cgram_mmio_write((regs.cgram_addr & 0x01fe) + 1, value & 0x7f);
  }
''', '''void PPU::mmio_w2122(uint8 value) {
  RT_SFC(uint32_t rt_t = rtrace.src(value);)
  if(!(regs.cgram_addr & 1)) {
    regs.cgram_latchdata = value;
    RT_SFC(rtrace.cg_latch = rt_t;)
  } else {
    RT_SFC(rtrace.pending = rtrace.cg_latch;)
    cgram_mmio_write((regs.cgram_addr & 0x01fe),     regs.cgram_latchdata);
    RT_SFC(rtrace.pending = (value & 0x80) ? RTrace::derive(rt_t) : rt_t;)  //bit 15 is dropped
    cgram_mmio_write((regs.cgram_addr & 0x01fe) + 1, value & 0x7f);
  }
''')

# ---- coprocessor boards: follow S-CPU ROM reads through the chip's handler ----
skip = False
if '--chip-readers-only' in sys.argv:
    edit('sfc/memory/memory.cpp', '  rt_ptr[id] = fastptr;', RT_PTR)
edit('sfc/sfc.hpp', '    bool dma = false;         /* a DMA/HDMA write is in progress */\n',
     '    bool dma = false;          /* a DMA/HDMA write is in progress */\n'
     '    const uint8 *last_mapped = nullptr;  /* byte last read through MappedRAM::read (chip ROM handlers) */\n')
edit('sfc/memory/memory-inline.hpp', 'uint8 MappedRAM::read(unsigned addr) { return data_[addr]; }\n',
     'uint8 MappedRAM::read(unsigned addr) { RT_SFC(rtrace.last_mapped = data_ + addr;) return data_[addr]; }\n')
edit('sfc/sfc.hpp', '''    const uint8 *b = cartridge.rom.data();
    return (p && b && p >= b && p < b + cartridge.rom.size()) ? (uint32_t)(p - b) : RT_PC_NONE;
''', '''    if(!p) return RT_PC_NONE;
    /* Coprocessor boards keep the game ROM in the chip's own buffer. */
    MappedRAM* roms[] = {&cartridge.rom, &sa1.rom, &superfx.rom, &sdd1.rom, &hitachidsp.rom, &spc7110.prom};
    for(MappedRAM* m : roms) {
      const uint8 *b = m->data();
      if(b && p >= b && p < b + m->size()) return (uint32_t)(p - b);
    }
    const uint8 *d = spc7110.drom.data();  //data ROM follows the program ROM in the file
    if(d && p >= d && p < d + spc7110.drom.size()) return (uint32_t)(spc7110.prom.size() + (p - d));
    return RT_PC_NONE;
''')
edit('sfc/cpu/memory/memory.cpp', '  regs.mdr = bus.read(addr);\n',
     '  RT_SFC(rtrace.last_mapped = nullptr;)\n  regs.mdr = bus.read(addr);\n')
edit('sfc/cpu/memory/memory.cpp', '''  const uint8* p = bus.rt_resolve(addr);
  uint32_t rom = rtrace.rom_offset(p);
''', '''  const uint8* p = bus.rt_resolve(addr);
  if(!p && rtrace.last_mapped) {  //served by a coprocessor's bus handler
    uint32_t chip = rtrace.rom_offset(rtrace.last_mapped);
    if(chip != RT_PC_NONE) {
      if(*rtrace.last_mapped == v) p = rtrace.last_mapped;
      else if(!(rt_fetch & 2)) { rt_read_tagged(RT_TAG(RT_DERIVED, chip), v); return; }  //decompressed on the way
    }
  }
  uint32_t rom = rtrace.rom_offset(p);
''')
edit('sfc/cpu/memory/memory.cpp', '  return rtrace.tag_of(bus.rt_resolve(addr));\n', '''  const uint8* p = bus.rt_resolve(addr);
  if(!p && rtrace.last_mapped) {  //served by a coprocessor's bus handler
    uint32_t chip = rtrace.rom_offset(rtrace.last_mapped);
    if(chip != RT_PC_NONE) return RT_TAG(*rtrace.last_mapped == regs.mdr ? RT_ROM : RT_DERIVED, chip);
  }
  return rtrace.tag_of(p);
''')
edit('sfc/cpu/dma/dma.cpp', '  if(dma_addr_valid(abus) == false) return 0x00;\n  return bus.read(abus);\n',
     '  RT_SFC(rtrace.last_mapped = nullptr;)\n  if(dma_addr_valid(abus) == false) return 0x00;\n  return bus.read(abus);\n')

# ---- export the tracing API -------------------------------------------------
p = root / 'target-libretro' / 'link.T'
t = p.read_text(encoding='utf-8', newline='')
if 'romancer_trace_' not in t:
    if 'global: retro_*;' not in t:
        raise SystemExit('link.T: no "global: retro_*;"')
    p.write_text(t.replace('global: retro_*;', 'global: retro_*; romancer_trace_*;'), encoding='utf-8', newline='')
print('bsnes-mercury hooks applied')
