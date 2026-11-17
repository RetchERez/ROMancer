"""Overlay fallback for the 8-bit processors graphics_trace did not cover: 6502 (NES) and Z80 (Master System).

graphics_trace.plan_overlay_patch calls into this module; use that entry
point. The idea is the one described there: a small routine on the
vertical-blank interrupt checks whether video memory holds exactly the
original tile and, if so, writes the edited one.

NES (6502), CHR-RAM cartridges only
    The NMI vector is pointed at the routine, which must sit in memory that
    is mapped whenever the interrupt can fire: the last 8 KB of the program
    ROM (16 KB on the boards that fix 16 KB there), or the same place in
    every 32 KB bank on boards that switch all of it. The routine reads and
    writes pattern memory through $2006/$2007. Those writes also move the
    picture chip's scroll latch, which a game cannot read back, so the
    routine runs before the game's own handler (which sets the scroll for the
    coming frame) and, when the game's scroll variables can be recognised in
    its code, ends by writing them the way the game does.

Master System (Z80)
    The interrupt entry at $0038 is pointed at the routine. It works only
    when the line counter says the picture is over (a game may also take
    line interrupts at $0038), and with `guard` it leaves a frame alone when
    the interrupted program holds the video data port in register C, the
    sign of a block transfer in progress. The routine goes into the first
    32 KB of the ROM where one fits; otherwise into any bank, or into ROM
    added at the end, behind a short stub that pages it in and restores the
    game's page from the mapper register's RAM mirror.

    Two variations. `after`: the work runs when the game's own handler has
    returned, for a tile the game itself writes every frame. `hook='poll'`:
    for a game that takes no interrupt and waits for the vertical blank by
    reading the status port in a loop; that loop becomes a call to the
    routine, which starts with the loop.

Every placement is a claim until verify_plan has replayed it.
"""
from __future__ import annotations

import re
from typing import Iterable

OVERLAY_NOTES = ['The game unpacks this tile in a way ROMancer does not decode, so the edit is applied '
                 'by a small added routine each frame instead of changing the stored data.',
                 'It applies wherever the game shows this exact tile in this tile slot.']


def _free(rom: bytes, size: int, lo: int, hi: int, *, zero_ends: Iterable[int] = (), avoid: Iterable[tuple[int, int]] = (),
          margin: int = 4, align: int = 1) -> int | None:
    """File offset of `size` unused bytes in [lo, hi): a run of FF, or a run of 00 that ends at one of `zero_ends`.

    `margin` bytes are kept from the data in front of the run. The smallest
    run that fits is used, so large runs stay available.
    """
    zero_ends = set(zero_ends)
    avoid = list(avoid)
    best = None
    for m in re.finditer(b'\xff+|\x00+', rom[lo:hi]):
        a, b = lo + m.start(), lo + m.end()
        if rom[a] == 0 and b not in zero_ends:
            continue
        start = a + margin
        start += -start % align
        if b - start < size or any(x < start + size and start < y for x, y in avoid):
            continue
        if best is None or b - a < best[0]:
            best = (b - a, start)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# NES
# ---------------------------------------------------------------------------

# Boards that switch the whole 32 KB of program ROM at once: the hook must exist in every bank.
_NES_SWITCH_32K = {7, 11, 13, 34, 66, 140}
# Boards whose last 16 KB never moves (others are trusted only for their last 8 KB).
_NES_FIXED_16K = {0, 1, 2, 3, 71, 94, 180}


def nes_scroll_shadow(prg: bytes) -> dict | None:
    """The variables a game writes to the scroll and control registers in its interrupt handler.

    Looks for `lda V1 ; sta $2005 ; lda V2 ; sta $2005` (zero-page or
    absolute operands) and for `lda V0 ; sta $2000`. Returns
    {'x': bytes, 'y': bytes, 'control': bytes or None}, each the `lda`
    instruction to repeat, or None when the game has no such code.
    """
    def load_before(at):
        if at >= 2 and prg[at - 2] == 0xA5:
            return bytes(prg[at - 2:at])
        if at >= 3 and prg[at - 3] == 0xAD and prg[at - 1] < 0x08:      # absolute, in the console's own RAM
            return bytes(prg[at - 3:at])
        return None

    found = None
    at = prg.find(b'\x8D\x05\x20')
    while at >= 0 and found is None:
        first = load_before(at)
        nxt = prg.find(b'\x8D\x05\x20', at + 3, at + 9)
        if first and nxt >= 0:
            second = load_before(nxt)
            if second and nxt - len(second) == at + 3:
                found = (first, second)
        at = prg.find(b'\x8D\x05\x20', at + 3)
    if not found:
        return None
    control = None
    at = prg.find(b'\x8D\x00\x20')
    while at >= 0 and control is None:
        control = load_before(at)
        at = prg.find(b'\x8D\x00\x20', at + 3)
    return {'x': found[0], 'y': found[1], 'control': control}


