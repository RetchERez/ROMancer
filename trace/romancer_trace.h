/* ROMancer provenance tracing, shared by the tracing builds of every engine.
 *
 * Each byte of a traced memory domain (palette RAM, video RAM, work RAM, ...)
 * carries a 32-bit tag saying where its current value came from:
 *
 *   bits 28-30  kind   RT_ROM      copied from a ROM data byte
 *                      RT_IMM      copied from an instruction operand in ROM
 *                      RT_DERIVED  computed by code; offset = last ROM data byte read
 *                      RT_NONE     never written while tracing
 *   bit  31     weak   the value was 0x00 or 0xFF, so the match may be a coincidence
 *   bits 0-27   ROM file offset (header excluded)
 *
 * A second 32-bit array per domain records the ROM offset of the instruction
 * that performed the write (RT_PC_NONE when it ran from RAM or was DMA).
 *
 * Tags propagate by value matching: every CPU read pushes (value, tag) into a
 * short ring; a write takes the tag of the most recent ring entry holding the
 * same value. Plain copy loops, DMA and immediate loads are therefore exact;
 * computed values are reported as derived, never as exact.
 *
 * A domain's `data` must be the machine's real state whenever the frontend can
 * look (between retro_* calls): either the engine's own memory, or a view the
 * engine refreshes after every run, reset and loadstate. A buffer that only
 * follows the game's writes goes stale on loadstate and leaks between games.
 *
 * Tags are not part of a savestate. The Game Boy engines clear every tag (via
 * romancer_trace_reset) when a game loads, on reset and on loadstate, because
 * the bytes then come from the state rather than from writes that were
 * watched; to get provenance after a loadstate, replay from it with tracing on.
 *
 * The header is self-contained C99 and compiles as C++. Define
 * ROMANCER_TRACE_IMPLEMENTATION in exactly one translation unit.
 */
#ifndef ROMANCER_TRACE_H
#define ROMANCER_TRACE_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RT_VERSION 1
#define RT_NONE 0u
#define RT_ROM 1u
#define RT_IMM 2u
#define RT_DERIVED 3u
#define RT_WEAK 0x80000000u
#define RT_OFFSET_MASK 0x0FFFFFFFu
#define RT_PC_NONE 0xFFFFFFFFu
#define RT_TAG(kind, offset) ((((uint32_t)(kind)) << 28) | ((uint32_t)(offset) & RT_OFFSET_MASK))
#define RT_KIND(tag) (((tag) >> 28) & 7u)
#define RT_RING 8
#define RT_MAX_DOMAINS 16

#if defined(_WIN32) && defined(__GNUC__)
/* spelled with underscores: bsnes/nall defines a `dllexport` macro */
#define RT_EXPORT __attribute__((__dllexport__))
#elif defined(_WIN32)
#define RT_EXPORT __declspec(dllexport)
#else
#define RT_EXPORT __attribute__((visibility("default")))
#endif

typedef struct rt_domain {
    const char *name;      /* e.g. "palette", "vram", "wram", "oam" */
    uint32_t size;         /* bytes */
    uint32_t *tag;         /* size entries */
    uint32_t *pc;          /* size entries */
    const uint8_t *data;   /* live contents, or NULL when the core keeps them elsewhere */
} rt_domain;

typedef struct rt_state {
    int enabled;
    uint8_t ring_value[RT_RING];
    uint32_t ring_tag[RT_RING];
    unsigned ring_head;
    uint32_t last_rom;     /* offset of the most recent ROM data read */
    uint32_t pc;           /* ROM offset of the current instruction, or RT_PC_NONE */
    int domain_count;
    rt_domain domains[RT_MAX_DOMAINS];
    uint64_t writes;       /* traced writes since reset, for sanity checks */
} rt_state;

extern rt_state romancer_trace;

/* ---- hooks called by the engine ------------------------------------- */

static inline void rt_push(uint8_t value, uint32_t tag) {
    rt_state *s = &romancer_trace;
    unsigned i = s->ring_head = (s->ring_head + 1) % RT_RING;
    s->ring_value[i] = value;
    s->ring_tag[i] = tag;
}

/* CPU read of a ROM data byte at file offset `offset`. */
static inline void rt_read_rom(uint32_t offset, uint8_t value) {
    if (!romancer_trace.enabled) return;
    romancer_trace.last_rom = offset;
    rt_push(value, RT_TAG(RT_ROM, offset));
}

/* CPU fetch of an instruction operand (immediate) at ROM offset `offset`. */
static inline void rt_read_imm(uint32_t offset, uint8_t value) {
    if (!romancer_trace.enabled) return;
    rt_push(value, RT_TAG(RT_IMM, offset));
}

