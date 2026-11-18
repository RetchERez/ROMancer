"""Live palettes from a tracing engine, mapped to the ROM bytes behind them.

Each swatch is one palette entry as the hardware holds it right now, with the
ROM offsets its stored bytes came from. Editing a swatch plans ROM writes for
those offsets; romancer.provenance.verify_edit then confirms them.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .level_palette import decode_palette, encode_palette
from .provenance import RT_DERIVED, RT_IMM, RT_ROM, RT_WEAK, Scene, tag_kind, tag_offset

# The NES stores 6-bit color indices; these are the colors FCEUmm displays for them.
NES_RGB = ((117,117,117),(36,24,142),(0,0,170),(69,0,158),(142,0,117),(170,0,16),(166,0,0),(125,8,0),(65,44,0),(0,69,0),(0,81,0),(0,60,20),(24,60,93),(0,0,0),(0,0,0),(0,0,0),
           (190,190,190),(0,113,239),(32,56,239),(130,0,243),(190,0,190),(231,0,89),(219,40,0),(203,77,12),(138,113,0),(0,150,0),(0,170,0),(0,146,56),(0,130,138),(0,0,0),(0,0,0),(0,0,0),
           (255,255,255),(60,190,255),(93,150,255),(207,138,255),(247,121,255),(255,117,182),(255,117,97),(255,154,56),(243,190,60),(130,211,16),(77,223,73),(89,251,154),(0,235,219),(121,121,121),(0,0,0),(0,0,0),
           (255,255,255),(170,231,255),(199,215,255),(215,203,255),(255,199,255),(255,199,219),(255,190,178),(255,219,170),(255,231,162),(227,255,162),(170,243,190),(178,255,207),(158,255,243),(199,199,199),(0,0,0),(0,0,0))

# domain name, stored format, bytes per entry, entries per palette line, and how to name a group.
LAYOUTS = {
    'nes': [('palette', 'nes-index', 1, 4, lambda i: ('Background' if i < 16 else 'Sprite') + f' palette {i % 16 // 4}')],
    'snes': [('palette', 'rgb555-le', 2, 16, lambda i: ('Background' if i < 128 else 'Sprite') + f' palette {i // 16 % 8}')],
    'genesis': [('palette', 'genesis', 2, 16, lambda i: f'Palette line {i // 16}')],
    'sms': [('palette', 'sms-rgb222', 1, 16, lambda i: ('Background' if i < 16 else 'Sprite') + ' palette')],
    'gb': [('dmg_palette', 'dmg-shades', 1, 1, lambda i: ('Background shades', 'Sprite shades 0', 'Sprite shades 1')[i])],
    'gbc': [('palette', 'rgb555-le', 2, 4, lambda i: ('Background' if i < 32 else 'Sprite') + f' palette {i % 32 // 4}'),
            ('dmg_palette', 'dmg-shades', 1, 1, lambda i: ('Background shades', 'Sprite shades 0', 'Sprite shades 1')[i])],
}
LAYOUTS['gb'] = LAYOUTS['gbc']  # Game Boy Color hardware runs some GB games with CGB palettes


@dataclass
class Swatch:
    domain: str
    entry: int
    group: str
    format: str
    stored: bytes
    rgb: list            # [[r,g,b]] (one color, or four shades for a DMG register)
    sources: list        # per stored byte: {'offset', 'kind', 'weak', 'pc'} or None
    status: str = ''     # 'rom', 'code', 'derived', 'unknown'
    notes: list = field(default_factory=list)

    @property
    def editable(self) -> bool:
        return self.status in ('rom', 'code')


def _decode(fmt, raw):
    if fmt == 'nes-index':
        return [list(NES_RGB[raw[0] & 0x3F])]
    if fmt == 'dmg-shades':
        return decode_palette(raw, fmt, 4)
    return decode_palette(raw, fmt, 1)


def swatches(scene: Scene, system: str) -> list[Swatch]:
    out = []
    for domain, fmt, size, _line, group in LAYOUTS.get(system, []):
        d = scene.snapshot.domains.get(domain)
        if d is None or d.data is None:
            continue
        for entry in range(len(d.data) // size):
            raw = d.data[entry * size:(entry + 1) * size]
            srcs = []
            for k in range(size):
                t = d.tags[entry * size + k]
                kind = tag_kind(t)
                srcs.append(None if kind == 0 else {'offset': tag_offset(t), 'kind': ('', 'rom', 'code', 'derived')[kind],
                                                    'weak': bool(t & RT_WEAK), 'pc': d.pcs[entry * size + k]})
            kinds = {s['kind'] for s in srcs if s}
            status = ('unknown' if not kinds or None in srcs else 'derived' if 'derived' in kinds
                      else 'code' if 'code' in kinds else 'rom')
            sw = Swatch(domain, entry, group(entry), fmt, bytes(raw), _decode(fmt, raw), srcs, status)
            if size == 2 and status in ('rom', 'code') and srcs[0]['offset'] + 1 != srcs[1]['offset'] and srcs[0]['offset'] - 1 != srcs[1]['offset']:
                sw.notes.append('The two bytes of this color come from separate places in the ROM.')
            if any(s and s['weak'] for s in srcs):
                sw.notes.append('Stored value is 00 or FF, so the source match needs the replay check.')
            out.append(sw)
    return out


def encode_swatch(swatch: Swatch, rgb) -> bytes:
    """The bytes palette RAM holds once this entry shows `rgb` (four shades for a DMG register)."""
    if swatch.format == 'nes-index':
        best = min(range(64), key=lambda i: sum((a - b) ** 2 for a, b in zip(NES_RGB[i], rgb)) + (i & 0x0F in (0x0D, 0x0E, 0x0F)) * 10**6)
        return bytes([(swatch.stored[0] & 0xC0) | best])
    if swatch.format == 'dmg-shades':
        return bytes(encode_palette([list(c) for c in rgb], 'dmg-shades', swatch.stored))
    return bytes(encode_palette([list(rgb)], swatch.format, swatch.stored))


def plan_color_edit(swatch: Swatch, rgb, rom: bytes) -> list[tuple[int, int, int]]:
    """ROM writes [(offset, old, new)] that store `rgb` in this entry.

    Only ROM and code-value sources are written directly. Derived sources need
    locate_derived_source first.
    """
    if not swatch.editable:
        raise ValueError('This color is computed by the game; locate its source before editing.')
    new = encode_swatch(swatch, rgb)
    writes = []
    # NES tags count from the end of the 16-byte iNES header; `rom` is the whole file.
    skip = 16 if swatch.format == 'nes-index' and rom[:4] == b'NES\x1a' else 0
    for k, src in enumerate(swatch.sources):
        if new[k] == swatch.stored[k]:
            continue
        off = src['offset'] + skip
        if off >= len(rom) or rom[off] != swatch.stored[k]:
            raise ValueError('ROM byte at the traced source differs from the stored color; take a new scene.')
        writes.append((off, rom[off], new[k]))
    return writes


def plan_at(swatch: Swatch, rgb, rom: bytes, offsets) -> list[tuple[int, int, int]]:
    """ROM writes that store `rgb` at `offsets` (tracing offsets, one per stored byte), whatever the entry's tags say.

    The ROM must hold the entry's stored bytes there now. Like every plan for a
    color the tags do not name directly, this is a proposal for a replay to confirm.
    """
    direct = [{'offset': int(o), 'kind': 'rom', 'weak': False, 'pc': None} for o in offsets]
    if len(direct) != len(swatch.stored):
        raise ValueError('A place for this color needs one ROM offset for each stored byte.')
    return plan_color_edit(replace(swatch, status='rom', sources=direct), rgb, rom)


def line_entries(system: str, domain: str) -> int:
    """How many palette entries the hardware groups together (the three shade registers count as one group)."""
    if domain == 'dmg_palette':
        return 3
    return next((layout[3] for layout in LAYOUTS.get(system, []) if layout[0] == domain), 16)


def _line_runs(raw: bytes, size: int, least: int, variety: int, rom: bytes, skip: int) -> list[tuple[int, int, int]]:
    """(first entry, entries, ROM position) of every longest stretch of a palette line the ROM holds byte for byte."""
    count = len(raw) // size
    runs = set()
    for seed in range(count - least + 1):
        pattern = raw[seed * size:(seed + least) * size]
        if len(set(pattern)) < min(variety, 2):
            continue                      # one repeated value is everywhere in a ROM
        hits, found = [], rom.find(pattern, skip)
        while found >= 0 and len(hits) <= 256:
            hits.append(found)
            found = rom.find(pattern, found + 1)
        if len(hits) > 256:
            continue
        for hit in hits:
            start, end = seed, seed + least
            while start > 0 and hit - (seed - start + 1) * size >= skip and (
                    rom[hit - (seed - start + 1) * size:hit - (seed - start) * size] == raw[(start - 1) * size:start * size]):
                start -= 1
            while end < count and rom[hit + (end - seed) * size:hit + (end - seed + 1) * size] == raw[end * size:(end + 1) * size]:
                end += 1
            if len(set(raw[start * size:end * size])) >= variety:
                runs.add((start, end - start, hit - (seed - start) * size))
    return sorted(runs, key=lambda r: (-r[1], r[2]))


def stored_copies(swatch: Swatch, swatches, rom: bytes, system: str, limit: int = 6, cache: dict | None = None) -> list[dict]:
    """Places where the ROM holds this entry inside a plain copy of the palette line it belongs to.

    A fade routine, a second processor on the cartridge or a copy made before
    recording started all leave a color without a usable tag, though the
    palette itself often sits in the ROM as plain colors. This looks for
    stretches of neighbouring entries of the same line, this entry included,
    that the ROM holds byte for byte. Each result is
    {'offsets': tracing offsets of this entry's bytes, 'run': entries matched, 'copies': places with a run that long},
    longest run first, then nearest to the entry's traced offsets. A match is a
    proposal only: plan_at writes it and a replay decides.
    """
    size = len(swatch.stored)
    count = line_entries(system, swatch.domain)
    first = swatch.entry - swatch.entry % count
    line = {s.entry: s for s in swatches if s.domain == swatch.domain and first <= s.entry < first + count}
    if any(first + k not in line for k in range(count)):
        return []
    raw = b''.join(line[first + k].stored for k in range(count))
    skip = 16 if swatch.format == 'nes-index' and rom[:4] == b'NES\x1a' else 0
    shades = swatch.domain == 'dmg_palette'
    key = (swatch.domain, raw)
    runs = None if cache is None else cache.get(key)
    if runs is None:
        runs = _line_runs(raw, size, 3 if shades else 4 if size == 1 else 2, 2 if shades else 3, rom, skip)
        if cache is not None:
            cache[key] = runs
    at = swatch.entry - first
    near = [s['offset'] for s in swatch.sources if s]
    mine = [(run, position - skip + (at - start) * size) for start, run, position in runs if start <= at < start + run]
    lengths = {}
    for run, _ in mine:
        lengths[run] = lengths.get(run, 0) + 1
    mine.sort(key=lambda m: (-m[0], min((abs(m[1] - n) for n in near), default=0), m[1]))
    out, seen = [], set()
    for run, place in mine:
        if place not in seen:
            seen.add(place)
            out.append({'offsets': list(range(place, place + size)), 'run': run, 'copies': lengths[run]})
    return out[:limit]


def found_places(swatch: Swatch, swatches, rom: bytes, system: str, hints=(), limit: int = 6, cache: dict | None = None) -> list[dict]:
    """Places to try for a color the tags do not lead to, best first: [{'offsets', 'how', 'note'}].

    `hints` are offset lists where another scene traced this same entry, holding
    this same color, straight to the ROM (a fade tags it 'derived' a moment later).
    Then come the plain copies of its palette line (stored_copies).
    """
    own = tuple(s['offset'] if s else None for s in swatch.sources)
    out, seen = [], {own}
    for offsets in hints:
        offsets = tuple(int(o) for o in offsets)
        if offsets not in seen and len(offsets) == len(swatch.stored):
            seen.add(offsets)
            out.append({'offsets': list(offsets), 'how': 'other scene',
                        'note': 'Another recorded scene loads this color straight from the ROM; this is that place.'})
    for copy in stored_copies(swatch, swatches, rom, system, limit=limit, cache=cache):
        offsets = tuple(copy['offsets'])
        if offsets not in seen:
            seen.add(offsets)
            out.append({'offsets': list(offsets), 'how': f"copy of {copy['run']} entries",
                        'note': f"The ROM holds {copy['run']} neighbouring colors of this palette as plain colors; this is that place."})
    for place in constant_places(swatch, swatches, rom, system, limit=limit):
        if (place,) not in seen:
            seen.add((place,))
            out.append({'offsets': [place], 'how': 'constant in code',
                        'note': 'The game sets this color from a number in its program; this is that number.'})
    return out[:limit]


# Instructions that load a one-byte number, per processor. A palette value set from code sits right after one.
_LOADS = {'gb': (0x3E, 0x36, 0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E), 'nes': (0xA9, 0xA2, 0xA0)}
_LOADS['gbc'] = _LOADS['sms'] = _LOADS['gb']


def constant_places(swatch: Swatch, swatches, rom: bytes, system: str, limit: int = 6) -> list[int]:
    """Tracing offsets of numbers in the program that may set this one-byte palette value.

    A game that keeps its palette as numbers in code (load a number, store it,
    load the next) may fade it through work RAM, which loses the tag. Only
    numbers that have a neighbour of the same palette line set close by are
    offered: one matching byte alone is far too common. A proposal for a replay.
    """
    loads = _LOADS.get(system)
    if not loads or len(swatch.stored) != 1:
        return []
    skip = 16 if swatch.format == 'nes-index' and rom[:4] == b'NES\x1a' else 0

    def numbers(value):
        hits = []
        for load in loads:
            found = rom.find(bytes([load, value]), skip)
            while found >= 0 and len(hits) <= 512:
                hits.append(found + 1 - skip)
                found = rom.find(bytes([load, value]), found + 1)
        return sorted(hits) if len(hits) <= 512 else []

    count = line_entries(system, swatch.domain)
    first = swatch.entry - swatch.entry % count
    others = [numbers(s.stored[0]) for s in swatches
              if s.domain == swatch.domain and first <= s.entry < first + count and s.entry != swatch.entry and any(s.stored)]
    scored = []
    for place in numbers(swatch.stored[0]):
        close = sum(any(abs(o - place) <= 24 and o != place for o in other) for other in others)
        if close:
            scored.append((-close, place))
    return [place for _, place in sorted(scored)[:limit]]


def plan_by_measurement(measure, rom: bytes, offsets, stored: bytes, wanted: bytes, reach: int = 2, limit: int = 64):
    """ROM writes that give a palette entry the bytes `wanted`, worked out by experiment, or None.

    For a color the game puts together from several ROM bytes (two bits of a
    Game Boy shade register from each of four table bytes, say). `offsets` are
    file offsets known to move the entry. Every bit of those bytes and of
    their neighbours within `reach` is flipped on its own and
    `measure(writes)` reports the entry's bytes after a replay (None when it
    did not move). If the flips combine without interfering, a set of them
    turns `stored` into `wanted`; the caller replays that set, because only
    the replay shows whether they really combine.
    """
    offsets = sorted(set(int(o) for o in offsets))
    if not offsets or len(stored) != len(wanted) or stored == wanted:
        return None
    bytes_ = [o for o in range(max(0, offsets[0] - reach), min(len(rom), offsets[-1] + reach + 1))]
    if len(bytes_) * 8 > limit:
        bytes_ = [o for o in offsets if 0 <= o < len(rom)][:limit // 8]
    number = lambda raw: int.from_bytes(raw, 'big')
    goal = number(stored) ^ number(wanted)
    basis = {}                                    # leading bit -> (effect, set of (offset, bit))
    for offset in bytes_:
        for bit in range(8):
            after = measure([(offset, rom[offset], rom[offset] ^ (1 << bit))])
            if after is None or len(after) != len(stored):
                continue
            effect, flips = number(after) ^ number(stored), frozenset([(offset, bit)])
            while effect:
                lead = effect.bit_length() - 1
                if lead not in basis:
                    basis[lead] = (effect, flips)
                    break
                effect, flips = effect ^ basis[lead][0], flips ^ basis[lead][1]
    chosen = frozenset()
    while goal:
        lead = goal.bit_length() - 1
        if lead not in basis:
            return None
        goal, chosen = goal ^ basis[lead][0], chosen ^ basis[lead][1]
    values = {}
    for offset, bit in chosen:
        values[offset] = values.get(offset, rom[offset]) ^ (1 << bit)
    return [(offset, rom[offset], value) for offset, value in sorted(values.items())] or None


def plan_derived_edit(swatch: Swatch, rgb, rom: bytes, radius: int = 3) -> list[tuple[int, int, int]]:
    """ROM writes for a 'derived' entry that the game is passing through unchanged right now.

    Fade and brightness routines compute every color, so their output is tagged
    derived even at full brightness, and a derived tag only names the last ROM
    byte that went into the value (usually the high byte of the color). When
    the stored bytes sit in the ROM at, or within `radius` bytes of, a traced
    offset, that place is the palette data itself and can be written like a
    direct source. This is a proposal: the entry counts as editable only after
    verify_edit shows the planned color arriving in palette RAM.
    """
    if swatch.status != 'derived':
        raise ValueError('This color is not computed; use plan_color_edit.')
    skip = 16 if swatch.format == 'nes-index' and rom[:4] == b'NES\x1a' else 0
    size = len(swatch.stored)
    srcs = swatch.sources

    def as_direct(offsets):
        return plan_at(swatch, rgb, rom, offsets)

    # Each byte still equals the ROM byte it was computed from.
    if all(s and s['offset'] + skip < len(rom) and rom[s['offset'] + skip] == swatch.stored[k] for k, s in enumerate(srcs))             and len({s['offset'] for s in srcs}) == size:
        return as_direct([s['offset'] for s in srcs])
    # The whole entry sits next to a traced offset; prefer the place that ends on it.
    places = set()
    for s in srcs:
        if not s:
            continue
        for start in range(max(0, s['offset'] - radius - size + 1), s['offset'] + radius + 1):
            if rom[start + skip:start + skip + size] == swatch.stored:
                places.add((abs(start + size - 1 - s['offset']), abs(start - s['offset']), start))
    if not places:
        raise ValueError('This color is not a plain copy of its source right now (mid-fade, recolored or compressed).')
    start = min(places)[2]
    return as_direct(list(range(start, start + size)))


def locate_derived_source(verify, rom: bytes, swatch: Swatch, scene: Scene, radius: int = 3):
    """Find which ROM bytes near a derived tag actually change this entry.

    `verify(edited_rom)` must return romancer.provenance.verify_edit's result.
    Each candidate is checked by replaying the engine, so the answer is a
    measured effect, never a guess.
    """
    hits = []
    seen = set()
    # NES tags count from the end of the 16-byte iNES header; `rom` may be the whole file.
    skip = 16 if swatch.format == 'nes-index' and rom[:4] == b'NES\x1a' else 0
    for src in swatch.sources:
        if not src or src['kind'] != 'derived':
            continue
        for off in range(max(skip, src['offset'] + skip - radius), min(len(rom), src['offset'] + skip + radius + 1)):
            if off in seen:
                continue
            seen.add(off)
            edited = bytearray(rom)
            edited[off] ^= 0x1F
            result = verify(bytes(edited))
            indices = result['changed'].get(swatch.domain, [])
            width = len(swatch.stored)
            if any(swatch.entry * width <= i < (swatch.entry + 1) * width for i in indices):
                hits.append({'offset': off, 'also_changes': {k: len(v) for k, v in result['changed'].items()}})
    return hits
