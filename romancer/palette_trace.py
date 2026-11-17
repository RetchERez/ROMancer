"""Live palettes from a tracing engine, mapped to the ROM bytes behind them.

Each swatch is one palette entry as the hardware holds it right now, with the
ROM offsets its stored bytes came from. Editing a swatch plans ROM writes for
those offsets; romancer.provenance.verify_edit then confirms them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


def plan_color_edit(swatch: Swatch, rgb, rom: bytes) -> list[tuple[int, int, int]]:
    """ROM writes [(offset, old, new)] that store `rgb` in this entry.

    Only ROM and code-value sources are written directly. Derived sources need
    locate_derived_source first.
    """
    if not swatch.editable:
        raise ValueError('This color is computed by the game; locate its source before editing.')
    if swatch.format == 'nes-index':
        best = min(range(64), key=lambda i: sum((a - b) ** 2 for a, b in zip(NES_RGB[i], rgb)) + (i & 0x0F in (0x0D, 0x0E, 0x0F)) * 10**6)
        new = bytes([(swatch.stored[0] & 0xC0) | best])
    elif swatch.format == 'dmg-shades':
        new = encode_palette([list(c) for c in rgb], 'dmg-shades', swatch.stored)
    else:
        new = encode_palette([list(rgb)], swatch.format, swatch.stored)
    writes = []
    for k, src in enumerate(swatch.sources):
        if new[k] == swatch.stored[k]:
            continue
        off = src['offset']
        if off >= len(rom) or rom[off] != swatch.stored[k]:
            raise ValueError('ROM byte at the traced source differs from the stored color; take a new scene.')
        writes.append((off, rom[off], new[k]))
    return writes


def locate_derived_source(verify, rom: bytes, swatch: Swatch, scene: Scene, radius: int = 3):
    """Find which ROM bytes near a derived tag actually change this entry.

    `verify(edited_rom)` must return romancer.provenance.verify_edit's result.
    Each candidate is checked by replaying the engine, so the answer is a
    measured effect, never a guess.
    """
    hits = []
    seen = set()
    for src in swatch.sources:
        if not src or src['kind'] != 'derived':
            continue
        for off in range(max(0, src['offset'] - radius), min(len(rom), src['offset'] + radius + 1)):
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
