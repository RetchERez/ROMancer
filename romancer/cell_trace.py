"""Background (map cell) edits, by whichever stored form the replay confirms.

A background cell names the tile it shows. graphics_trace reads the cells of
a scene and, for each stored byte, the ROM byte it came from. This module
plans a change to one cell and confirms it by replaying the real engine.

    tile_status(cell)        where the cell's tile number comes from ('rom', 'code', 'derived', 'unknown')
    cell_bytes(cell, ...)    the bytes the cell would store after a change
    map_area(layers)         {domain: set of byte indices} that hold background cells
    plan_cell_edit(...)      -> graphics_trace.EditPlan, confirmed by replay

plan_cell_edit tries, in this order:

direct        the changed bytes of the cell are ROM bytes (or code values): written in place.
reencode      the map is packed in the ROM with a codec ROMancer knows: unpacked, changed, packed again
              (graphics_trace.find_compressed_block / plan_block_edit).
cell-source   the game builds the cell from a stored piece: a block (metatile) definition, a table the
              game adds a base to, or a literal inside packed data. The traced tag of a computed byte names
              the last ROM byte read before it was written. The ROM bytes at and around it are tried one
              at a time: the byte is moved by as much as the cell has to move, the scene is replayed, and
              the place counts only when the cell then holds exactly the planned value. Every other cell
              built from the same stored piece changes with it; the plan lists them (`also_cells`), and it
              is refused when anything outside the background maps changes. A place the game adds to the
              cell (rather than copies) is also refused when a quarter of the layer moves with it: that is
              the base the game adds to every cell it draws, not a piece of this background.

A plan is returned only when the replay showed the planned bytes in video
memory. Nothing here is a guess that reaches the user unconfirmed.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Iterable

from . import graphics_trace as gt

PATHS = ('direct', 'reencode', 'cell-source')


def tile_bytes(cell) -> list[int]:
    """Indices into cell.stored of the bytes that hold the tile number, lowest eight bits first."""
    if cell.system in ('gb', 'gbc', 'nes') or len(cell.stored) == 1:
        return [0]
    return [1, 0] if cell.system == 'genesis' else [0, 1]


def tile_source(cell):
    """The traced source of the byte that holds the low eight bits of the tile number (or None)."""
    k = tile_bytes(cell)[0]
    return cell.sources[k] if k < len(cell.sources) else None


def tile_status(cell) -> str:
    """Where the cell's tile number comes from: 'rom', 'code', 'derived' or 'unknown'.

    MapCell.status covers every stored byte of the cell. On the NES the
    second byte is the attribute byte of a 4x4 block, which games compute;
    on the 16-bit systems the upper byte often has a palette or priority bit
    added. Which picture the cell shows is the tile number, and its low byte
    is very often a plain ROM byte even then.
    """
    src = tile_source(cell)
    return src['kind'] if src else 'unknown'


def cell_bytes(cell, **options) -> bytes:
    """The bytes `cell` would store with `options` (tile, hflip, vflip, palette, priority) applied.

    graphics_trace.plan_tilemap_edit owns the encoding; it is read here from
    the writes it plans against a stand-in ROM that is the cell itself.
    """
    size = len(cell.stored)
    marked = replace(cell, sources=[{'offset': k, 'kind': 'rom', 'weak': False, 'pc': 0} for k in range(size)])
    new = bytearray(cell.stored)
    for offset, _, value in gt.plan_tilemap_edit(marked, bytes(cell.stored) + bytes(size), skip=0, **options):
        new[offset] = value
    return bytes(new)


def map_area(layers: Iterable, system: str = '') -> dict:
    """{domain: set of byte indices} holding background cells (every layer of the scene).

    The Game Boy keeps two maps in fixed places and a game may show either,
    so both count there whatever the registers say right now.
    """
    area: dict = {}
    for layer in layers:
        for c in layer.cells:
            area.setdefault(c.domain, set()).update(c.addresses)
    if system in ('gb', 'gbc'):
        area.setdefault('vram', set()).update(range(0x1800, 0x2000))
        if system == 'gbc':
            area['vram'].update(range(0x3800, 0x4000))
    return area


def side_effects(result: dict, expect: dict, layers: Iterable, system: str = '') -> dict:
    """What a replay changed besides the planned bytes.

    Returns {'also_cells': [[layer name, x, y], ...], 'outside_maps': n}:
    other background cells that changed, and how many changed bytes are
    not part of any background map.
    """
    layers = list(layers)
    area = map_area(layers, system)
    by_address = {}
    for layer in layers:
        for c in layer.cells:
            for a in c.addresses:
                by_address.setdefault((c.domain, a), []).append((layer.name, c.x, c.y))
    cells, outside = [], 0
    seen = set()
    for name, indices in (result.get('changed') or {}).items():
        planned = {int(i) for i in (expect.get(name) or {})}
        for i in indices:
            if i in planned:
                continue
            if i not in area.get(name, ()):
                outside += 1
                continue
            for key in by_address.get((name, i), ()):
                if key not in seen:
                    seen.add(key)
                    cells.append(list(key))
    return {'also_cells': cells, 'outside_maps': outside}


def _source_candidates(cell, k: int, rom: bytes, skip: int, radius: int) -> list[int]:
    """File offsets worth trying for stored byte k, likeliest first.

    At and around the traced offset of the byte itself, then around those of
    the cell's other bytes. A place whose ROM byte already equals the stored
    value comes before one that would need a constant added.
    """
    have = cell.stored[k]
    anchors = []
    for src in [cell.sources[k]] + [s for j, s in enumerate(cell.sources) if j != k]:
        if src and src['offset'] + skip not in anchors:
            anchors.append(src['offset'] + skip)
    ranked = []
    for rank, anchor in enumerate(anchors):
        for dist in range(-radius, radius + 1):
            off = anchor + dist
            if not skip <= off < len(rom):
                continue
            ranked.append(((rom[off] != have, rank, abs(dist), dist < 0), off))
    out = []
    for _, off in sorted(ranked):
        if off not in out:
            out.append(off)
    return out


def plan_cell_edit(cell, new: bytes, rom: bytes, scene, system: str, *, verify: Callable, layers: Iterable | None = None,
                   paths: Iterable[str] = PATHS, radius: int = 3, max_probes: int = 6, max_candidates: int = 6,
                   avoid: Iterable[tuple[int, int]] = ()) -> gt.EditPlan:
    """Make `cell` store `new`, confirmed by replay. Raises ValueError (saying what was tried) when no path is.

    `verify(plan, expect)` must return graphics_trace.verify_plan's result
    for an EditPlan replayed in `scene`. The returned plan has
    plan.verified set, plan.kind naming the path, and plan.details with
    'also_cells' / 'outside_maps' (side_effects) and 'tried'.
    """
    new = bytes(new)
    changed = [k for k in range(len(cell.stored)) if new[k] != cell.stored[k]]
    if not changed:
        raise ValueError('The cell already stores that.')
    layers = list(layers) if layers is not None else gt.layers(scene, system)
    skip = gt.rom_skip(rom, system)
    expect = {cell.domain: {cell.addresses[k]: new[k] for k in changed}}
    tried = []

    def finish(plan, path):
        plan.details.update(side_effects(plan.verified, expect, layers, system))
        plan.details['tried'] = tried + [path]
        plan.details['path'] = path
        others = len(plan.details['also_cells'])
        if others:
            plan.notes.append(f'{others} other background cell{"s" if others != 1 else ""} in this scene '
                              f'change{"" if others != 1 else "s"} with it: the game builds them from the same stored piece.')
        return plan

    if 'direct' in paths and all(cell.sources[k] and cell.sources[k]['kind'] in ('rom', 'code') for k in changed):
        try:
            writes = gt._direct_writes(cell.stored, new, cell.sources, rom, skip, 'map cell')
        except ValueError as e:
            tried.append(f'direct: {e}')
        else:
            plan = gt.EditPlan('direct', gt.with_checksums(rom, writes, system), len(rom), expect)
            if verify(plan, expect).get('as_planned'):
                return finish(plan, 'direct')
            tried.append('direct: the replay did not show the cell as planned')

    if 'reencode' in paths:
        low, high = min(cell.addresses[k] for k in changed), max(cell.addresses[k] for k in changed)
        block = None
        try:
            block = gt.find_compressed_block(scene, rom, system, cell.domain, low, high - low + 1)
        except (ValueError, IndexError, KeyError):
            block = None
        if block is None:
            tried.append('reencode: no packed data ROMancer knows produced this part of the map')
        else:
            try:
                plan = gt.plan_block_edit(block, expect[cell.domain], rom, system, verify=lambda p: verify(p, p.expect),
                                          avoid=avoid, max_candidates=max_candidates)
                if verify(plan, expect).get('as_planned'):
                    return finish(plan, 'reencode')
                tried.append(f'reencode ({block.codec}): the replay did not show the cell as planned')
            except (ValueError, IndexError, KeyError) as e:
                tried.append(f'reencode ({block.codec}): {str(e)[:120]}')

    if 'cell-source' in paths and len(changed) == 1:
        k = changed[0]
        delta = (new[k] - cell.stored[k]) & 0xFF
        whole = max([len(layer.cells) for layer in layers if layer.name == cell.layer] or [1024])
        probes = 0
        for off in _source_candidates(cell, k, rom, skip, radius):
            if probes >= max_probes:
                break
            probes += 1
            value = (rom[off] + delta) & 0xFF
            plan = gt.EditPlan('cell-source', gt.with_checksums(rom, [(off, rom[off], value)], system), len(rom), expect,
                               details={'source_offset': off, 'relation': 'copy' if rom[off] == cell.stored[k] else 'offset'})
            result = verify(plan, expect)
            if not result.get('as_planned'):
                continue
            effects = side_effects(result, expect, layers, system)
            if effects['outside_maps']:
                tried.append(f'cell-source at {off:#x}: the cell came out as planned, but {effects["outside_maps"]} bytes '
                             'outside the background maps changed too')
                continue
            if plan.details['relation'] == 'offset' and len(effects['also_cells']) > whole // 4:
                tried.append(f'cell-source at {off:#x}: the cell came out as planned, but so did {len(effects["also_cells"])} '
                             'other cells: the byte is a base the game adds to every cell, not a piece of this background')
                continue
            plan.notes.append('The game builds this cell from a stored piece; the piece was changed.')
            return finish(plan, 'cell-source')
        tried.append(f'cell-source: none of {probes} ROM bytes around the traced source gave the planned cell')
    elif 'cell-source' in paths:
        tried.append('cell-source: more than one stored byte of the cell would have to change')
    raise ValueError('No way of changing this background cell was confirmed by replaying the game. Tried: ' + '; '.join(tried))
