"""Apply ROMancer provenance hooks to a BlastEm source tree (argv[1]).

Genesis/Mega Drive (68000) and Master System / Game Gear (Z80, Mode 4).
The hooks sit in the generated interpreter cores (m68k.cpu / z80.cpu via
cpu_dsl.py and their m68k_util.c / z80_util.c helpers), so a tracing build is
always NEW_CORE=1; the Makefile switches that on when -DROMANCER_TRACE is in
ZCC_EXTRA, CFLAGS or CC. Every C hook is under #ifdef ROMANCER_TRACE; the two
.cpu files gain ccall lines whose targets are empty macros in a normal build.

Build with `make -f Makefile.libretro ABI=generic NEW_CORE=1 ...`: on x86 the
32X SH-2 otherwise wants the JIT helpers that NEW_CORE leaves out, and the
link fails. See trace-win/build_blastem.sh.

Domains, Genesis: palette (CRAM, 128 bytes, big-endian words as stored), vram
(64 KB, VRAM byte order), vsram (80), wram (64 KB at $FF0000, 68K byte order),
z80ram (8 KB). SMS: palette (32 bytes, bits 0-5 of each byte written; Game
Gear 64), vram (16 KB, by VDP address), wram (8 KB). Every domain's contents
are read from emulator state, so they are right after a savestate load too.
ROM tags are file offsets of the exact byte (BlastEm keeps a Genesis ROM as
host-order words; the tag is the big-endian file position).

68000: data reads, extension-word immediates (the opcode word is dropped from
the value ring at dispatch), byte and word writes. A word write takes the
tags of a word that was read as a word; a zero/sign-extended byte keeps a
just-read byte's tag; any other word is derived. Z80: the same per byte,
through the Sega mapper or the Genesis bank register.

The VDP FIFO carries each entry's two byte tags and the writing instruction's
ROM offset, so tags land where the byte physically does when the entry drains
(auto-increment, byte swap, Mode 4 address map). 68K->VDP DMA tags each word
from its source address (ROM offsets, or the tags the RAM bytes carry); fill
is derived; copy propagates VRAM tags. The 68K and the Z80 keep separate value
rings (swapped around z80_run), since the 68K syncs the Z80 in the middle of
its own VDP port writes.

BlastEm cannot save or load a state before the first retro_run(); ROMancer's
boot checkpoint and checkpoint replays need both, so the tracing build does
the machine reset on demand (rt_prestart). A run that makes no savestate call
before its first frame executes exactly the stock code path.
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])
if (root / 'rt_blastem.h').exists() or 'ROMANCER_TRACE' in (root / 'vdp.c').read_text(encoding='utf-8', errors='replace'):
    raise SystemExit('blastem: this tree is already patched; restore the pristine source first')


def edit(rel, old, new, count=1):
    p = root / rel
    t = p.read_text(encoding='utf-8', newline='')
    if '\r\n' in t:
        old, new = old.replace('\n', '\r\n'), new.replace('\n', '\r\n')
    if t.count(old) != count:
        raise SystemExit(f'{rel}: expected {count} of {old!r}, found {t.count(old)}')
    p.write_text(t.replace(old, new), encoding='utf-8', newline='')


def after(rel, anchor, hook, count=1):
    edit(rel, anchor, anchor + T.format(hook), count)


def before(rel, anchor, hook, count=1):
    edit(rel, anchor, T.format(hook) + anchor, count)


T = '#ifdef ROMANCER_TRACE\n{}\n#endif\n'

GLUE = r'''/* ROMancer provenance tracing glue for BlastEm; see romancer_trace.h. */
#ifndef RT_BLASTEM_H
#define RT_BLASTEM_H
#ifdef ROMANCER_TRACE
#include "romancer_trace.h"

enum { RT_SYS_NONE, RT_SYS_GEN, RT_SYS_SMS };
enum { RT_LOC_NONE, RT_LOC_ROM, RT_LOC_DOM };

typedef struct {
	uint8_t value[RT_RING];
	uint32_t tag[RT_RING];
	unsigned head;
	uint32_t last_rom, pc;
} rt_cpu_ring;

typedef struct {
	int sys;
	void *vdp;                /* the emulated VDP (not a render-thread copy) */
	rt_domain *pal, *vram, *vsram, *wram, *zram;
	uint32_t copy_tag;        /* VRAM copy DMA byte in flight */
	uint32_t latch_tag, latch_pc; /* Game Gear CRAM latch */
	unsigned fetch_slot[2];   /* ring slots holding the last 68K prefetch */
	uint32_t fetch_tag[2];
	int fetch_live;           /* that prefetch has not been classified yet */
	unsigned fetch_mask;      /* 68K ring slots holding operand bytes it fetched */
	int cpu;                  /* whose ring is live: 0 main CPU, 1 Genesis Z80 */
	rt_cpu_ring saved[2];
} rt_blastem_state;

extern rt_blastem_state rt_bl;
/* Classify a CPU address: ROM (*index = file offset), a traced domain, or neither. */
int rt_locate68(uint32_t address, rt_domain **d, uint32_t *index);
int rt_locatez80(uint32_t address, rt_domain **d, uint32_t *index);

static inline void rt_put(rt_domain *d, uint32_t i, uint32_t tag, uint32_t pc) {
	if (!romancer_trace.enabled || !d || i >= d->size) return;
	d->tag[i] = tag;
	d->pc[i] = pc;
	romancer_trace.writes++;
}

static inline uint32_t rt_derive(uint32_t tag) {
	if (RT_KIND(tag) == RT_NONE) return RT_NONE;
	return RT_TAG(RT_DERIVED, tag) | (tag & RT_WEAK);
}

static inline uint32_t rt_weaken(uint32_t tag, uint8_t value) {
	uint32_t t = tag & ~RT_WEAK;
	if (value == 0x00 || value == 0xFF || (tag & RT_WEAK)) t |= RT_WEAK;
	return t;
}

/* rt_tag_for() restricted to what a 68000 byte store can be a copy of: a data
 * byte, or the low (odd) byte of an extension word - `move.b #imm` keeps its
 * operand there. The high byte of an extension word is mostly address bytes
 * ($00FF..., $00C0...); tagging a stored 00 with one invites an edit of code.
 * With data_only, operands are not considered at all. Only operands the CPU
 * fetched itself count here (fetch_mask); an operand's tag that travelled
 * through RAM belongs to a data byte like any other. */
static inline uint32_t rt_tag_for68(uint8_t value, int data_only) {
	rt_state *s = &romancer_trace;
	unsigned i, k;
	uint32_t tag;
	for (k = 0; k < RT_RING; k++) {
		i = (s->ring_head + RT_RING - k) % RT_RING;
		tag = s->ring_tag[i];
		if (s->ring_value[i] != value || tag == RT_NONE) continue;
		if ((rt_bl.fetch_mask >> i & 1) && (data_only || !(tag & 1))) continue;
		return rt_weaken(tag, value);
	}
	return s->last_rom ? RT_TAG(RT_DERIVED, s->last_rom) : RT_NONE;
}

/* The tag of `value` if it is one of the two most recent reads. Operands do
 * not count: an immediate that is stored is found as a whole word, and a
 * masked value that happens to equal its mask (andi #$0F) is not a copy. */
static inline void rt_tag_recent(uint8_t value, uint32_t *tag) {
	rt_state *s = &romancer_trace;
	unsigned k, i;
	for (k = 0; k < 2; k++) {
		i = (s->ring_head + RT_RING - k) % RT_RING;
		if (s->ring_value[i] == value && s->ring_tag[i] != RT_NONE && !(rt_bl.fetch_mask >> i & 1)) {
			*tag = rt_weaken(s->ring_tag[i], value);
			return;
		}
	}
}

/* Tags for a big-endian word about to be written: prefer an adjacent (hi, lo)
 * pair in the ring, i.e. a word that was read as a word (an operand word is
 * one extension word, never the tail of one and the head of the next).
 * `dup`: the word is a byte the bus duplicated (a byte write to a VDP port). */
static inline void rt_tag_word(uint8_t hi, uint8_t lo, uint32_t *th, uint32_t *tl, int dup) {
	rt_state *s = &romancer_trace;
	unsigned k, i, j;
	for (k = 0; k + 1 < RT_RING; k++) {
		i = (s->ring_head + RT_RING - k) % RT_RING;
		j = (i + RT_RING - 1) % RT_RING;
		if (s->ring_value[i] == lo && s->ring_value[j] == hi
			&& s->ring_tag[i] != RT_NONE && s->ring_tag[j] != RT_NONE) {
			if ((RT_KIND(s->ring_tag[i]) == RT_IMM || RT_KIND(s->ring_tag[j]) == RT_IMM)
				&& ((s->ring_tag[j] & 1) || (s->ring_tag[i] & ~RT_WEAK) != (s->ring_tag[j] & ~RT_WEAK) + 1)) continue;
			*th = rt_weaken(s->ring_tag[j], hi);
			*tl = rt_weaken(s->ring_tag[i], lo);
			return;
		}
	}
	/* No such word. A zero/sign-extended or shifted byte keeps the source of a
	 * byte that was just read; any other word was computed, and matching its
	 * halves one by one against unrelated reads would only find coincidences. */
	if (dup && hi == lo) {
		*th = *tl = rt_tag_for68(lo, 0);
		return;
	}
	*th = *tl = s->last_rom ? RT_TAG(RT_DERIVED, s->last_rom) : RT_NONE;
	if (hi == 0x00 || hi == 0xFF) {
		*th = rt_tag_for68(hi, 1);
		if (lo == 0x00 || lo == 0xFF) *tl = rt_tag_for68(lo, 1); else rt_tag_recent(lo, tl);
	} else if (lo == 0x00 || lo == 0xFF) {
		*tl = rt_tag_for68(lo, 1);
		rt_tag_recent(hi, th);
	}
}

static inline void rt_cpu_read(int k, rt_domain *d, uint32_t i, uint8_t v, int fetch) {
	if (k == RT_LOC_ROM) {
		if (fetch) rt_read_imm(i, v); else rt_read_rom(i, v);
	} else {
		uint32_t t = k == RT_LOC_DOM ? rt_tag_at(d, i) : RT_NONE;
		/* A computed value is reported against the ROM byte its input came
		 * from, also when that input reached the CPU through RAM (a fade
		 * working on a RAM copy of the palette, say). */
		if (RT_KIND(t) == RT_ROM || RT_KIND(t) == RT_DERIVED) romancer_trace.last_rom = t & RT_OFFSET_MASK;
		rt_read_tagged(t, v);
	}
}

static inline void rt_m68k_read(uint32_t a, uint32_t v, int word, int fetch) {
	rt_domain *d = NULL;
	uint32_t i = 0;
	int k;
	if (!romancer_trace.enabled || !rt_bl.sys) return;
	a &= 0xFFFFFF;
	if (!word) {
		k = rt_locate68(a, &d, &i);
		rt_cpu_read(k, d, i, v, 0);
		rt_bl.fetch_mask &= ~(1u << romancer_trace.ring_head);
		return;
	}
	k = rt_locate68(a & ~1u, &d, &i);
	rt_cpu_read(k, d, i, v >> 8, fetch);
	rt_cpu_read(k, d, i + 1, v, fetch);
	rt_bl.fetch_mask &= ~(1u << romancer_trace.ring_head | 1u << (romancer_trace.ring_head + RT_RING - 1) % RT_RING);
	if (fetch) {
		unsigned h = romancer_trace.ring_head;
		rt_bl.fetch_mask |= 1u << h | 1u << (h + RT_RING - 1) % RT_RING;
		rt_bl.fetch_slot[0] = (h + RT_RING - 1) % RT_RING;
		rt_bl.fetch_slot[1] = h;
		rt_bl.fetch_tag[0] = romancer_trace.ring_tag[rt_bl.fetch_slot[0]];
		rt_bl.fetch_tag[1] = romancer_trace.ring_tag[h];
		rt_bl.fetch_live = 1;
	}
}

static inline void rt_m68k_write(uint32_t a, uint32_t v, int word) {
	rt_domain *d = NULL;
	uint32_t i = 0, th, tl;
	if (!romancer_trace.enabled || !rt_bl.sys) return;
	a &= 0xFFFFFF;
	if (rt_locate68(word ? a & ~1u : a, &d, &i) != RT_LOC_DOM) return;
	if (!word) {
		rt_put(d, i, rt_tag_for68(v, 0), romancer_trace.pc);
	} else if (d == rt_bl.zram) {
		rt_write(d, i, v >> 8);   /* the Z80 bus only takes the high byte */
	} else {
		rt_tag_word(v >> 8, v, &th, &tl, 0);
		rt_put(d, i, th, romancer_trace.pc);
		rt_put(d, i + 1, tl, romancer_trace.pc);
	}
}

/* The opcode word of the instruction being dispatched is never data: drop it
 * from the ring (it was the last prefetch), so opcodes do not use up history. */
static inline void rt_fetch_clear(void) {
	rt_state *s = &romancer_trace;
	int n;
	if (!rt_bl.fetch_live) return;
	rt_bl.fetch_live = 0;
	for (n = 0; n < 2; n++)
		if (s->ring_tag[rt_bl.fetch_slot[n]] == rt_bl.fetch_tag[n])
			s->ring_tag[rt_bl.fetch_slot[n]] = RT_NONE;
	if (s->ring_head == rt_bl.fetch_slot[1]) s->ring_head = (s->ring_head + RT_RING - 2) % RT_RING;
}

static inline void rt_z80_read(uint32_t a, uint8_t v, int fetch) {
	rt_domain *d = NULL;
	uint32_t i = 0;
	int k;
	if (!romancer_trace.enabled || !rt_bl.sys) return;
	k = rt_locatez80(a & 0xFFFF, &d, &i);   /* its own statement: it fills in d and i */
	rt_cpu_read(k, d, i, v, fetch);
}

static inline void rt_z80_write(uint32_t a, uint8_t v) {
	rt_domain *d = NULL;
	uint32_t i = 0;
	if (!romancer_trace.enabled || !rt_bl.sys) return;
	if (rt_locatez80(a & 0xFFFF, &d, &i) == RT_LOC_DOM) rt_write(d, i, v);
}

/* Make `cpu`'s value ring the live one. */
static inline void rt_ring_swap(int cpu) {
	rt_state *s = &romancer_trace;
	rt_cpu_ring *o, *n;
	if (rt_bl.cpu == cpu) return;
	o = &rt_bl.saved[rt_bl.cpu];
	n = &rt_bl.saved[cpu];
	memcpy(o->value, s->ring_value, sizeof o->value);
	memcpy(o->tag, s->ring_tag, sizeof o->tag);
	o->head = s->ring_head; o->last_rom = s->last_rom; o->pc = s->pc;
	memcpy(s->ring_value, n->value, sizeof n->value);
	memcpy(s->ring_tag, n->tag, sizeof n->tag);
	s->ring_head = n->head; s->last_rom = n->last_rom; s->pc = n->pc;
	rt_bl.cpu = cpu;
}
#endif
#endif
'''
(root / 'rt_blastem.h').write_text(GLUE, encoding='utf-8', newline='\n')

# ---- build: tracing needs the generated interpreter cores; export the API.
edit('Makefile', 'TRANSOBJS=gen.o backend.o $(MEM) arena.o tern.o\n',
     '#ROMancer tracing builds hook the generated 68K/Z80 interpreters\n'
     'ifneq (,$(findstring -DROMANCER_TRACE,$(ZCC_EXTRA) $(CFLAGS) $(CC)))\nNEW_CORE:=1\nendif\n\n'
     'TRANSOBJS=gen.o backend.o $(MEM) arena.o tern.o\n')
edit('link.T', 'global: retro_*;', 'global: retro_*; romancer_trace_*;')

# ---- 68000: dispatch hook, data reads/writes, prefetch (opcode + extension words).
edit('m68k.cpu', 'm68k_run_op\n\tdispatch prefetch\n', 'm68k_run_op\n\tccall rt_m68k_op context\n\tdispatch prefetch\n')
M = 'm68k_util.c'
after(M, '#include <string.h>\n#ifdef DEBUG_DISASM\n#include "68kinst.h"\n#endif\n', r'''#include "rt_blastem.h"
/* Start of an instruction: its opcode word was the last prefetch. */
static inline void rt_m68k_op(m68k_context *context)
{
	rt_domain *d;
	uint32_t i;
	if (!romancer_trace.enabled || !rt_bl.sys) return;
	rt_fetch_clear();
	rt_instruction(rt_locate68((context->pc - 2) & 0xFFFFFF, &d, &i) == RT_LOC_ROM ? i : RT_PC_NONE);
}
#else
#define rt_m68k_op(context)''')
after(M, '\tcontext->scratch1 = context->read8[index](address, context, context->read8_data[index]);\n',
      '\trt_m68k_read(address, context->scratch1, 0, 0);')
edit(M, '\tcontext->scratch1 = context->read16[index](address, context, context->read16_data[index]);\n',
     T.format('\tuint32_t rt_fetch = context->scratch1 == context->pc;')
     + '\tcontext->scratch1 = context->read16[index](address, context, context->read16_data[index]);\n'
     + T.format('\trt_m68k_read(address, context->scratch1, 1, rt_fetch);'))
edit(M, '\tcontext->write8[index](address, context, context->scratch1, context->write8_data[index]);\n',
     T.format('\tuint32_t rt_v = context->scratch1;')
     + '\tcontext->write8[index](address, context, context->scratch1, context->write8_data[index]);\n'
     + T.format('\trt_m68k_write(address, rt_v, 0);'))
edit(M, '\tcontext->write16[index](address, context, context->scratch1, context->write16_data[index]);\n',
     T.format('\tuint32_t rt_v = context->scratch1;')
     + '\tcontext->write16[index](address, context, context->scratch1, context->write16_data[index]);\n'
     + T.format('\trt_m68k_write(address, rt_v, 1);'))

# ---- Z80: opcode fetch, instruction start, data reads/writes, I/O reads, ring swap.
edit('z80.cpu', '\tocall read_8\n\tpc += 1\n\t\nz80_run_op\n',
     '\tocall read_8\n\tpc += 1\n\tccall rt_z80_opfetch context\n\t\nz80_run_op\n')
edit('z80.cpu', '\tz80_op_fetch\n\tdispatch scratch1\n\nz80_interrupt\n',
     '\tz80_op_fetch\n\tccall rt_z80_insn context\n\tdispatch scratch1\n\nz80_interrupt\n')
Z = 'z80_util.c'
edit(Z, '#include <string.h>\n\nvoid z80_read_8(z80_context *context)\n', '#include <string.h>\n' + T.format(r'''#include "rt_blastem.h"
/* An opcode byte (main or prefixed) is never data. */
static inline void rt_z80_opfetch(z80_context *context)
{
	if (romancer_trace.enabled && rt_bl.sys) {
		romancer_trace.ring_tag[romancer_trace.ring_head] = RT_NONE;
		romancer_trace.ring_head = (romancer_trace.ring_head + RT_RING - 1) % RT_RING;
	}
}
static inline void rt_z80_insn(z80_context *context)
{
	rt_domain *d;
	uint32_t i;
	if (!romancer_trace.enabled || !rt_bl.sys) return;
	rt_instruction(rt_locatez80((context->pc - 1) & 0xFFFF, &d, &i) == RT_LOC_ROM ? i : RT_PC_NONE);
}
#else
#define rt_z80_opfetch(context)
#define rt_z80_insn(context)''') + '\nvoid z80_read_8(z80_context *context)\n')
edit(Z, 'void z80_read_8(z80_context *context)\n{\n\tcontext->cycles += 3 * context->opts->gen.clock_divider;\n',
     'void z80_read_8(z80_context *context)\n{\n' + T.format('\tuint32_t rt_a = context->scratch1;')
     + '\tcontext->cycles += 3 * context->opts->gen.clock_divider;\n')
edit(Z, '\t\tcontext->scratch1 = read_byte(context->scratch1, (void **)context->mem_pointers, &context->opts->gen, context);\n\t}\n}\n',
     '\t\tcontext->scratch1 = read_byte(context->scratch1, (void **)context->mem_pointers, &context->opts->gen, context);\n\t}\n'
     + T.format('\trt_z80_read(rt_a, context->scratch1, rt_a == context->pc);') + '}\n')
edit(Z, '\t\twrite_byte(context->scratch2, context->scratch1, (void **)context->mem_pointers, &context->opts->gen, context);\n\t}\n}\n',
     '\t\twrite_byte(context->scratch2, context->scratch1, (void **)context->mem_pointers, &context->opts->gen, context);\n\t}\n'
     + T.format('\trt_z80_write(context->scratch2, context->scratch1);') + '}\n')
after(Z, '\tcontext->cycles += 4 * context->opts->gen.clock_divider;\n\tcontext->scratch1 = read_byte(context->scratch1, (void **)context->mem_pointers, &context->opts->gen, context);\n',
      '\tif (romancer_trace.enabled && rt_bl.sys) rt_read_tagged(RT_NONE, context->scratch1);')
edit(Z, '\t\tz80_execute(context, target_cycle);\n',
     T.format('\t\trt_ring_swap(1);') + '\t\tz80_execute(context, target_cycle);\n' + T.format('\t\trt_ring_swap(0);'))

# ---- VDP: FIFO entries carry tags from the port write (or DMA source) to the store.
edit('vdp.h', '\tuint8_t  cd;\n\tuint8_t  partial;\n} fifo_entry;',
     '\tuint8_t  cd;\n\tuint8_t  partial;\n' + T.format('\tuint32_t rt_tag[2]; /* tags of value >> 8 and value & 0xFF */\n\tuint32_t rt_pc;') + '} fifo_entry;')
V = 'vdp.c'
VDP_HOOKS = r'''#include "rt_blastem.h"
static void rt_vdp_cpu(vdp_context *context, fifo_entry *cur, uint8_t hi, uint8_t lo, int byte)
{
	cur->rt_tag[0] = cur->rt_tag[1] = RT_NONE;
	cur->rt_pc = RT_PC_NONE;
	if (!romancer_trace.enabled || context != rt_bl.vdp) return;
	if (rt_bl.sys == RT_SYS_GEN && rt_bl.cpu == 0) {
		rt_tag_word(hi, lo, cur->rt_tag, cur->rt_tag + 1, 1);   /* 68000 */
	} else {
		cur->rt_tag[0] = rt_tag_for(hi);                         /* Z80: one byte at a time */
		cur->rt_tag[1] = byte || hi == lo ? cur->rt_tag[0] : rt_tag_for(lo);
	}
	cur->rt_pc = romancer_trace.pc;
}
static void rt_vdp_dma(vdp_context *context, fifo_entry *cur, uint32_t src)
{
	rt_domain *d = NULL;
	uint32_t i = 0, a = (src * 2) & 0xFFFFFF;
	int k;
	cur->rt_tag[0] = cur->rt_tag[1] = RT_NONE;
	cur->rt_pc = RT_PC_NONE;
	if (!romancer_trace.enabled || context != rt_bl.vdp || rt_bl.sys != RT_SYS_GEN) return;
	if ((a >= 0xA00000 && a < 0xB00000) || (a >= 0xC00000 && a <= 0xE00000)) return;
	k = rt_locate68(a, &d, &i);
	if (k == RT_LOC_ROM) {
		cur->rt_tag[0] = RT_TAG(RT_ROM, i);
		cur->rt_tag[1] = RT_TAG(RT_ROM, i + 1);
	} else if (k == RT_LOC_DOM) {
		cur->rt_tag[0] = rt_tag_at(d, i);
		cur->rt_tag[1] = rt_tag_at(d, i + 1);
	}
}
static void rt_vdp_fill(fifo_entry *cur)
{
	cur->rt_tag[0] = rt_derive(cur->rt_tag[0]);
	cur->rt_tag[1] = rt_derive(cur->rt_tag[1]);
	cur->rt_pc = RT_PC_NONE;
}
/* `address` is what write_vram_byte() receives. */
static void rt_vdp_vram_byte(vdp_context *context, uint32_t address, uint32_t tag, uint32_t pc)
{
	uint32_t i;
	if (!romancer_trace.enabled || context != rt_bl.vdp) return;
	if (rt_bl.sys == RT_SYS_SMS) {
		i = (address ^ 1) & 0x3FFF;
	} else if (context->regs[REG_MODE_2] & BIT_MODE_5) {
		i = address & 0xFFFF;
	} else {
		i = mode4_address_map[address & 0x3FFF];
	}
	rt_put(rt_bl.vram, i, tag, pc);
}
static void rt_vdp_vram_word(vdp_context *context, fifo_entry *start)
{
	uint32_t a = start->address;
	if (context != rt_bl.vdp) return;
	a = ((a & 0x3FC) | (a >> 1 & 0xFC01) | (a >> 9 & 0x2)) ^ 1;
	rt_put(rt_bl.vram, a & 0xFFFF, start->rt_tag[1], start->rt_pc);
}
/* A mode 5 CRAM/VSRAM store of the entry at word index `a` (bytes 2a, 2a+1). */
static void rt_vdp_word_store(vdp_context *context, rt_domain *d, fifo_entry *start, uint32_t a)
{
	if (start->partial == 3) {
		rt_put(d, a * 2 + !(start->address & 1), start->rt_tag[1], start->rt_pc);
	} else if (start->partial) {
		fifo_entry *f = context->fifo + context->fifo_write;
		rt_put(d, a * 2, rt_derive(f->rt_tag[0]), RT_PC_NONE);
		rt_put(d, a * 2 + 1, rt_derive(f->rt_tag[1]), RT_PC_NONE);
	} else {
		rt_put(d, a * 2, start->rt_tag[0], start->rt_pc);
		rt_put(d, a * 2 + 1, start->rt_tag[1], start->rt_pc);
	}
}
static void rt_vdp_cram(vdp_context *context, fifo_entry *start)
{
	uint32_t a;
	if (context != rt_bl.vdp) return;
	if (!(context->regs[REG_MODE_2] & BIT_MODE_5)) {
		if (context->type == VDP_GAMEGEAR) {
			a = start->address & 0x3E;
			rt_put(rt_bl.pal, a, rt_bl.latch_tag, rt_bl.latch_pc);
			rt_put(rt_bl.pal, a + 1, start->rt_tag[1], start->rt_pc);
		} else {
			a = start->address & 0x1F;
			rt_put(rt_bl.pal, a, start->rt_tag[1], start->rt_pc);
		}
		return;
	}
	rt_vdp_word_store(context, rt_bl.pal, start, (start->address >> 1) & (CRAM_SIZE-1));
}
static void rt_vdp_copy_read(vdp_context *context)
{
	if (context != rt_bl.vdp) return;
	rt_bl.copy_tag = rt_tag_at(rt_bl.vram, (context->regs[REG_DMASRC_M] << 8) | (context->regs[REG_DMASRC_L] ^ 1));
}'''
edit(V, 'uint16_t mode4_address_map[0x4000];\n', 'uint16_t mode4_address_map[0x4000];\n' + T.format(VDP_HOOKS))
# CPU data port writes (68K word, Z80/PBC byte).
edit(V, '\tcur->value = value;\n\tif (context->regs[REG_MODE_2] & BIT_MODE_5) {\n\t\tcur->cd = context->cd;\n\t} else {\n\t\tcur->cd = (context->cd & 2) | 1;\n',
     '\tcur->value = value;\n' + T.format('\trt_vdp_cpu(context, cur, value >> 8, value, 0);')
     + '\tif (context->regs[REG_MODE_2] & BIT_MODE_5) {\n\t\tcur->cd = context->cd;\n\t} else {\n\t\tcur->cd = (context->cd & 2) | 1;\n')
edit(V, '\tcur->value = value;\n\tif (context->regs[REG_MODE_2] & BIT_MODE_5) {\n\t\tcur->cd = context->cd;\n\t} else {\n\t\tif ((context->cd & 3) == CRAM_WRITE) {\n',
     '\tcur->value = value;\n' + T.format('\trt_vdp_cpu(context, cur, value, value, 1);')
     + '\tif (context->regs[REG_MODE_2] & BIT_MODE_5) {\n\t\tcur->cd = context->cd;\n\t} else {\n\t\tif ((context->cd & 3) == CRAM_WRITE) {\n')
# 68K -> VDP DMA: the source word's own tags.
after(V, '\t\t\tcur->value = read_dma_value((context->regs[REG_DMASRC_H] << 16) | (context->regs[REG_DMASRC_M] << 8) | context->regs[REG_DMASRC_L]);\n',
      '\t\t\trt_vdp_dma(context, cur, (context->regs[REG_DMASRC_H] << 16) | (context->regs[REG_DMASRC_M] << 8) | context->regs[REG_DMASRC_L]);')
# Fill: repeats of the data port byte are derived.
before(V, '\t\tvdp_advance_dma(context);\n\t}\n\tfifo_entry * start = context->fifo + context->fifo_read;\n', '\t\trt_vdp_fill(cur);')
# Stores, where the byte physically lands.
after(V, '\t\t\t\twrite_vram_word(context, start->address, start->value);\n', '\t\t\t\trt_vdp_vram_word(context, start);')
after(V, '\t\t\t\tvdp_check_update_sat_byte(context, address, byte);\n\t\t\t\twrite_vram_byte(context, address, byte);\n',
      '\t\t\t\trt_vdp_vram_byte(context, address, start->partial == 1 ? start->rt_tag[0] : start->rt_tag[1], start->rt_pc);')
after(V, '\t\t\t\t\t\tcontext->cram_latch = start->value;\n', '\t\t\t\t\t\trt_bl.latch_tag = start->rt_tag[1];\n\t\t\t\t\t\trt_bl.latch_pc = start->rt_pc;')
after(V, '\t\t\twrite_cram(context, start->address, val);\n', '\t\t\trt_vdp_cram(context, start);')
before(V, '\t\t\t\tuint8_t buffer[3] = {((start->address/2) & 63) + 128,',
       '\t\t\t\tif (context == rt_bl.vdp) {\n\t\t\t\t\trt_vdp_word_store(context, rt_bl.vsram, start, (start->address/2) & 63);\n\t\t\t\t}')
# A loaded savestate's FIFO entries have no provenance.
after(V, '\t\t\tentry->cd = load_int8(buf);\n\t\t\tentry->partial = load_int8(buf);\n',
      '\t\t\tentry->rt_tag[0] = entry->rt_tag[1] = RT_NONE;\n\t\t\tentry->rt_pc = RT_PC_NONE;')
# VRAM copy DMA: propagate the source byte's tag.
after(V, '\t\t\tcontext->prefetch = context->vdpmem[(context->regs[REG_DMASRC_M] << 8) | context->regs[REG_DMASRC_L] ^ 1];\n',
      '\t\t\trt_vdp_copy_read(context);')
after(V, '\t\t\twrite_vram_byte(context, context->address ^ 1, context->prefetch);\n',
      '\t\t\trt_vdp_vram_byte(context, context->address ^ 1, rt_bl.copy_tag, RT_PC_NONE);')

# ---- libretro glue: state, address classification, domains, per-frame shadows.
L = 'libblastem.c'
GLUE_C = r'''#ifndef NEW_CORE
#error "ROMANCER_TRACE hooks the generated interpreter cores; build with NEW_CORE=1"
#endif
#define ROMANCER_TRACE_IMPLEMENTATION
#include "rt_blastem.h"
#include "backend.h"

rt_blastem_state rt_bl;
/* fatal_error() or machine_freeze() inside retro_run() (an edited ROM writing
 * to a read-only VDP port, say) exits the process in stock BlastEm. A replay of an edited ROM is
 * allowed to go wrong, so the tracing build unwinds to retro_run() instead and
 * leaves the machine stopped: later retro_run() calls do nothing. */
static jmp_buf rt_run_recover;
static uint8_t rt_run_recover_valid, rt_dead;
/* A stopped machine reports no domain contents (data == NULL), so a crash is
 * never mistaken for "the edit changed these bytes". */
static void rt_no_contents(void)
{
	int i;
	for (i = 0; i < romancer_trace.domain_count; i++) romancer_trace.domains[i].data = NULL;
}
extern uint16_t mode4_address_map[0x4000];
enum { RT_PAL = 128, RT_VRAM = 0x10000, RT_VSRAM = 80, RT_WRAM = 0x10000, RT_ZRAM = 0x2000 };
#define RT_CELLS (RT_PAL + RT_VRAM + RT_VSRAM + RT_WRAM + RT_ZRAM)
static uint32_t rt_tag_mem[RT_CELLS], rt_pc_mem[RT_CELLS];
static uint8_t rt_pal_mem[RT_PAL], rt_vsram_mem[RT_VSRAM], rt_wram_mem[RT_WRAM], rt_vram16_mem[0x4000];
static genesis_context *rt_gen;
static sms_context *rt_sms;
static const uint8_t *rt_rom;
static uint32_t rt_rom_size;

int rt_locate68(uint32_t a, rt_domain **d, uint32_t *i)
{
	if (!rt_gen) return RT_LOC_NONE;
	if (a >= 0xE00000) {
		*d = rt_bl.wram;
		*i = a & 0xFFFF;
		return RT_LOC_DOM;
	}
	if ((a & 0xFF0000) == 0xA00000) {
		if ((a & 0xFFFF) >= 0x4000) return RT_LOC_NONE;
		*d = rt_bl.zram;
		*i = a & 0x1FFF;
		return RT_LOC_DOM;
	}
	if (a < 0x400000) {
		/* follows mapper banks; ROM is stored as host-order words */
		const uint8_t *q = get_native_pointer(a & ~1u, (void **)rt_gen->m68k->mem_pointers, &rt_gen->m68k->opts->gen);
		if (q && q >= rt_rom && q < rt_rom + rt_rom_size) {
			*i = (uint32_t)(q - rt_rom) + (a & 1);
			if (*i < rt_rom_size) return RT_LOC_ROM;
		}
	}
	return RT_LOC_NONE;
}

int rt_locatez80(uint32_t a, rt_domain **d, uint32_t *i)
{
	if (rt_gen) {
		if (a < 0x4000) {
			*d = rt_bl.zram;
			*i = a & 0x1FFF;
			return RT_LOC_DOM;
		}
		if (a >= 0x8000 && rt_gen->z80_bank_reg < 0x140) return rt_locate68(rt_gen->z80_bank_reg << 15 | (a & 0x7FFF), d, i);
		return RT_LOC_NONE;
	}
	if (rt_sms) {
		const uint8_t *q = get_native_pointer(a, (void **)rt_sms->z80->mem_pointers, &rt_sms->z80->opts->gen);
		if (!q) return RT_LOC_NONE;
		if (q >= rt_rom && q < rt_rom + rt_rom_size) {
			*i = (uint32_t)(q - rt_rom);
			return RT_LOC_ROM;
		}
		if (q >= rt_sms->ram && q < rt_sms->ram + sizeof(rt_sms->ram)) {
			*d = rt_bl.wram;
			*i = (uint32_t)(q - rt_sms->ram);
			return RT_LOC_DOM;
		}
	}
	return RT_LOC_NONE;
}

/* Domain contents in the same byte order as their tags; refreshed every frame. */
static void rt_refresh(void)
{
	uint32_t i;
	if (rt_gen) {
		vdp_context *v = rt_gen->vdp;
		const uint8_t *w = (const uint8_t *)rt_gen->work_ram;
		for (i = 0; i < CRAM_SIZE; i++) {
			rt_pal_mem[i * 2] = v->cram[i] >> 8;
			rt_pal_mem[i * 2 + 1] = v->cram[i];
		}
		for (i = 0; i < RT_VSRAM / 2; i++) {
			rt_vsram_mem[i * 2] = v->vsram[i] >> 8;
			rt_vsram_mem[i * 2 + 1] = v->vsram[i];
		}
		for (i = 0; i < RT_WRAM; i++) rt_wram_mem[i] = w[i ^ 1];
	} else if (rt_sms) {
		/* Palette bytes are rebuilt from CRAM so they survive a savestate load.
		 * Mode 4 CRAM keeps bits 0-5 of the written byte (the color); bits 6-7,
		 * which the hardware ignores, read back as 0. */
		vdp_context *v = rt_sms->vdp;
		if (v->type == VDP_GAMEGEAR) {
			for (i = 0; i < 32; i++) {
				rt_pal_mem[i * 2] = v->cram[i];
				rt_pal_mem[i * 2 + 1] = v->cram[i] >> 8;
			}
		} else {
			for (i = 0; i < 32; i++) rt_pal_mem[i] = (v->cram[i] >> 1 & 7) | (v->cram[i] >> 2 & 0x38);
		}
		for (i = 0; i < 0x4000; i++) rt_vram16_mem[i] = v->vdpmem[mode4_address_map[i ^ 1]];
	}
}

static void rt_teardown(void)
{
	rt_bl.sys = RT_SYS_NONE;
	rt_gen = NULL;
	rt_sms = NULL;
	romancer_trace.domain_count = 0;
}

static void rt_setup(system_header *sys, uint32_t media_size)
{
	uint32_t *t = rt_tag_mem, *c = rt_pc_mem;
	rt_teardown();
	rt_dead = 0;
	memset(&rt_bl, 0, sizeof rt_bl);
	memset(romancer_trace.ring_value, 0, sizeof romancer_trace.ring_value);
	memset(romancer_trace.ring_tag, 0, sizeof romancer_trace.ring_tag);
	romancer_trace.last_rom = 0;
	romancer_trace.pc = RT_PC_NONE;
	memset(rt_pal_mem, 0, sizeof rt_pal_mem);
	if (sys->type == SYSTEM_GENESIS) {
		genesis_context *gen = (genesis_context *)sys;
		rt_gen = gen;
		rt_rom = (const uint8_t *)gen->cart;
		rt_rom_size = gen->header.info.rom_size;
		rt_bl.vdp = gen->vdp;
		rt_bl.pal = rt_register("palette", RT_PAL, t, c, rt_pal_mem); t += RT_PAL; c += RT_PAL;
		rt_bl.vram = rt_register("vram", RT_VRAM, t, c, gen->vdp->vdpmem); t += RT_VRAM; c += RT_VRAM;
		rt_bl.vsram = rt_register("vsram", RT_VSRAM, t, c, rt_vsram_mem); t += RT_VSRAM; c += RT_VSRAM;
		rt_bl.wram = rt_register("wram", RT_WRAM, t, c, rt_wram_mem); t += RT_WRAM; c += RT_WRAM;
		rt_bl.zram = rt_register("z80ram", RT_ZRAM, t, c, gen->zram);
		rt_bl.sys = RT_SYS_GEN;
	} else if (sys->type == SYSTEM_SMS || sys->type == SYSTEM_GAME_GEAR) {
		sms_context *sms = (sms_context *)sys;
		rt_sms = sms;
		rt_rom = sms->rom;
		rt_rom_size = sms->rom_size;
		rt_bl.vdp = sms->vdp;
		rt_bl.pal = rt_register("palette", sys->type == SYSTEM_GAME_GEAR ? 64 : 32, t, c, rt_pal_mem); t += RT_PAL; c += RT_PAL;
		rt_bl.vram = rt_register("vram", 0x4000, t, c, rt_vram16_mem); t += 0x4000; c += 0x4000;
		rt_bl.wram = rt_register("wram", sizeof(sms->ram), t, c, sms->ram);
		rt_bl.sys = RT_SYS_SMS;
	} else {
		return;
	}
	if (media_size && media_size < rt_rom_size) rt_rom_size = media_size;
	rt_refresh();
}'''
edit(L, '#include "vfs_file.h"\n\ntern_node *config;\n', '#include "vfs_file.h"\n' + T.format(GLUE_C) + '\ntern_node *config;\n')
edit(L, '\tif (!current_system) {\n\t\trelease_media();\n\t\treturn 0;\n\t}\n\n\t/* ROMancer SMS adapter',
     '\tif (!current_system) {\n\t\trelease_media();\n\t\treturn 0;\n\t}\n' + T.format('\trt_setup(current_system, media.size);') + '\n\t/* ROMancer SMS adapter')
edit(L, '\tflush_audio();\n}\n\n/* Returns the amount of data',
     '\tflush_audio();\n' + T.format('\trt_run_recover_valid = 0;\n\trt_refresh();') + '}\n\n/* Returns the amount of data')
after(L, 'RETRO_API void retro_run(void)\n{\n\tbool options_updated = false;\n',
      '\tif (rt_dead) return;\n\tif (setjmp(rt_run_recover)) {\n\t\trt_run_recover_valid = 0;\n\t\trt_dead = 1;\n'
      '\t\tfprintf(stderr, "ROMancer trace: the machine stopped on a fatal error; this run is over\\n");\n\t\tfflush(stderr);\n'
      '\t\trt_no_contents();\n'
      '\t\treturn;\n\t}\n\trt_run_recover_valid = 1;')
after(L, 'void lib_fatal_error(void)\n{\n',
      '\tif (rt_run_recover_valid) {\n\t\trt_run_recover_valid = 0;\n\t\tlongjmp(rt_run_recover, 1);\n\t}')
# machine_freeze() (an illegal VDP access, a write without TMSS unlock, ...) calls exit(1)
# itself and never reaches fatal_error(); give it the same way out of retro_run().
after('config.c', 'void machine_freeze(tern_node *config, debug_callback callback, void *data, char *format, ...)\n{\n',
      '\t{\n\t\textern void lib_fatal_error(void);\n\t\tlib_fatal_error(); /* returns unless retro_run() is on the stack */\n\t}')
edit(L, '\tcurrent_system->deserialize(current_system, (uint8_t *)(buffer + 1), *buffer);\n',
     T.format('\trt_prestart();')
     + '\tcurrent_system->deserialize(current_system, (uint8_t *)(buffer + 1), *buffer);\n' + T.format('\trt_refresh();'))
# Savestates before the first frame (ROMancer's boot checkpoint, and replays that
# load a checkpoint into a freshly loaded game).
PRESTART = r'''/* BlastEm resets the machine inside the first retro_run() and refuses to save a
 * state before it; a state loaded before it would be reset away again. ROMancer
 * takes a boot checkpoint before the first frame and replays checkpoints in a
 * freshly loaded game, so the tracing build does that same reset on demand and
 * lets the first retro_run() resume. Without a savestate call before the first
 * frame nothing here runs. */
static void rt_prestart(void)
{
	if (started || !current_system) return;
	if (current_system->type == SYSTEM_GENESIS) {
		/* start_genesis(): reset, then the loop resume_genesis() also runs */
		m68k_reset(((genesis_context *)current_system)->m68k);
	} else if (current_system->type == SYSTEM_SMS || current_system->type == SYSTEM_GAME_GEAR) {
		/* start_sms(): reset, video standard, then run_sms() as resume_sms() does */
		sms_context *sms = (sms_context *)current_system;
		z80_assert_reset(sms->z80, 0);
		z80_clear_reset(sms->z80, 128*15);
		render_set_video_standard(sms->vdp->type == VDP_GAMEGEAR ? VID_GAMEGEAR : VID_NTSC);
	} else {
		return;
	}
	started = 1;
}'''
edit(L, 'static size_t serialize_size_cache;\nRETRO_API size_t retro_serialize_size(void)\n{\n',
     T.format(PRESTART) + 'static size_t serialize_size_cache;\nRETRO_API size_t retro_serialize_size(void)\n{\n' + T.format('\trt_prestart();'))
edit(L, 'RETRO_API bool retro_serialize(void *data, size_t size)\n{\n',
     'RETRO_API bool retro_serialize(void *data, size_t size)\n{\n' + T.format('\trt_prestart();'))
before(L, '\tcurrent_system->free_context(current_system);\n\tcurrent_system = NULL;\n\t//the next system loaded', '\trt_teardown();')
print('blastem hooks applied')