def nes_mask_shadow(prg: bytes) -> bytes | None:
    """The variable a game writes to the picture chip's mask register ($2001), as the `lda` instruction to repeat.

    Games keep the register's value in RAM because it cannot be read back,
    and write it with `lda V ; sta $2001`. The variable most often used that
    way is returned, or None when there is no such code.
    """
    seen: dict[bytes, int] = {}
    at = prg.find(b'\x8D\x01\x20')
    while at >= 0:
        if at >= 2 and prg[at - 2] == 0xA5:
            key = bytes(prg[at - 2:at])
            seen[key] = seen.get(key, 0) + 1
        elif at >= 3 and prg[at - 3] == 0xAD and prg[at - 1] < 0x08:
            key = bytes(prg[at - 3:at])
            seen[key] = seen.get(key, 0) + 1
        at = prg.find(b'\x8D\x01\x20', at + 3)
    return max(seen, key=seen.get) if seen else None


def _nes_routine(origin: int, records: bytes, resume: int, shadow: dict | None, null: bool = False,
                 mask: bytes | None = None) -> bytes:
    """6502 overlay routine at CPU address `origin`; ends with JMP to the game's handler.

    A record is: address high, low, the 16 original bytes, address high,
    low again, the 16 new bytes. The table ends with a byte of $80 or more.
    X indexes the table, so it holds at most seven records.

    `mask` is the game's `lda` of its mask-register variable (nes_mask_shadow):
    the routine then does nothing while that variable has the picture
    switched off. Games switch the picture off to load pattern memory from
    their main program, with the interrupt still running; using the address
    register then would send the rest of their data elsewhere.
    """
    if null:
        return b'\x4C' + resume.to_bytes(2, 'little')
    from .graphics_trace import _assemble

    def table(k):                     # operand: address of table + k
        return ('abs+', 'table', k)

    items = [
        b'\x48\x8A\x48\x98\x48',              # pha ; txa ; pha ; tya ; pha
    ]
    if mask:
        items += [mask + b'\x29\x18', ('jr', 0xF0, 'out')]   # lda V ; and #$18 ; beq out   (background and sprites both off)
    items += [
        b'\x2C\x02\x20',                      # bit $2002            (first write to $2006 is the high byte)
        b'\xA2\x00',                          # ldx #0
        ('label', 'rec'),
        b'\xBC', table(0),                    # ldy table,x
        ('jr', 0x30, 'done'),                 # bmi done
        b'\x20', ('abs', 'setaddr'),          # jsr setaddr
        b'\xAD\x07\x20',                      # lda $2007            (the read buffer)
        b'\xA0\x10',                          # ldy #16
        ('label', 'cmp'),
        b'\xAD\x07\x20', b'\xDD', table(2),   # lda $2007 ; cmp table+2,x
        ('jr', 0xD0, 'miss'),
        b'\xE8\x88', ('jr', 0xD0, 'cmp'),     # inx ; dey ; bne cmp
        b'\xE8\xE8',                          # inx ; inx            (x -> the second address)
        b'\x20', ('abs', 'setaddr'),
        b'\xA0\x10',
        ('label', 'cpy'),
        b'\xBD', table(2), b'\x8D\x07\x20',   # lda table+2,x ; sta $2007
        b'\xE8\x88', ('jr', 0xD0, 'cpy'),
        b'\xE8\xE8', ('jr', 0xD0, 'rec'),     # inx ; inx ; bne rec  (x is never 0 here)
        ('label', 'miss'),
        b'\xE8\x88', ('jr', 0xD0, 'miss'),    # skip the rest of the original bytes
        b'\x8A\x18\x69\x14\xAA',              # txa ; clc ; adc #20 ; tax
        ('jr', 0xD0, 'rec'),
        ('label', 'done'),
    ]
    if shadow:
        items.append(b'\x2C\x02\x20')         # bit $2002
        if shadow['control']:
            items.append(shadow['control'] + b'\x8D\x00\x20')
        items.append(shadow['x'] + b'\x8D\x05\x20' + shadow['y'] + b'\x8D\x05\x20')
    items += [
        ('label', 'out'),
        b'\x68\xA8\x68\xAA\x68',              # pla ; tay ; pla ; tax ; pla
        b'\x4C' + resume.to_bytes(2, 'little'),
        ('label', 'setaddr'),
        b'\xBD', table(0), b'\x8D\x06\x20',   # lda table,x ; sta $2006
        b'\xBD', table(1), b'\x8D\x06\x20',   # lda table+1,x ; sta $2006
        b'\x60',
        ('label', 'table'), records, b'\xFF',
    ]
    # graphics_trace._assemble knows ('abs', label); resolve ('abs+', label, k) here in two passes.
    def build(labels):
        plain = []
        for it in items:
            if isinstance(it, tuple) and it[0] == 'abs+':
                plain.append(((origin + labels.get(it[1], 0) + it[2]) & 0xFFFF).to_bytes(2, 'little'))
            else:
                plain.append(it)
        return plain
    labels = {}
    for _ in range(2):
        pos = 0
        for it in build(labels):
            if isinstance(it, (bytes, bytearray)):
                pos += len(it)
            elif it[0] == 'label':
                labels[it[1]] = pos
            else:
                pos += 2
    return _assemble(build(labels), origin)