/* CPU read of a traced byte that already carries a tag (RAM, VRAM, ...). */
static inline void rt_read_tagged(uint32_t tag, uint8_t value) {
    if (!romancer_trace.enabled) return;
    rt_push(value, tag);
}

/* Start of an instruction; `rom_pc` is its ROM offset or RT_PC_NONE. */
static inline void rt_instruction(uint32_t rom_pc) { romancer_trace.pc = rom_pc; }

/* Tag for a value the CPU is about to write. */
static inline uint32_t rt_tag_for(uint8_t value) {
    rt_state *s = &romancer_trace;
    unsigned i, k;
    uint32_t tag;
    for (k = 0; k < RT_RING; k++) {
        i = (s->ring_head + RT_RING - k) % RT_RING;
        if (s->ring_value[i] == value && s->ring_tag[i] != RT_NONE) {
            tag = s->ring_tag[i] & ~RT_WEAK;
            if (value == 0x00 || value == 0xFF || (s->ring_tag[i] & RT_WEAK)) tag |= RT_WEAK;
            return tag;
        }
    }
    return s->last_rom ? RT_TAG(RT_DERIVED, s->last_rom) : RT_NONE;
}

/* CPU write of `value` into byte `index` of a traced domain. */
static inline void rt_write(rt_domain *d, uint32_t index, uint8_t value) {
    if (!romancer_trace.enabled || !d || index >= d->size) return;
    d->tag[index] = rt_tag_for(value);
    d->pc[index] = romancer_trace.pc;
    romancer_trace.writes++;
}

/* Write with an explicit tag: DMA and other transfers that know their source. */
static inline void rt_write_tag(rt_domain *d, uint32_t index, uint32_t tag) {
    if (!romancer_trace.enabled || !d || index >= d->size) return;
    d->tag[index] = tag;
    d->pc[index] = RT_PC_NONE;
    romancer_trace.writes++;
}

static inline uint32_t rt_tag_at(const rt_domain *d, uint32_t index) {
    return (d && index < d->size) ? d->tag[index] : RT_NONE;
}

/* Register a domain; arrays are owned by the engine. Returns the slot. */
rt_domain *rt_register(const char *name, uint32_t size, uint32_t *tag, uint32_t *pc, const uint8_t *data);

/* ---- exported to ROMancer ------------------------------------------- */
RT_EXPORT int romancer_trace_version(void);
RT_EXPORT void romancer_trace_enable(int enabled);
RT_EXPORT void romancer_trace_reset(void);
RT_EXPORT int romancer_trace_domain_count(void);
RT_EXPORT const rt_domain *romancer_trace_domain(int index);
RT_EXPORT uint64_t romancer_trace_writes(void);

#ifdef ROMANCER_TRACE_IMPLEMENTATION
rt_state romancer_trace;

rt_domain *rt_register(const char *name, uint32_t size, uint32_t *tag, uint32_t *pc, const uint8_t *data) {
    int i;
    for (i = 0; i < romancer_trace.domain_count; i++)
        if (strcmp(romancer_trace.domains[i].name, name) == 0) break;
    if (i == RT_MAX_DOMAINS) return NULL;
    if (i == romancer_trace.domain_count) romancer_trace.domain_count++;
    romancer_trace.domains[i].name = name;
    romancer_trace.domains[i].size = size;
    romancer_trace.domains[i].tag = tag;
    romancer_trace.domains[i].pc = pc;
    romancer_trace.domains[i].data = data;
    memset(tag, 0, size * sizeof(uint32_t));
    memset(pc, 0xFF, size * sizeof(uint32_t));
    return &romancer_trace.domains[i];
}

int romancer_trace_version(void) { return RT_VERSION; }
void romancer_trace_enable(int enabled) { romancer_trace.enabled = enabled ? 1 : 0; }
void romancer_trace_reset(void) {
    int i;
    for (i = 0; i < romancer_trace.domain_count; i++) {
        rt_domain *d = &romancer_trace.domains[i];
        memset(d->tag, 0, d->size * sizeof(uint32_t));
        memset(d->pc, 0xFF, d->size * sizeof(uint32_t));
    }
    memset(romancer_trace.ring_value, 0, sizeof romancer_trace.ring_value);
    memset(romancer_trace.ring_tag, 0, sizeof romancer_trace.ring_tag);
    romancer_trace.last_rom = 0;
    romancer_trace.pc = RT_PC_NONE;
    romancer_trace.writes = 0;
}
int romancer_trace_domain_count(void) { return romancer_trace.domain_count; }
const rt_domain *romancer_trace_domain(int index) {
    return (index >= 0 && index < romancer_trace.domain_count) ? &romancer_trace.domains[index] : NULL;
}
uint64_t romancer_trace_writes(void) { return romancer_trace.writes; }
#endif

#ifdef __cplusplus
}
#endif
#endif