def nes_overlay_patch(edits, rom: bytes, system: str, avoid=(), null: bool = False, guard: bool = True):
    from .graphics_trace import EditPlan, _diff_writes, encode_tile
    if rom[:4] != b'NES\x1a':
        raise ValueError('Not an iNES ROM image.')
    if rom[5] != 0 and not null:
        raise ValueError('This cartridge keeps its tiles in ROM (CHR-ROM): they are edited in place, not by an overlay.')
    mapper = (rom[6] >> 4) | (rom[7] & 0xF0)
    head = 16 + (512 if rom[6] & 4 else 0)
    prg_size = rom[4] * 0x4000
    if prg_size < 0x4000 or len(rom) < head + prg_size:
        raise ValueError('Not an iNES ROM image.')
    prg = rom[head:head + prg_size]
    records = bytearray()
    expect: dict[int, int] = {}
    for tile, pixels in edits:
        new = encode_tile(pixels, tile.format) if not isinstance(pixels, (bytes, bytearray)) else bytes(pixels)
        a = tile.addresses[0]
        if tile.domain != 'chr' or len(tile.stored) != 16 or len(new) != 16 or tile.addresses[-1] - a != 15 or a >= 0x2000:
            raise ValueError('The overlay edits 16-byte tiles in pattern memory (CHR-RAM).')
        diff = [k for k in range(16) if new[k] != tile.stored[k]]
        if not diff:
            continue
        address = bytes((a >> 8, a & 0xFF))
        records += address + tile.stored + address + new
        expect.update({a + k: new[k] for k in diff})
    if not records and not null:
        raise ValueError('The edit changes nothing.')
    if len(records) > 7 * 36:
        raise ValueError('The NES overlay handles at most seven tiles at a time.')
    # Where the vectors live: one copy per 32 KB bank on boards that switch it all, else the end of the image
    # (and the end of each 256 KB half on the large MMC1 boards, which select the half with a CHR register).
    if mapper in _NES_SWITCH_32K:
        ends = list(range(0x8000, prg_size + 1, 0x8000))
        reach = 0x2000
    elif mapper == 1 and prg_size == 0x80000:
        ends, reach = [0x40000, 0x80000], 0x4000
    else:
        ends, reach = [prg_size], (0x4000 if mapper in _NES_FIXED_16K else 0x2000)
    handlers = {prg[e - 6] | prg[e - 5] << 8 for e in ends}
    if len(handlers) != 1:
        raise ValueError('The program banks of this cartridge do not share one interrupt handler.')
    handler = handlers.pop()
    if handler in (0x0000, 0xFFFF):
        raise ValueError('This game has no vertical-blank interrupt handler to hook.')
    shadow = None if null else nes_scroll_shadow(prg)
    mask = nes_mask_shadow(prg) if guard and not null else None
    first = ends[0]
    taken = [(a - head, b - head) for a, b in avoid]

    def place(size):
        """Bank-relative position of `size` free bytes that are free at every vector copy, or None."""
        for m in re.finditer(b'\xff+|\x00+', prg[first - reach:first - 6]):
            a, b = first - reach + m.start(), first - reach + m.end()
            if prg[a] == 0 and b != first - 6:
                continue
            start = a + 4
            if b - start < size:
                continue
            rel = start - first
            if all(prg[e + rel - 4:e + rel + size] == prg[first + rel - 4:first + rel + size] for e in ends) and \
                    not any(x < e + rel + size and e + rel < y for e in ends for x, y in taken):
                return rel
        return None
    size = len(_nes_routine(0, bytes(records), handler, shadow, null, mask))
    where = place(size)
    if where is None and shadow:
        # No room for the version that sets the scroll again itself: fall back to leaving that to the game's handler.
        smaller = len(_nes_routine(0, bytes(records), handler, None, null, mask))
        where = place(smaller)
        if where is not None:
            shadow = None
    if where is None:
        raise ValueError(f'The part of the program ROM that is always mapped has no {size} free bytes for the overlay routine.')
    origin = 0x10000 + where
    code = _nes_routine(origin, bytes(records), handler, shadow, null, mask)
    edited = bytearray(rom)
    for e in ends:
        at = head + e + where
        edited[at:at + len(code)] = code
        edited[head + e - 6:head + e - 4] = origin.to_bytes(2, 'little')
    notes = list(OVERLAY_NOTES)
    if not null:
        notes.append('The routine uses the picture chip\'s address register, which also holds the scroll position. '
                     + ('It ends by setting the scroll from the game\'s own scroll variables.' if shadow else
                        'It runs before the game\'s own handler, which sets the scroll for the coming frame; a game that '
                        'skips that in some frames would show a scroll jump there.'))
    return EditPlan('hook-only' if null else 'overlay', _diff_writes(rom, bytes(edited)), len(edited), {'chr': expect}, notes=notes,
                    details={'routine_size': len(code), 'routine_offset': head + ends[-1] + where, 'copies': len(ends),
                             'hook_offset': head + ends[-1] - 6, 'placement': 'fixed-bank' if len(ends) == 1 else 'every-bank',
                             'tiles': len(records) // 36, 'cpu': '6502', 'handler': handler, 'mapper': mapper,
                             'scroll': 'restored from the game\'s variables' if shadow else 'left to the game\'s handler',
                             'guard': 'does nothing while the game\'s mask variable has the picture switched off' if mask
                                      else 'none'})


# ---------------------------------------------------------------------------
# Master System
# ---------------------------------------------------------------------------

def z80_length(code: bytes, i: int) -> int | None:
    """Length of the Z80 instruction at code[i], or None for the prefixes this module does not move (DD, FD)."""
    op = code[i]
    if op == 0xCB:
        return 2
    if op == 0xED:
        return 4 if code[i + 1] in (0x43, 0x4B, 0x53, 0x5B, 0x63, 0x6B, 0x73, 0x7B) else 2
    if op in (0xDD, 0xFD):
        return None
    x, y, z = op >> 6, op >> 3 & 7, op & 7
    if x == 0:
        if z == 0:
            return 1 if y < 2 else 2
        if z == 1:
            return 1 if y & 1 else 3
        if z == 2:
            return 3 if y >= 4 else 1
        return 2 if z == 6 else 1
    if x in (1, 2):
        return 1
    if z in (2, 4):
        return 3
    if z == 3:
        return (3, 2, 2, 2, 1, 1, 1, 1)[y]
    if z == 5:
        return 3 if y == 1 else 1
    return 2 if z == 6 else 1


def _z80_displace(rom: bytes, at: int, need: int = 3) -> tuple[bytes, int]:
    """(code that does what rom[at:at+covered] did and then continues after it, covered) for a 3-byte jump at `at`."""
    if rom[at] in (0xFF, 0x00) and rom[at + 1] == rom[at] and rom[at + 2] == rom[at]:
        raise ValueError('This game has no interrupt handler at $0038 to hook.')
    covered = 0
    moved = bytearray()
    while covered < need:
        op = rom[at + covered]
        n = z80_length(rom, at + covered)
        if n is None or (op in (0x10, 0x20, 0x28, 0x30, 0x38)):
            raise ValueError('The interrupt handler starts with code that cannot be moved.')
        if op == 0x18:      # jr e: the same jump, absolute
            e = rom[at + covered + 1]
            return bytes(moved) + b'\xC3' + ((at + covered + 2 + (e - 256 if e & 0x80 else e)) & 0xFFFF).to_bytes(2, 'little'), covered + 2
        moved += rom[at + covered:at + covered + n]
        covered += n
        if op in (0xC3, 0xC9, 0xE9) or (op == 0xED and rom[at + covered - 1] in (0x45, 0x4D)):
            return bytes(moved), covered
    return bytes(moved) + b'\xC3' + (at + covered).to_bytes(2, 'little'), covered


def _z80_work(records: bytes) -> list:
    """The record loop. A record is: key address high, low, key value, tile address low, high, 32 old, 32 new."""
    return [
        b'\x21', ('abs', 'table'),            # ld hl,table
        ('label', 'next'),
        b'\x7E\xFE\xFF', ('jr', 0x28, 'done'),   # ld a,(hl) ; cp $FF ; jr z,done
        b'\x57\x23\x7E\x23',                  # ld d,a ; inc hl ; ld a,(hl) ; inc hl
        b'\xD3\xBF\x7A\xD3\xBF',              # out ($BF),a ; ld a,d ; out ($BF),a     (read from the key address)
        b'\xDB\xBE\xBE\x23',                  # in a,($BE) ; cp (hl) ; inc hl          (inc hl keeps the flags)
        b'\x5E\x23\x56\x23',                  # ld e,(hl) ; inc hl ; ld d,(hl) ; inc hl
        ('jr', 0x20, 'skip64'),
        b'\x7B\xD3\xBF\x7A\xD3\xBF',          # ld a,e ; out ($BF),a ; ld a,d ; out ($BF),a
        b'\x06\x20',                          # ld b,32
        ('label', 'cmp'),
        b'\xDB\xBE\xBE', ('jr', 0x20, 'skipb'), b'\x23', ('jr', 0x10, 'cmp'),   # in a,($BE) ; cp (hl) ; jr nz ; inc hl ; djnz
        b'\x7B\xD3\xBF\x7A\xF6\x40\xD3\xBF',  # ld a,e ; out ($BF),a ; ld a,d ; or $40 ; out ($BF),a   (write)
        b'\x06\x20',
        ('label', 'cpy'),
        b'\x7E\xD3\xBE\x23', ('jr', 0x10, 'cpy'),   # ld a,(hl) ; out ($BE),a ; inc hl ; djnz
        ('jr', 0x18, 'next'),
        ('label', 'skipb'),
        b'\x78\xC6\x20', ('jr', 0x18, 'adv'),  # ld a,b ; add a,32
        ('label', 'skip64'),
        b'\x3E\x40',                          # ld a,64
        ('label', 'adv'),
        b'\x85\x6F', ('jr', 0x30, 'next'), b'\x24', ('jr', 0x18, 'next'),   # add a,l ; ld l,a ; jr nc ; inc h
        ('label', 'done'),
    ]


_Z80_VBLANK = [b'\xDB\x7E\xFE\xC0', ('jr', 0x38, 'out')]         # in a,($7E) ; cp $C0 ; jr c,out   (picture still being drawn)
_Z80_GUARD = [b'\x79\xFE\xBE', ('jr', 0x28, 'out')]               # ld a,c ; cp $BE ; jr z,out       (a block transfer is under way)


def _z80_direct(origin: int, records: bytes, tail: bytes, guard: bool, wait=None, after: bool = False) -> bytes:
    """The whole routine at `origin`. `wait` (a function of the address it will sit at) is the game's own
    wait-for-vertical-blank loop when the routine is called from that wait instead of from the interrupt.

    With `after`, the routine first calls on into the game's handler (`tail`), leaving its own work as the
    address that handler returns to: the work then runs when the game's handler has finished, after any tile
    the game itself writes each frame, and its own `ret` goes back to the interrupted program.
    """
    from .graphics_trace import _assemble
    head = [wait(origin), b'\xF5'] if wait else [b'\xF5'] + _Z80_VBLANK + (_Z80_GUARD if guard else [])
    if after:
        head = [b'\xCD', ('abs', 'handler')] + head                # call handler   (it returns to the work below)
    items = head + [b'\xC5\xD5\xE5'] + _z80_work(records) + [b'\xE1\xD1\xC1', ('label', 'out'), b'\xF1']
    items += [b'\xC9', ('label', 'handler'), tail] if after else [tail]
    items += [('label', 'table'), records, b'\xFF']
    return _assemble(items, origin)


def _z80_body(origin: int, records: bytes, guard: bool) -> bytes:
    from .graphics_trace import _assemble
    items = (_Z80_GUARD if guard else []) + [b'\xC5\xD5\xE5'] + _z80_work(records) + [
        b'\xE1\xD1\xC1', ('label', 'out'), b'\xC9', ('label', 'table'), records, b'\xFF']
    return _assemble(items, origin)


_SMS_POLLS = (
    # (the loop as it stands in the ROM, with None for the two bytes of its own address)
    (b'\xDB\xBF\x07\x30\xFB', False),          # in a,($BF) ; rlca ; jr nc,*-3
    (b'\xDB\xBF\xE6\x80\x28\xFA', False),      # in a,($BF) ; and $80 ; jr z,*-4
    (b'\xDB\xBF\xB7\xF2', True),               # in a,($BF) ; or a ; jp p,(the in)
)


def sms_poll_sites(rom: bytes, most: int = 8):
    """Places where a game waits for the vertical blank by reading the status port in a loop.

    Returns (file offsets, length of the loop in bytes, function giving the
    loop's bytes for the address it is moved to), for the form found most
    often, or ([], 0, None). Only loops in the first 32 KB are taken, where
    a file offset is also the address the loop runs at.
    """
    best = ([], 0, None)
    for head, absolute in _SMS_POLLS:
        found = []
        at = rom.find(head, 0, 0x8000)
        while at >= 0:
            if not absolute or rom[at + 4:at + 6] == at.to_bytes(2, 'little'):
                found.append(at)
            at = rom.find(head, at + 1, 0x8000)
        if len(best[0]) < len(found) <= most:
            best = (found, len(head) + (2 if absolute else 0),
                    (lambda origin, head=head: head + origin.to_bytes(2, 'little')) if absolute else (lambda origin, head=head: head))
    return best


def _z80_stub(bank: int, entry: int, tail: bytes, wait=None, origin: int = 0, after: bool = False) -> bytes:
    from .graphics_trace import _assemble
    items = [b'\xCD', ('abs', 'handler')] if after else []
    items += ([wait(origin), b'\xF5'] if wait else [b'\xF5'] + _Z80_VBLANK) + [
        b'\x3A\xFF\xFF\xF5',                              # ld a,($FFFF) ; push af      (the game's page, from the register's RAM mirror)
        b'\x3E', bytes([bank]), b'\x32\xFF\xFF',          # ld a,bank ; ld ($FFFF),a
        b'\xCD', entry.to_bytes(2, 'little'),             # call the routine
        b'\xF1\x32\xFF\xFF',                              # pop af ; ld ($FFFF),a
        ('label', 'out'), b'\xF1']
    items += [b'\xC9', ('label', 'handler'), tail] if after else [tail]
    return _assemble(items, origin)


def sms_slot1_is_paged(rom: bytes, scene=None) -> bool:
    """True when the game appears to page the second 16 KB of its address space ($4000-$7FFF).

    Signs: a store to the page register $FFFE that is not the usual start-up
    `ld a,1 ; ld ($FFFE),a`, a 16-bit store that covers it, or, given a
    scene, a value other than 1 (or the never-written 0) in the register's
    RAM mirror at that moment.
    """
    at = rom.find(b'\x32\xFE\xFF')
    while at >= 0:
        if rom[max(0, at - 2):at] != b'\x3E\x01':
            return True
        at = rom.find(b'\x32\xFE\xFF', at + 1)
    for pattern in (b'\x22\xFD\xFF', b'\x22\xFE\xFF', b'\xED\x43\xFE\xFF', b'\xED\x53\xFE\xFF', b'\xED\x73\xFE\xFF'):
        if pattern in rom:
            return True
    if scene is not None:
        ram = scene.snapshot.domains.get('wram')
        if ram is not None and ram.data is not None and len(ram.data) >= 0x2000 and ram.data[0x1FFE] not in (0, 1):
            return True
    return False


def sms_overlay_patch(edits, rom: bytes, system: str, avoid=(), guard: bool = True, grow: bool = True, null: bool = False,
                      scene=None, hook: str = 'irq', after: bool = False):
    """`hook='poll'`: for a game that waits for the vertical blank by reading the status port in a loop instead
    of taking the interrupt. Each such loop becomes a call to the routine, which begins with the loop.
    `after`: the work runs when the game's interrupt handler has returned instead of before it starts (for a
    tile the game itself writes every frame)."""
    from .graphics_trace import EditPlan, _diff_writes, encode_tile, fix_checksums
    if len(rom) < 0x4000:
        raise ValueError('Not a Master System ROM image.')
    poll = hook == 'poll'
    after = after and not poll and not null
    sites, site_size, wait = sms_poll_sites(rom) if poll else ([], 0, None)
    if poll and not sites:
        raise ValueError('This game has no loop that waits for the vertical blank by reading the status port.')
    records = bytearray()
    expect: dict[int, int] = {}
    for tile, pixels in edits:
        new = encode_tile(pixels, tile.format) if not isinstance(pixels, (bytes, bytearray)) else bytes(pixels)
        a = tile.addresses[0]
        if tile.domain != 'vram' or len(tile.stored) != 32 or len(new) != 32 or tile.addresses[-1] - a != 31 or a + 32 > 0x4000:
            raise ValueError('The overlay edits whole 32-byte tiles in video memory.')
        diff = [k for k in range(32) if new[k] != tile.stored[k]]
        if not diff:
            continue
        key = a + diff[0]
        records += bytes((key >> 8, key & 0xFF, tile.stored[diff[0]], a & 0xFF, a >> 8)) + tile.stored + new
        expect.update({a + k: new[k] for k in diff})
    if not records and not null:
        raise ValueError('The edit changes nothing.')
    records = bytes(records)
    vector = 0x38
    if poll:
        tail, guard = b'\xC9', False                 # the routine is called, so it ends with ret; nothing is interrupted
        try:
            covered = _z80_displace(rom, vector)[1]
        except ValueError:
            covered = 0x66 + 3 - vector              # no usable interrupt entry: look for free bytes behind $0066
    else:
        tail, covered = _z80_displace(rom, vector)
    notes = list(OVERLAY_NOTES)
    details = {'hook_offset': sites[0] if poll else vector, 'hook': hook, 'tiles': len(records) // 69, 'cpu': 'z80',
               'timing': 'after the game\'s handler' if after else 'before the game\'s handler',
               'guard': 'skips frames in which the interrupted program holds the video data port in register C' if guard else 'none'}

    def install(target):
        """Point the game at the routine (or its stub) at address `target`."""
        if not poll:
            edited[vector:vector + 3] = b'\xC3' + target.to_bytes(2, 'little')
            return
        for at in sites:
            edited[at:at + site_size] = b'\xCD' + target.to_bytes(2, 'little') + bytes(site_size - 3)   # call ; nop ...
        details['hook_sites'] = len(sites)
        notes.append(f'This game waits for the vertical blank in a loop instead of taking the interrupt; the routine '
                     f'is called from that wait ({len(sites)} place(s) in the ROM).')
    edited = bytearray(rom)
    low_end = min(len(rom), 0x8000)
    header = 0x7FF0 if rom[0x7FF0:0x7FF8] == b'TMR SEGA' else None
    zero_ends = {0x4000, 0x8000} | ({header} if header else set())
    # Free bytes are looked for from just behind the hook itself; the pause handler's entry at $0066 stays.
    low = vector + covered
    avoid = list(avoid) + [(0x66, 0x69)] + [(at, at + site_size) for at in sites]
    if null:
        size = len(tail) + site_size
        where = _free(rom, size, low, low_end, zero_ends=zero_ends, avoid=avoid)
        if where is None:
            raise ValueError('The first 32 KB of the ROM have no free bytes for the hook.')
        edited[where:where + size] = (wait(where) if poll else b'') + tail
        install(where)
        final = fix_checksums(bytes(edited), rom, system)
        return EditPlan('hook-only', _diff_writes(rom, final), len(final), {'vram': {}}, details={**details, 'routine_offset': where})
    size = len(_z80_direct(0, records, tail, guard, wait, after))
    # Where the processor always sees it: bank 0 for certain; bank 1 as long as the game never pages the second
    # 16 KB. Order: the whole routine in bank 0; in bank 1 when nothing suggests that the game pages it; a stub
    # in bank 0 with the routine paged in at $8000; and only then bank 1 for a game that does seem to page it
    # (the replay, and a run from power-on, show whether that holds).
    has_bank1 = len(rom) >= 0x8000
    paged1 = has_bank1 and sms_slot1_is_paged(rom, scene)
    mapper = len(rom) >= 0xC000
    body_size = len(_z80_body(0x8000, records, guard))
    stub_size = len(_z80_stub(0, 0x8000, tail, wait, 0, after))

    def bank1(n):
        return _free(rom, n, 0x4000, header or 0x8000, zero_ends=zero_ends, avoid=avoid) if has_bank1 else None
    where = _free(rom, size, low, min(low_end, 0x4000), zero_ends=zero_ends, avoid=avoid)
    stub = None
    if where is None and not paged1:
        where = bank1(size)
    if where is None and mapper:
        stub = _free(rom, stub_size, low, min(low_end, 0x4000), zero_ends=zero_ends, avoid=avoid)
        if stub is None and not paged1:
            stub = bank1(stub_size)
    if where is None and stub is None and paged1:
        where = bank1(size)
        if where is None and mapper:
            stub = bank1(stub_size)
    if (where is not None and where >= 0x4000) or (stub is not None and stub >= 0x4000):
        details['assumes'] = 'the second 16 KB of the ROM stays mapped at $4000-$7FFF'
        notes.append('The routine is reached through the second 16 KB of the ROM, which '
                     + ('this game appears to keep mapped at all times.' if not paged1 else
                        'this game may page out; the replay and a run from power-on show whether it does while the '
                        'interrupt can fire.'))
    if where is not None:
        code = _z80_direct(where, records, tail, guard, wait, after)
        edited[where:where + len(code)] = code
        install(where)
        details.update(placement='bank0' if where < 0x4000 else 'bank1', routine_offset=where, routine_size=len(code))
    else:
        # a stub where the processor always sees it, the routine in any bank paged in at $8000
        if not mapper:
            raise ValueError(f'The ROM has no {size} free bytes for the overlay routine and no mapper to page more in.')
        if stub is None:
            raise ValueError(f'The part of the ROM that is always mapped has no {stub_size} free bytes for the overlay stub.')
        body = None
        for bank in range(2, len(rom) // 0x4000):
            body = _free(rom, body_size, bank * 0x4000, (bank + 1) * 0x4000, zero_ends={(bank + 1) * 0x4000},
                         avoid=avoid + [(stub, stub + stub_size)])
            if body is not None:
                break
        placement = 'paged'
        if body is None and grow and len(rom) < 0x100000 and len(rom) & (len(rom) - 1) == 0:
            body = len(rom) + 4
            edited += b'\xFF' * len(rom)
            placement = 'paged-added'
            notes.append(f'The ROM has no free space for the routine, so it grows from {len(rom) >> 10} KB to {len(edited) >> 10} KB.')
        if body is None:
            raise ValueError(f'The ROM has no {body_size} free bytes for the overlay routine' + (' and cannot grow.' if grow else '.'))
        bank = body // 0x4000
        if bank > 0xFF:
            raise ValueError('The overlay routine would land in a bank the mapper cannot select.')
        entry = 0x8000 + (body & 0x3FFF)
        code = _z80_body(entry, records, guard)
        edited[body:body + len(code)] = code
        stub_code = _z80_stub(bank, entry, tail, wait, stub, after)
        edited[stub:stub + len(stub_code)] = stub_code
        install(stub)
        details.update(placement=placement + ('' if stub < 0x4000 else '-stub1'), routine_offset=body, routine_size=len(code),
                       stub_offset=stub, stub_size=len(stub_code))
        notes.append(f'The routine sits in ROM bank {bank}; a stub pages it in at $8000 and then restores the game\'s page '
                     'from the copy the mapper keeps at $FFFF.')
    final = fix_checksums(bytes(edited), rom, system)
    return EditPlan('overlay', _diff_writes(rom, final), len(final), {'vram': expect}, notes=notes, details=details)
