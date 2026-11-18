"""Graphics compression codecs used by 8- and 16-bit console games.

Every codec is a pair of pure functions:

    decode(data, start=0, limit=0x10000) -> (decoded bytes, bytes consumed)
    encode(decoded) -> stream bytes

`decode` raises ValueError when the bytes at `start` are not a valid stream.
`encode` output always round-trips through `decode`. Some encoders find the
cheapest parse and some are plain greedy ones, so a stream may come out larger
than the original game's packer made it (the block is then moved).
romancer.graphics_trace matches these decoders against traced video memory
to recognise a compressed block, and re-encodes the block after an edit.

Families:
  lz2, lz2-le      Nintendo LC_LZ2 (Super Mario World / Zelda 3 offset order)
  lz3              Nintendo LC_LZ3 (Pokemon Gold/Silver/Crystal and relatives)
  lz5              Nintendo LC_LZ5 (Super Metroid)
  konami-snes      Konami on the Super NES (Castlevania IV, Contra III, Gradius III, Turtles in Time, ...)
  hal              HAL Laboratory (Kirby, Adventures of Lolo, EarthBound)
  lzss-*           Okumura LZSS ring buffer, fill 00 or 20, optional 16-bit size
  kosinski         Sega Kosinski
  nemesis          Sega Nemesis (nibble run-length with a prefix code)
  enigma           Sega Enigma (tilemap words)
  packbits         PackBits run-length
  rle-konami       Konami run-length (NES era)
  rle-pairs        (count, value) pairs, zero count ends
  rle-escape       runs behind an escape byte named by the stream's first byte (Capcom, Game Boy)
  comper           Sega Comper (word LZ)
  kosinski-moduled Sega Kosinski in 4 KB modules (Sonic 3 & Knuckles)
  saxman           Sega Saxman (Okumura LZSS behind a packed-size word)
  rle-sega-planes  Sega Master System plane run-length (Phantasy Star and many more)
  rnc1, rnc2       "RNC" streams, methods 1 and 2 (gfx_packers)
  raw              stored as it is
  lz~... rle~...   members of the parameterised families in gfx_families, named by their parameters
  <codec>|<map>    any codec whose output the game lays into video memory with made-up
                   planes (3bpp, 012Z, ...); see map_parse

recognise() finds the block behind a traced tile; graphics_trace calls it when its
own search finds nothing complete.
"""
from __future__ import annotations

import bisect
from collections import Counter

from . import gfx_families, gfx_packers

MAX_OUT = 0x10000


class _Reader:
    __slots__ = ('data', 'pos')

    def __init__(self, data, pos):
        self.data = data
        self.pos = pos

    def byte(self):
        if self.pos >= len(self.data):
            raise ValueError('stream is truncated')
        b = self.data[self.pos]
        self.pos += 1
        return b


_REV = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))


# ---- Nintendo LC_LZ2 / LC_LZ3 / HAL ------------------------------------
# One command byte: cccl llll (length l+1), or 111c ccll + llllllll (length up to 1024).

_NINTENDO = {
    'lz2': dict(big=True, cmds={0: 'lit', 1: 'fill', 2: 'fill2', 3: 'inc', 4: 'copy'}, words=False, rel=False),
    'lz2-le': dict(big=False, cmds={0: 'lit', 1: 'fill', 2: 'fill2', 3: 'inc', 4: 'copy'}, words=False, rel=False),
    'lz3': dict(big=True, cmds={0: 'lit', 1: 'fill', 2: 'fill2', 3: 'zero', 4: 'copy', 5: 'rev', 6: 'back'}, words=False, rel=True),
    'hal': dict(big=True, cmds={0: 'lit', 1: 'fill', 2: 'fill2', 3: 'inc', 4: 'copy', 5: 'rev', 6: 'back'}, words=True, rel=False),
}


def _nintendo_decode(variant, data, start=0, limit=MAX_OUT):
    v = _NINTENDO[variant]
    r = _Reader(data, start)
    out = bytearray()
    while True:
        first = r.byte()
        if first == 0xFF:
            break
        if first >= 0xE0:
            cmd = (first >> 2) & 7
            length = ((first & 3) << 8 | r.byte()) + 1
        else:
            cmd = first >> 5
            length = (first & 31) + 1
        op = v['cmds'].get(cmd)
        if op is None:
            raise ValueError('unknown command')
        if op == 'lit':
            if r.pos + length > len(data):
                raise ValueError('stream is truncated')
            out += data[r.pos:r.pos + length]
            r.pos += length
        elif op == 'fill':
            out += bytes([r.byte()]) * length
        elif op == 'fill2':
            a, b = r.byte(), r.byte()
            if v['words']:
                out += bytes([a, b]) * length
            else:
                out += (bytes([a, b]) * ((length + 1) // 2))[:length]
        elif op == 'inc':
            a = r.byte()
            out += bytes((a + i) & 0xFF for i in range(length))
        elif op == 'zero':
            out += bytes(length)
        else:
            a = r.byte()
            if v['rel'] and a & 0x80:
                origin = len(out) - (a & 0x7F) - 1
            else:
                b = r.byte()
                origin = (a << 8 | b) if v['big'] else (b << 8 | a)
            if origin < 0 or origin >= len(out):
                raise ValueError('copy reaches outside the output')
            if op == 'back':
                if origin - length + 1 < 0:
                    raise ValueError('copy reaches outside the output')
                out += bytes(out[origin - i] for i in range(length))
            else:
                for i in range(length):
                    if origin + i >= len(out):
                        raise ValueError('copy reaches outside the output')
                    out.append(_REV[out[origin + i]] if op == 'rev' else out[origin + i])
        if len(out) > limit:
            raise ValueError('output exceeds the limit')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), r.pos - start


def _nintendo_commands(variant, data, start=0):
    """Names of the commands a stream uses (and whether it uses the long length form)."""
    v = _NINTENDO[variant]
    used = set()
    pos = start
    while pos < len(data) and data[pos] != 0xFF:
        first = data[pos]
        pos += 1
        if first >= 0xE0:
            cmd = (first >> 2) & 7
            length = ((first & 3) << 8 | data[pos]) + 1
            pos += 1
            used.add('long')
        else:
            cmd = first >> 5
            length = (first & 31) + 1
        op = v['cmds'].get(cmd)
        if op is None:
            break
        used.add(op)
        if op == 'lit':
            pos += length
        elif op in ('fill', 'inc'):
            pos += 1
        elif op == 'fill2':
            pos += 2
        elif op != 'zero':
            if v['rel'] and data[pos] & 0x80:
                used.add('near')
                pos += 1
            else:
                used.add('far')
                pos += 2
    return used


def _nintendo_encode(variant, raw, allowed=None, size=None):
    """Shortest-path parse over the variant's commands, or over just those in `allowed`.

    With `size`, a stream shorter than that is lengthened to exactly `size`
    bytes by splitting commands (the output is the same). Some games read
    the next stream from wherever the previous one ended, so a re-encoded
    stream must not end early.

    Games' own unpackers do not all implement every command of a family, so
    when a stream is re-encoded only the commands seen in the original are
    used (see encode(..., like=...)).
    """
    v = _NINTENDO[variant]
    ops = {name: cmd for cmd, name in v['cmds'].items() if allowed is None or name in allowed or name == 'lit'}
    max_len = 1024 if allowed is None or 'long' in allowed else 32
    near_ok = allowed is None or 'near' in allowed
    far_ok = allowed is None or 'far' in allowed
    n = len(raw)
    if n > 0x10000:
        raise ValueError('data is too long for this codec')
    raw = bytes(raw)
    fwd: dict[bytes, list[int]] = {}
    rev: dict[bytes, list[int]] = {}
    bak: dict[bytes, list[int]] = {}
    INF = 1 << 30
    closed = [INF] * (n + 1)
    lit = [INF] * (n + 1)
    how = [None] * (n + 1)      # command that reaches a closed state at i: (start, op, length, args)
    lit_from = [0] * (n + 1)    # 1 when lit[i] continues a run, 0 when it opens one at i-1
    closed[0] = 0

    def head(length):
        return 1 if length <= 32 else 2

    def offer(i, op, length, cost_args, args, base):
        j = i + length
        c = base + head(length) + cost_args
        if c < closed[j]:
            closed[j] = c
            how[j] = (i, op, length, args)

    def lengths(top, least):
        out = {top}
        if top > 32:
            out.add(32)
        if top - 1 >= least:
            out.add(top - 1)
        return [x for x in out if x >= least]

    for i in range(n):
        if i >= 3:  # grams that start before i (copies may still run into the bytes being written)
            p = i - 3
            g = raw[p:p + 3]
            fwd.setdefault(g, []).append(p)
            if 'rev' in ops:
                rev.setdefault(bytes(_REV[x] for x in g), []).append(p)
            if 'back' in ops:
                bak.setdefault(g[::-1], []).append(p + 2)
        base = min(closed[i], lit[i])
        if base >= INF:
            continue
        # literal
        if lit[i] + 1 <= closed[i] + 2:
            if lit[i] + 1 < lit[i + 1]:
                lit[i + 1] = lit[i] + 1
                lit_from[i + 1] = 1
        elif closed[i] + 2 < lit[i + 1]:
            lit[i + 1] = closed[i] + 2
            lit_from[i + 1] = 0
        # runs
        r = 1
        while i + r < n and r < max_len and raw[i + r] == raw[i]:
            r += 1
        if r >= 2:
            zero = raw[i] == 0 and 'zero' in ops
            if zero or 'fill' in ops:
                for k in lengths(r, 2):
                    offer(i, 'zero' if zero else 'fill', k, 0 if zero else 1, raw[i], base)
        if i + 1 < n and raw[i + 1] != raw[i] and 'fill2' in ops:
            r = 2
            while i + r < n and r < (2 * max_len if v['words'] else max_len) and raw[i + r] == raw[i + r - 2]:
                r += 1
            if v['words']:
                r -= r & 1
                if r >= 4:
                    j = i + r
                    c = base + head(r // 2) + 2
                    if c < closed[j]:
                        closed[j] = c
                        how[j] = (i, 'fill2', r // 2, (raw[i], raw[i + 1]))
            elif r >= 4:
                for k in lengths(r, 4):
                    offer(i, 'fill2', k, 2, (raw[i], raw[i + 1]), base)
        if 'inc' in ops:
            r = 1
            while i + r < n and r < max_len and raw[i + r] == (raw[i] + r) & 0xFF:
                r += 1
            if r >= 3:
                for k in lengths(r, 3):
                    offer(i, 'inc', k, 1, raw[i], base)
        # copies
        g = raw[i:i + 3]
        if len(g) == 3:
            for op, table in (('copy', fwd), ('rev', rev), ('back', bak)):
                if op not in ops:
                    continue
                best_len, best_at = 0, 0
                for at in reversed(table.get(g, [])[-40:]):
                    near = v['rel'] and near_ok and i - at <= 128
                    if not near and not far_ok:
                        continue
                    k = 3
                    if op == 'copy':
                        while k < max_len and i + k < n and raw[at + k] == raw[i + k]:
                            k += 1
                    elif op == 'rev':
                        while k < max_len and i + k < n and _REV[raw[at + k]] == raw[i + k]:
                            k += 1
                    else:
                        while k < max_len and i + k < n and at - k >= 0 and raw[at - k] == raw[i + k]:
                            k += 1
                    if k > best_len or (k == best_len and near):
                        best_len, best_at = k, at
                if best_len >= 3:
                    near = v['rel'] and near_ok and 0 < i - best_at <= 128
                    if v['rel'] and not near and best_at >= 0x8000:
                        continue
                    for k in lengths(best_len, 3):
                        offer(i, op, k, 1 if near else 2, best_at, base)
    # walk back
    cmds = []
    i = n
    while i > 0:
        if closed[i] <= lit[i]:
            start, op, length, args = how[i]
            cmds.append((start, op, length, args))
            i = start
        else:
            j = i
            while lit_from[j]:
                j -= 1
            j -= 1
            cmds.append((j, 'lit', i - j, None))
            i = j
            # a literal run always opens from a closed state
            if i > 0:
                start, op, length, args = how[i]
                cmds.append((start, op, length, args))
                i = start
    cmds.reverse()

    def cost(c):
        start, op, length, args = c
        if op == 'lit':
            return sum((1 if min(max_len, length - q) <= 32 else 2) + min(max_len, length - q) for q in range(0, length, max_len))
        near = op in ('copy', 'rev', 'back') and v['rel'] and near_ok and 0 < start - args <= 128
        return (1 if length <= 32 else 2) + {'zero': 0, 'fill': 1, 'inc': 1, 'fill2': 2}.get(op, 1 if near else 2)

    if size is not None:
        short = size - (sum(cost(c) for c in cmds) + 1)
        k = 0
        while short > 0 and k < len(cmds):
            start, op, length, args = cmds[k]
            if op == 'lit' and 2 <= length <= 32:
                cmds[k:k + 1] = [(start, 'lit', 1, None), (start + 1, 'lit', length - 1, None)]   # one more header byte
                short -= 1
                k += 1
            elif op == 'fill' and 2 <= length <= 32 and short >= 2:
                cmds[k:k + 1] = [(start, 'fill', 1, args), (start + 1, 'fill', length - 1, args)]  # header and value again
                short -= 2
                k += 1
            elif op == 'fill' and length == 2 and short == 1:
                cmds[k] = (start, 'lit', 2, None)                                                   # 3 bytes instead of 2
                short -= 1
            else:
                k += 1
    out = bytearray()

    def emit(cmd, length):
        if length <= 32:
            out.append(cmd << 5 | (length - 1))
        else:
            out.append(0xE0 | cmd << 2 | (length - 1) >> 8)
            out.append((length - 1) & 0xFF)

    for start, op, length, args in cmds:
        if op == 'lit':
            p = start
            while p < start + length:
                k = min(max_len, start + length - p)
                emit(ops['lit'], k)
                out += raw[p:p + k]
                p += k
            continue
        emit(ops[op], length)
        if op == 'fill' or op == 'inc':
            out.append(args)
        elif op == 'fill2':
            out += bytes(args)
        elif op in ('copy', 'rev', 'back'):
            if v['rel'] and near_ok and 0 < start - args <= 128:
                out.append(0x80 | (start - args - 1))
            else:
                out += bytes((args >> 8, args & 0xFF) if v['big'] else (args & 0xFF, args >> 8))
    out.append(0xFF)
    return bytes(out)


# ---- Nintendo LC_LZ5 (Super Metroid) ------------------------------------------
# The LC_LZ2 header, with other copies: 4 = from an absolute little-endian offset,
# 6 = from 1-255 bytes back; 5 and 7 are the same with every byte inverted (7 only
# exists behind the long header).

def _lz5_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    out = bytearray()
    while True:
        first = r.byte()
        if first == 0xFF:
            break
        if first >= 0xE0:
            cmd = (first >> 2) & 7
            length = ((first & 3) << 8 | r.byte()) + 1
        else:
            cmd = first >> 5
            length = (first & 31) + 1
        if cmd == 0:
            if r.pos + length > len(data):
                raise ValueError('stream is truncated')
            out += data[r.pos:r.pos + length]
            r.pos += length
        elif cmd == 1:
            out += bytes([r.byte()]) * length
        elif cmd == 2:
            a, b = r.byte(), r.byte()
            out += (bytes([a, b]) * ((length + 1) // 2))[:length]
        elif cmd == 3:
            a = r.byte()
            out += bytes((a + i) & 0xFF for i in range(length))
        else:
            if cmd < 6:
                origin = r.byte() | r.byte() << 8
            else:
                origin = len(out) - r.byte()
            if origin < 0 or origin >= len(out):
                raise ValueError('copy reaches outside the output')
            flip = 0xFF if cmd & 1 else 0
            for i in range(length):
                out.append(out[origin + i] ^ flip)
        if len(out) > limit:
            raise ValueError('output exceeds the limit')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), r.pos - start


def _lz5_encode(raw):
    raw = bytes(raw)
    n = len(raw)
    if not n or n > 0x10000:
        raise ValueError('data is too long for this codec')
    out = bytearray()
    lit = bytearray()

    def head(cmd, length):
        if length <= 32:
            out.append(cmd << 5 | (length - 1))
        else:
            out.append(0xE0 | cmd << 2 | (length - 1) >> 8)
            out.append((length - 1) & 0xFF)

    def flush():
        for q in range(0, len(lit), 1024):
            chunk = lit[q:q + 1024]
            head(0, len(chunk))
            out.extend(chunk)
        lit.clear()

    index: dict[bytes, list[int]] = {}
    indexed = 0
    i = 0
    while i < n:
        while indexed < i:
            index.setdefault(raw[indexed:indexed + 3], []).append(indexed)
            indexed += 1
        run = 1
        while run < 1024 and i + run < n and raw[i + run] == raw[i]:
            run += 1
        two = 2
        while two < 1024 and i + two < n and raw[i + two] == raw[i + two - 2]:
            two += 1
        inc = 1
        while inc < 1024 and i + inc < n and raw[i + inc] == (raw[i] + inc) & 0xFF:
            inc += 1
        best_len, best_at = 0, 0
        for at in reversed(index.get(raw[i:i + 3], [])[-48:]):
            k = 3
            while k < 1024 and i + k < n and raw[at + k] == raw[i + k]:
                k += 1
            if k > best_len:
                best_len, best_at = k, at
        # bytes saved by each choice (against literals)
        options = [(run - 2, 1, run), (two - 3, 2, two), (inc - 2, 3, inc),
                   (best_len - (2 if i - best_at <= 255 else 3), 4, best_len)]
        saved, cmd, length = max(options)
        if saved < 1 or length < 3:
            lit.append(raw[i])
            i += 1
            continue
        flush()
        if cmd == 4 and i - best_at <= 255:
            head(6, length)
            out.append(i - best_at)
        else:
            head(cmd, length)
            if cmd == 1 or cmd == 3:
                out.append(raw[i])
            elif cmd == 2:
                out += raw[i:i + 2]
            else:
                out += bytes((best_at & 0xFF, best_at >> 8))
        i += length
    flush()
    out.append(0xFF)
    return bytes(out)


# ---- Konami (Super NES) -----------------------------------------------------------
# A little-endian size of the whole stream, then commands:
#   00-7F  copy (b >> 2) + 2 bytes from a 1024-byte ring, position (b & 3) << 8 | next byte
#          (the ring starts as zeros and is written from position 3DF)
#   80-9F  b & 1F bytes as they are
#   A0-BF  (b & 1F) + 2 bytes, each written after a 00
#   C0-DF  the next byte (b & 1F) + 2 times
#   E0-FF  (b & 1F) + 2 zeros

def _konami_snes_decode(framed, data, start=0, limit=MAX_OUT):
    n = len(data)
    pos = start
    if framed:
        if pos + 2 > n:
            raise ValueError('stream is truncated')
        size = data[pos] | data[pos + 1] << 8
        if size < 3 or start + size > n:
            raise ValueError('size header is out of range')
        end = start + size
        pos += 2
    else:
        end = n
    out = bytearray()
    while pos < end:
        if len(out) >= limit and not framed:
            break
        b = data[pos]
        pos += 1
        if b < 0x80:
            if pos >= end:
                raise ValueError('stream is truncated')
            count = (b >> 2) + 2
            here = len(out)
            dist = (0x3DF + here - ((b & 3) << 8 | data[pos])) & 0x3FF or 0x400
            pos += 1
            src = here - dist
            if src >= 0 and dist >= count:
                out += out[src:src + count]
            else:
                for k in range(src, src + count):
                    out.append(out[k] if k >= 0 else 0)
        elif b < 0xC0:
            count = (b & 0x1F) + (2 if b >= 0xA0 else 0)
            if pos + count > end:
                raise ValueError('stream is truncated')
            if b < 0xA0:
                out += data[pos:pos + count]
            else:
                for k in range(pos, pos + count):
                    out.append(0)
                    out.append(data[k])
            pos += count
        elif b < 0xE0:
            if pos >= end:
                raise ValueError('stream is truncated')
            out += bytes([data[pos]]) * ((b & 0x1F) + 2)
            pos += 1
        else:
            out += bytes((b & 0x1F) + 2)
        if len(out) > limit and framed:
            raise ValueError('output exceeds the limit')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), pos - start


def _konami_snes_encode(framed, raw):
    raw = bytes(raw)
    n = len(raw)
    if not n:
        raise ValueError('nothing to pack')
    # what can start at each position
    index: dict[bytes, list[int]] = {}
    INF = 1 << 30
    closed = [INF] * (n + 2)        # cheapest stream for raw[:i] that does not end inside a literal block
    lit = [INF] * (n + 2)           # ... that ends inside one
    how = [None] * (n + 2)          # the command that reaches closed[i]: (start, kind, argument)
    opened = [False] * (n + 2)
    closed[0] = 0
    for i in range(n):
        if i >= 1:
            index.setdefault(raw[i - 1:i + 1], []).append(i - 1)
        here = min(closed[i], lit[i])
        if here >= INF:
            continue
        if lit[i] + 1 <= closed[i] + 2:
            if lit[i] + 1 < lit[i + 1]:
                lit[i + 1], opened[i + 1] = lit[i] + 1, False
        elif closed[i] + 2 < lit[i + 1]:
            lit[i + 1], opened[i + 1] = closed[i] + 2, True
        run = 1
        while run < 33 and i + run < n and raw[i + run] == raw[i]:
            run += 1
        cost = 1 if raw[i] == 0 else 2
        for k in range(2, run + 1):
            if here + cost < closed[i + k]:
                closed[i + k], how[i + k] = here + cost, (i, 'zero' if raw[i] == 0 else 'run', k)
        pairs = 0
        while pairs < 33 and i + 2 * pairs + 1 < n and raw[i + 2 * pairs] == 0:
            pairs += 1
            if pairs >= 2 and here + 1 + pairs < closed[i + 2 * pairs]:
                closed[i + 2 * pairs], how[i + 2 * pairs] = here + 1 + pairs, (i, 'pairs', pairs)
        top, at0 = 0, 0
        for at in reversed(index.get(raw[i:i + 2], [])[-64:]):
            if i - at > 0x3FF:
                break
            k = 2
            while k < 33 and i + k < n and raw[at + k] == raw[i + k]:
                k += 1
            if k > top:
                top, at0 = k, at
                if k == 33:
                    break
        for k in range(2, top + 1):
            if here + 2 < closed[i + k]:
                closed[i + k], how[i + k] = here + 2, (i, 'copy', at0)
    # walk back
    cmds = []
    i = n
    in_lit = lit[n] < closed[n]
    while i > 0:
        if in_lit:
            j = i
            while not opened[j]:
                j -= 1
            j -= 1
            cmds.append((j, 'lit', i - j))
            i, in_lit = j, False
        else:
            start, kind, arg = how[i]
            cmds.append((start, kind, arg if kind != 'copy' else (arg, i - start)))
            i, in_lit = start, lit[start] < closed[start]
    cmds.reverse()
    out = bytearray()
    for start, kind, arg in cmds:
        if kind == 'lit':
            for q in range(start, start + arg, 31):
                chunk = raw[q:min(q + 31, start + arg)]
                out.append(0x80 | len(chunk))
                out += chunk
        elif kind == 'zero':
            out.append(0xE0 | (arg - 2))
        elif kind == 'run':
            out += bytes((0xC0 | (arg - 2), raw[start]))
        elif kind == 'pairs':
            out.append(0xA0 | (arg - 2))
            out += raw[start + 1:start + 2 * arg:2]
        else:
            at, length = arg
            ring = (0x3DF + at) & 0x3FF
            out += bytes(((length - 2) << 2 | ring >> 8, ring & 0xFF))
    if not framed:
        return bytes(out)
    size = len(out) + 2
    if size > 0xFFFF:
        raise ValueError('data is too long for this codec')
    return bytes((size & 0xFF, size >> 8)) + bytes(out)


# ---- Okumura LZSS --------------------------------------------------------

def _lzss_decode(fill, header, data, start=0, limit=MAX_OUT):
    # The 4096-byte ring is not kept: ring position p holds the output byte written when the
    # write position was last p, or the fill before that, so a ring offset is a distance back.
    n = len(data)
    pos = start
    want = None
    if header == 'le16':
        if pos + 2 > n:
            raise ValueError('stream is truncated')
        want = data[pos] | data[pos + 1] << 8
        pos += 2
        if not 0 < want <= limit:
            raise ValueError('size header is out of range')
    out = bytearray()
    target = want if want is not None else limit
    while len(out) < target:
        if pos >= n:
            if want is None and out:
                break
            raise ValueError('stream is truncated')
        flags = data[pos]
        pos += 1
        for bit in range(8):
            here = len(out)
            if here >= target:
                break
            if flags >> bit & 1:
                if pos >= n:
                    if want is None:
                        return bytes(out), pos - start
                    raise ValueError('stream is truncated')
                out.append(data[pos])
                pos += 1
            else:
                if pos + 2 > n:
                    if want is None:
                        return bytes(out), pos - start
                    raise ValueError('stream is truncated')
                hi = data[pos + 1]
                at = data[pos] | (hi & 0xF0) << 4
                pos += 2
                count = (hi & 0x0F) + 3
                dist = (0xFEE + here - at) & 0xFFF or 0x1000
                src = here - dist
                if src >= 0 and dist >= count:
                    out += out[src:src + count]
                else:
                    for k in range(src, src + count):
                        out.append(out[k] if k >= 0 else fill)
    del out[target:]
    return bytes(out), pos - start


def _lzss_encode(fill, header, raw):
    n = len(raw)
    out = bytearray()
    if header == 'le16':
        if n > 0xFFFF:
            raise ValueError('data is too long for this codec')
        out += bytes((n & 0xFF, n >> 8))
    index: dict[bytes, list[int]] = {}
    i = 0
    indexed = 0
    while i < n:
        flag_at = len(out)
        out.append(0)
        for bit in range(8):
            if i >= n:
                break
            while indexed < i:
                index.setdefault(bytes(raw[indexed:indexed + 3]), []).append(indexed)
                indexed += 1
            best_len, best_at = 0, 0
            for at in reversed(index.get(bytes(raw[i:i + 3]), [])[-32:]):
                if i - at > 4095:  # the ring has wrapped past it
                    break
                k = 0
                while k < 18 and i + k < n and raw[at + k] == raw[i + k]:
                    k += 1
                if k > best_len:
                    best_len, best_at = k, at
            if best_len >= 3:
                at = (0xFEE + best_at) & 0xFFF
                out += bytes((at & 0xFF, (at >> 4 & 0xF0) | (best_len - 3)))
                i += best_len
            else:
                out[flag_at] |= 1 << bit
                out.append(raw[i])
                i += 1
    return bytes(out)


# ---- Sega Kosinski ---------------------------------------------------------

def _kosinski_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    out = bytearray()
    state = [r.byte() | r.byte() << 8, 16]

    def bit():
        b = state[0] & 1
        state[0] >>= 1
        state[1] -= 1
        if state[1] == 0:
            state[0] = r.byte() | r.byte() << 8
            state[1] = 16
        return b

    while True:
        if bit():
            out.append(r.byte())
        else:
            if bit():
                lo, hi = r.byte(), r.byte()
                offset = ((hi & 0xF8) << 5 | lo) - 0x2000
                count = hi & 7
                if count:
                    count += 2
                else:
                    count = r.byte()
                    if count == 0:
                        break
                    if count == 1:
                        continue
                    count += 1
            else:
                count = (bit() << 1 | bit()) + 2
                offset = r.byte() - 0x100
            origin = len(out) + offset
            if origin < 0:
                raise ValueError('copy reaches outside the output')
            for k in range(count):
                out.append(out[origin + k])
        if len(out) > limit:
            raise ValueError('output exceeds the limit')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), r.pos - start


def _kosinski_encode(raw):
    """Cheapest parse by bit cost: literal 9; 2-5 bytes from up to 256 back 12; 3-9 bytes 18; longer 26."""
    raw = bytes(raw)
    n = len(raw)
    # longest match within 256 bytes and within 0x2000, at each position
    near = [(0, 0)] * n
    far = [(0, 0)] * n
    index: dict[bytes, list[int]] = {}
    for i in range(n):
        if i >= 1:
            index.setdefault(raw[i - 1:i + 1], []).append(i - 1)
        best_near = best_far = (0, 0)
        for at in reversed(index.get(raw[i:i + 2], [])[-64:]):
            dist = i - at
            if dist > 0x2000:
                break
            k = 2
            while k < 256 and i + k < n and raw[at + k] == raw[i + k]:
                k += 1
            if dist <= 256 and k > best_near[0]:
                best_near = (k, dist)
            if k > best_far[0]:
                best_far = (k, dist)
                if k == 256:
                    break
        near[i], far[i] = best_near, best_far
    INF = 1 << 60
    cost = [INF] * (n + 1)
    step = [(1, 0, 0)] * (n + 1)        # (length, distance, kind: 0 literal, 1 short, 2 long)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        c, how = cost[i + 1] + 9, (1, 0, 0)
        k, dist = near[i]
        for length in range(2, min(k, 5) + 1):
            if cost[i + length] + 12 < c:
                c, how = cost[i + length] + 12, (length, dist, 1)
        k, dist = far[i]
        if k >= 3:
            for length in range(3, min(k, 9) + 1):
                if cost[i + length] + 18 < c:
                    c, how = cost[i + length] + 18, (length, dist, 2)
            # long copies: every length up to 24, then only the longest
            for length in list(range(10, min(k, 24) + 1)) + ([k] if k > 24 else []):
                if cost[i + length] + 26 < c:
                    c, how = cost[i + length] + 26, (length, dist, 2)
        cost[i], step[i] = c, how
    out = bytearray(2)
    state = {'at': 0, 'bits': 0, 'used': 0}

    def put(b):
        state['bits'] |= b << state['used']
        state['used'] += 1
        if state['used'] == 16:
            out[state['at']] = state['bits'] & 0xFF
            out[state['at'] + 1] = state['bits'] >> 8
            state.update(at=len(out), bits=0, used=0)
            out.extend(b'\0\0')

    i = 0
    while i < n:
        length, dist, kind = step[i]
        if kind == 0:
            put(1)
            out.append(raw[i])
        elif kind == 1:
            put(0); put(0); put((length - 2) >> 1); put((length - 2) & 1)
            out.append((-dist) & 0xFF)
        else:
            put(0); put(1)
            off = (-dist) & 0x1FFF
            if length <= 9:
                out += bytes((off & 0xFF, (off >> 5 & 0xF8) | (length - 2)))
            else:
                out += bytes((off & 0xFF, off >> 5 & 0xF8, length - 1))
        i += length
    put(0); put(1)
    out += b'\x00\xF0\x00'
    out[state['at']] = state['bits'] & 0xFF
    out[state['at'] + 1] = state['bits'] >> 8
    return bytes(out)


# ---- Sega Nemesis ----------------------------------------------------------

class _Bits:
    """MSB-first bit reader."""
    __slots__ = ('r', 'cur', 'left')

    def __init__(self, reader):
        self.r = reader
        self.cur = 0
        self.left = 0

    def bit(self):
        if not self.left:
            self.cur = self.r.byte()
            self.left = 8
        self.left -= 1
        return self.cur >> self.left & 1

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = v << 1 | self.bit()
        return v


class _BitWriter:
    def __init__(self):
        self.out = bytearray()
        self.cur = 0
        self.n = 0

    def put(self, value, width):
        for k in range(width - 1, -1, -1):
            self.cur = self.cur << 1 | (value >> k & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.cur)
                self.cur = self.n = 0

    def finish(self):
        if self.n:
            self.out.append(self.cur << (8 - self.n))
            self.cur = self.n = 0
        return self.out


def _nemesis_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    head = r.byte() << 8 | r.byte()
    xor = bool(head & 0x8000)
    size = (head & 0x7FFF) * 32
    if not 0 < size <= limit:
        raise ValueError('tile count is out of range')
    table = {}
    value = r.byte()
    nibble = None
    while value != 0xFF:
        if value & 0x80:
            nibble = value & 0x0F
            value = r.byte()
            continue
        if nibble is None:
            raise ValueError('code table has no color')
        length = value & 0x0F
        code = r.byte()
        if not 1 <= length <= 8 or code >> length:
            raise ValueError('bad code length')
        table[(length, code)] = (nibble, (value >> 4 & 7) + 1)
        value = r.byte()
    bits = _Bits(r)
    nibbles = bytearray()
    total = size * 2
    while len(nibbles) < total:
        code = length = 0
        while True:
            code = code << 1 | bits.bit()
            length += 1
            if length == 6 and code == 0x3F:
                count = bits.bits(3) + 1
                nib = bits.bits(4)
                break
            hit = table.get((length, code))
            if hit:
                nib, count = hit
                break
            if length >= 8:
                raise ValueError('code is not in the table')
        nibbles += bytes([nib]) * count
    del nibbles[total:]
    out = bytearray((nibbles[i] << 4 | nibbles[i + 1]) for i in range(0, total, 2))
    if xor:
        for i in range(4, size):
            out[i] ^= out[i - 4]
    return bytes(out), r.pos - start


def _nemesis_body(raw):
    runs = []
    nibbles = bytearray()
    for b in raw:
        nibbles.append(b >> 4)
        nibbles.append(b & 15)
    i = 0
    while i < len(nibbles):
        k = 1
        while k < 8 and i + k < len(nibbles) and nibbles[i + k] == nibbles[i]:
            k += 1
        runs.append((nibbles[i], k))
        i += k
    freq = Counter(runs)
    # Choose code lengths: frequent runs get short codes; the Kraft sum of the
    # table stays at or below 63/64 so no code can begin with the 111111 escape.
    lengths = {}
    budget = 63 / 64
    ranked = [s for s, c in freq.most_common() if c >= 2]
    total = sum(freq[s] for s in ranked) or 1
    for s in ranked:
        p = freq[s] / total
        want = 1
        while want < 8 and 2.0 ** -want > p:
            want += 1
        while want <= 8 and 2.0 ** -want > budget + 1e-12:
            want += 1
        if want > 8:
            break
        lengths[s] = want
        budget -= 2.0 ** -want
    codes = {}
    code = 0
    prev = 0
    for s, length in sorted(lengths.items(), key=lambda kv: (kv[1], kv[0])):
        code <<= length - prev
        codes[s] = (length, code)
        code += 1
        prev = length
    head = bytearray()
    for nib in sorted({s[0] for s in codes}):
        head.append(0x80 | nib)
        for s, (length, c) in codes.items():
            if s[0] == nib:
                head += bytes(((s[1] - 1) << 4 | length, c))
    head.append(0xFF)
    w = _BitWriter()
    for s in runs:
        if s in codes:
            w.put(codes[s][1], codes[s][0])
        else:
            w.put(0x3F, 6)
            w.put(s[1] - 1, 3)
            w.put(s[0], 4)
    return bytes(head) + bytes(w.finish())


def _nemesis_encode(raw):
    if not raw or len(raw) % 32 or len(raw) // 32 > 0x7FFF:
        raise ValueError('Nemesis data must be whole 32-byte tiles')
    plain = _nemesis_body(raw)
    x = bytearray(raw)
    for i in range(len(x) - 1, 3, -1):
        x[i] ^= x[i - 4]
    xored = _nemesis_body(bytes(x))
    tiles = len(raw) // 32
    if len(xored) < len(plain):
        return bytes(((0x80 | tiles >> 8), tiles & 0xFF)) + xored
    return bytes((tiles >> 8, tiles & 0xFF)) + plain


# ---- Sega Enigma -------------------------------------------------------------

_ENIGMA_FLAGS = (0x8000, 0x4000, 0x2000, 0x1000, 0x0800)


def _enigma_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    width = r.byte()
    mask = r.byte()
    if not 1 <= width <= 11 or mask > 0x1F:
        raise ValueError('bad header')
    inc = r.byte() << 8 | r.byte()
    common = r.byte() << 8 | r.byte()
    bits = _Bits(r)
    out = bytearray()

    def inline():
        v = 0
        for k, flag in enumerate(_ENIGMA_FLAGS):
            if mask >> (4 - k) & 1 and bits.bit():
                v |= flag
        return v | bits.bits(width)

    def word(v):
        out.append(v >> 8 & 0xFF)
        out.append(v & 0xFF)

    while True:
        if bits.bit():
            mode = 4 | bits.bits(2)
        else:
            mode = bits.bit()
        count = bits.bits(4)
        if mode == 0:
            for _ in range(count + 1):
                word(inc)
                inc = (inc + 1) & 0xFFFF
        elif mode == 1:
            for _ in range(count + 1):
                word(common)
        elif mode in (4, 5, 6):
            v = inline()
            for _ in range(count + 1):
                word(v)
                v = (v + (0, 1, -1)[mode - 4]) & 0xFFFF
        else:
            if count == 15:
                break
            for _ in range(count + 1):
                word(inline())
        if len(out) > limit:
            raise ValueError('output exceeds the limit')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), r.pos - start


def _enigma_encode(raw):
    if not raw or len(raw) % 2:
        raise ValueError('Enigma data must be whole 16-bit words')
    words = [raw[i] << 8 | raw[i + 1] for i in range(0, len(raw), 2)]
    width = max(1, max(w & 0x7FF for w in words).bit_length())
    used = 0
    for w in words:
        used |= w & 0xF800
    mask = sum(1 << (4 - k) for k, flag in enumerate(_ENIGMA_FLAGS) if used & flag)
    common = Counter(words).most_common(1)[0][0]
    w = _BitWriter()

    def inline(v):
        for k, flag in enumerate(_ENIGMA_FLAGS):
            if mask >> (4 - k) & 1:
                w.put(1 if v & flag else 0, 1)
        w.put(v & ((1 << width) - 1), width)

    i = 0
    n = len(words)
    pending = []

    def flush():
        p = 0
        while p < len(pending):
            k = min(15, len(pending) - p)
            w.put(7, 3); w.put(k - 1, 4)
            for v in pending[p:p + k]:
                inline(v)
            p += k
        pending.clear()

    while i < n:
        v = words[i]
        same = 1
        while same < 16 and i + same < n and words[i + same] == v:
            same += 1
        up = 1
        while up < 16 and i + up < n and words[i + up] == (v + up) & 0xFFFF and ((v + up) & 0x7FF) >> width == 0 and (v ^ (v + up)) & 0xF800 == 0:
            up += 1
        down = 1
        while down < 16 and i + down < n and words[i + down] == (v - down) & 0xFFFF and v - down >= 0 and (v ^ (v - down)) & 0xF800 == 0:
            down += 1
        if v == common and same >= 1:
            flush(); w.put(1, 2); w.put(same - 1, 4); i += same
        elif same >= 2 and same >= up and same >= down:
            flush(); w.put(4, 3); w.put(same - 1, 4); inline(v); i += same
        elif up >= 2 and up >= down:
            flush(); w.put(5, 3); w.put(up - 1, 4); inline(v); i += up
        elif down >= 2:
            flush(); w.put(6, 3); w.put(down - 1, 4); inline(v); i += down
        else:
            pending.append(v); i += 1
    flush()
    w.put(7, 3); w.put(15, 4)
    return bytes((width, mask, 0, 0, common >> 8, common & 0xFF)) + bytes(w.finish())


# ---- run-length families ---------------------------------------------------

def _packbits_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    out = bytearray()
    while len(out) < limit and r.pos < len(data):
        n = r.byte()
        if n < 0x80:
            if r.pos + n + 1 > len(data):
                raise ValueError('stream is truncated')
            out += data[r.pos:r.pos + n + 1]
            r.pos += n + 1
        elif n > 0x80:
            out += bytes([r.byte()]) * (257 - n)
    if not out:
        raise ValueError('empty stream')
    return bytes(out[:limit]), r.pos - start


def _runs(raw, cap):
    i = 0
    n = len(raw)
    while i < n:
        k = 1
        while k < cap and i + k < n and raw[i + k] == raw[i]:
            k += 1
        yield raw[i], k
        i += k


def _packbits_encode(raw, size=None):
    """`size`: the stream being replaced was that long; this one is lengthened to match (a bare
    stream has no end of its own) by splitting literal blocks and runs."""
    tokens = []         # bytes (a literal block) or (value, count)
    lit = bytearray()

    def flush():
        for p in range(0, len(lit), 128):
            tokens.append(bytes(lit[p:p + 128]))
        lit.clear()

    for value, k in _runs(raw, 128):
        if k >= 3:
            flush()
            tokens.append((value, k))
        else:
            lit += bytes([value]) * k
    flush()
    now = sum(len(t) + 1 if isinstance(t, bytes) else 2 for t in tokens)
    i = 0
    while size is not None and now < size and i < len(tokens):
        t = tokens[i]
        if isinstance(t, bytes) and len(t) >= 2:
            tokens[i:i + 1] = [t[:1], t[1:]]            # one byte more
            now += 1
        elif not isinstance(t, bytes) and t[1] >= 4 and size - now >= 2:
            tokens[i:i + 1] = [(t[0], 2), (t[0], t[1] - 2)]     # two bytes more
            now += 2
        elif not isinstance(t, bytes) and t[1] - 1 <= size - now:
            tokens[i] = bytes([t[0]]) * t[1]            # a run written out
            now += t[1] - 1
        else:
            i += 1
    out = bytearray()
    for t in tokens:
        if isinstance(t, bytes):
            out.append(len(t) - 1)
            out += t
        else:
            out += bytes((257 - t[1], t[0]))
    return bytes(out)


def _konami_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    out = bytearray()
    while True:
        n = r.byte()
        if n == 0xFF:
            break
        if n <= 0x80:
            if n == 0:
                raise ValueError('zero-length run')
            out += bytes([r.byte()]) * n
        else:
            k = n - 0x80
            if r.pos + k > len(data):
                raise ValueError('stream is truncated')
            out += data[r.pos:r.pos + k]
            r.pos += k
        if len(out) > limit:
            raise ValueError('output exceeds the limit')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), r.pos - start


def _konami_encode(raw):
    out = bytearray()
    lit = bytearray()

    def flush():
        for p in range(0, len(lit), 0x7E):
            chunk = lit[p:p + 0x7E]
            out.append(0x80 + len(chunk))
            out.extend(chunk)
        lit.clear()

    # Runs stop at 7E: in the games that use this format a count of 7F is a command of its own
    # (it moves the write address), and 80 is not a count their loops handle.
    for value, k in _runs(raw, 0x7E):
        if k >= 3:
            flush()
            out += bytes((k, value))
        else:
            lit += bytes([value]) * k
    flush()
    out.append(0xFF)
    return bytes(out)


def _pairs_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    out = bytearray()
    while True:
        n = r.byte()
        if n == 0:
            break
        out += bytes([r.byte()]) * n
        if len(out) > limit:
            raise ValueError('output exceeds the limit')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), r.pos - start


def _pairs_encode(raw):
    out = bytearray()
    for value, k in _runs(raw, 255):
        out += bytes((k, value))
    out.append(0)
    return bytes(out)


# ---- Sega Comper ------------------------------------------------------------
# A 16-bit description field (MSB first), then its 16 tokens: 0 = one word as it
# is, 1 = (distance, count): count + 1 words from 0x100 - distance words back.

def _comper_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    out = bytearray()
    while True:
        desc = r.byte() << 8 | r.byte()
        for bit in range(15, -1, -1):
            if not desc >> bit & 1:
                out.append(r.byte())
                out.append(r.byte())
            else:
                dist = (0x100 - r.byte()) * 2
                count = r.byte()
                if count == 0:
                    if not out:
                        raise ValueError('empty stream')
                    return bytes(out), r.pos - start
                origin = len(out) - dist
                if origin < 0:
                    raise ValueError('copy reaches outside the output')
                for k in range((count + 1) * 2):
                    out.append(out[origin + k])
            if len(out) > limit:
                raise ValueError('output exceeds the limit')


def _comper_encode(raw):
    raw = bytes(raw)
    n = len(raw)
    if not n or n % 2:
        raise ValueError('Comper data must be whole 16-bit words')
    tokens = []
    index: dict[bytes, list[int]] = {}
    indexed = 0
    i = 0
    while i < n:
        while indexed < i:
            index.setdefault(raw[indexed:indexed + 2], []).append(indexed)
            indexed += 2
        best_len, best_at = 0, 0
        for at in reversed(index.get(raw[i:i + 2], [])[-48:]):
            if i - at > 512:
                break
            k = 0
            while k < 512 and i + k + 1 < n and raw[at + k] == raw[i + k] and raw[at + k + 1] == raw[i + k + 1]:
                k += 2
            if k > best_len:
                best_len, best_at = k, at
        if best_len >= 4:
            tokens.append((1, bytes(((0x100 - (i - best_at) // 2) & 0xFF, best_len // 2 - 1))))
            i += best_len
        else:
            tokens.append((0, raw[i:i + 2]))
            i += 2
    tokens.append((1, b'\0\0'))
    out = bytearray()
    for g in range(0, len(tokens), 16):
        group = tokens[g:g + 16]
        desc = 0
        for k, (flag, _) in enumerate(group):
            desc |= flag << (15 - k)
        out += bytes((desc >> 8, desc & 0xFF))
        for _, body in group:
            out += body
    return bytes(out)


# ---- Sega Kosinski, moduled (Sonic 3 & Knuckles) ----------------------------------
# Big-endian total size, then Kosinski streams of 0x1000 unpacked bytes each,
# every one but the last padded to a multiple of 16 bytes.

def _kosinskim_decode(data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    total = r.byte() << 8 | r.byte()
    if total == 0xA000:
        total = 0x8000
    if not 0 < total <= limit:
        raise ValueError('size header is out of range')
    out = bytearray()
    pos = start + 2
    while len(out) < total:
        part, used = _kosinski_decode(data, pos, 0x1000)
        if len(part) != min(0x1000, total - len(out)):
            raise ValueError('module size does not match the header')
        out += part
        pos += used
        if len(out) < total:
            pos = start + 2 + ((pos - start - 2 + 15) & ~15)
    return bytes(out), pos - start


def _kosinskim_encode(raw):
    raw = bytes(raw)
    n = len(raw)
    if not n or n > 0xFFFF or n == 0xA000:
        raise ValueError('data is too long for this codec')
    out = bytearray((n >> 8, n & 0xFF))
    for p in range(0, n, 0x1000):
        out += _kosinski_encode(raw[p:p + 0x1000])
        if p + 0x1000 < n:
            out += bytes(-(len(out) - 2) % 16)
    return bytes(out)


# ---- stored as it is ------------------------------------------------------------------

def _raw_decode(data, start=0, limit=MAX_OUT):
    out = bytes(data[start:start + limit])
    if not out:
        raise ValueError('empty stream')
    return out, len(out)


# ---- how unpacked bytes are laid into video memory -----------------------------------
# Games often store fewer bit planes than the video chip holds and fill the rest
# in as they load. A map is one character per video-memory byte of a repeating
# group: 0-9 a-v = that byte of the stored group, Z = a 00 the game makes up,
# F = an FF it makes up. "012Z" is three stored planes and an empty fourth.

_MAP_CHARS = '0123456789abcdefghijklmnopqrstuv'
MAP_ALIASES = {
    '3bpp': '0123456789abcdefgZhZiZjZkZlZmZnZ',     # Super NES: 16 bytes, then 8 each followed by 00
    '2of4': '0123456789abcdef' + 'Z' * 16,          # Super NES: two of four planes
    '1of2n': '01234567' + 'Z' * 8,                  # NES: first plane only
    '1of2n-b': 'Z' * 8 + '01234567',                # NES: second plane only
    '1x2n': '0123456701234567',                     # NES: one plane used for both
}
_MAPS: dict[str, tuple] = {}


def map_parse(text: str):
    """(group size in video memory, stored group size, [(stored index or -1, made-up value)])."""
    hit = _MAPS.get(text)
    if hit is None:
        chars = MAP_ALIASES.get(text, text)
        entries = []
        for c in chars:
            if c == 'Z':
                entries.append((-1, 0x00))
            elif c == 'F':
                entries.append((-1, 0xFF))
            elif c in _MAP_CHARS:
                entries.append((_MAP_CHARS.index(c), None))
            else:
                raise KeyError(text)
        k = max(q for q, _ in entries) + 1
        if k < 1 or {q for q, _ in entries if q >= 0} != set(range(k)):
            raise KeyError(text)
        hit = _MAPS[text] = (len(entries), k, tuple(entries))
    return hit


def map_expand(text: str, raw: bytes) -> bytes:
    m, k, entries = map_parse(text)
    groups = len(raw) // k
    out = bytearray(groups * m)
    for j, (q, const) in enumerate(entries):
        out[j::m] = raw[q:groups * k:k] if q >= 0 else bytes([const]) * groups
    return bytes(out)


def map_contract(text: str, expanded: bytes) -> bytes:
    """The stored bytes that expand to `expanded`; ValueError when it holds something the game cannot store."""
    m, k, entries = map_parse(text)
    if len(expanded) % m:
        raise ValueError('The data is not whole groups.')
    groups = len(expanded) // m
    out = bytearray(groups * k)
    seen = set()
    for j, (q, const) in enumerate(entries):
        col = expanded[j::m]
        if q < 0:
            if col != bytes([const]) * groups:
                raise ValueError('The game fills that part of the tile in itself (it is stored with fewer colors); '
                                 'it cannot be edited.')
        elif q in seen:
            if col != out[q::k]:
                raise ValueError('Those bytes are stored once and used twice; they can only change together.')
        else:
            seen.add(q)
            out[q::k] = col
    return bytes(out)


def map_index(text: str, i: int):
    """Index in the stored block of expanded byte `i`, or None when the game makes that byte up."""
    m, k, entries = map_parse(text)
    group, j = divmod(i, m)
    q = entries[j][0]
    return None if q < 0 else group * k + q


# Layouts worth trying on each system (besides "as it is").
MAPS = {
    'snes': ('3bpp', '2of4', '0Z', '00'),
    'sms': ('012Z', '01ZZ', '0ZZZ', '012F', '01FF', '0FFF'),
    'gb': ('0Z', 'Z0', '0F', 'F0'),
    'gbc': ('0Z', 'Z0', '0F', 'F0'),
    'nes': ('1of2n', '1of2n-b', '1x2n'),
    'genesis': (),
}


# ---- run length behind an escape byte (Capcom on the Game Boy) ---------------------
# The first byte of the stream is the escape. After it: any other byte stands for itself;
# escape, count, value is a run; escape, 00 ends the stream.

# Stored bytes also "unpack" (as themselves, until some escape, 00 pair turns up), so a stream is
# held to what the games' packers write: blocks of a few hundred tiles at most, runs that are
# worth their three bytes, and no long stretch without one.
_ESCAPE_MOST = 0x2000


def _escape_decode(framed, data, start=0, limit=MAX_OUT):
    n = len(data)
    if start + 3 > n:
        raise ValueError('stream is truncated')
    esc = data[start]
    pos = start + 1
    out = bytearray()
    runs = 0
    while True:
        if pos >= n:
            raise ValueError('stream is truncated')
        b = data[pos]
        pos += 1
        if b != esc:
            out.append(b)
        else:
            if pos >= n:
                raise ValueError('stream is truncated')
            count = data[pos]
            pos += 1
            if count == 0:
                break
            if pos >= n:
                raise ValueError('stream is truncated')
            if count < 3 and data[pos] != esc:
                raise ValueError('a run this short is not something a packer writes')
            runs += 1
            out += bytes([data[pos]]) * count
            pos += 1
        if len(out) > limit:
            if framed:
                raise ValueError('output exceeds the limit')
            del out[limit:]
            break
        if len(out) > 1024 * (runs + 1) or len(out) > _ESCAPE_MOST:
            raise ValueError('this is not packed data')
    if not out:
        raise ValueError('empty stream')
    return bytes(out), pos - start


def _escape_encode(raw, like=None):
    raw = bytes(raw)
    if not raw or len(raw) > _ESCAPE_MOST:
        raise ValueError('nothing to pack' if not raw else 'data is too long for this codec')
    seen = Counter(raw)
    esc = like[0] if like and seen[like[0]] == 0 else min(range(256), key=lambda v: (seen[v], v not in (5, 6, 0x0C), v))
    out = bytearray([esc])
    since = 0       # bytes written since the last run: the decoder gives up on long stretches without one
    for value, k in _runs(raw, 255):
        if k >= 4 or value == esc or (k == 3 and since > 768):
            out += bytes((esc, k, value))
            since = 0
        else:
            out += bytes([value]) * k
            since += k
    out += bytes((esc, 0))
    return bytes(out)


# ---- registry ---------------------------------------------------------------

def _bind(fn, *head):
    return lambda *args, **kw: fn(*head, *args, **kw)


class _Registry(dict):
    """Codecs by name. Family members (lz~..., rle~...) and layouts (codec|map) are made on first use."""

    made: dict = {}     # kept apart so that iterating CODECS lists only the fixed ones

    def __missing__(self, name):
        hit = self.made.get(name)
        if hit is not None:
            return hit
        if '|' in name:
            base, text = name.split('|', 1)
            entry = self[base]
            m, k, _ = map_parse(text)
            terminated = entry['terminated']

            def dec(data, start=0, limit=MAX_OUT, _d=entry['decode']):
                raw, used = _d(data, start, limit if terminated else (limit // m + 1) * k)
                out = map_expand(text, raw)
                if not out:
                    raise ValueError('empty stream')
                if not terminated:
                    used = min(used, len(out) // m * k)
                return out, used
            made = {'decode': dec, 'encode': lambda raw, _b=base: encode(_b, map_contract(text, raw)), 'terminated': terminated,
                    'base': base, 'map': text}
        else:
            dec, enc, terminated = gfx_families.build(name)
            made = {'decode': dec, 'encode': enc, 'terminated': terminated}
            if not terminated:
                made['exact'] = True
                made['sized'] = True
                if name.startswith('lz~'):
                    made['encode'] = lambda raw, size=None, like=None, _e=enc: _e(raw, None, size, like)
                    made['likes'] = True
            elif gfx_families.features(name):
                made['commands'] = gfx_families.features(name)
            if name.startswith('lz~') and not name.startswith('lz~n.'):
                # a size header says little: the body is looked at as a bare stream first
                made['peek'] = ('lz~n.' + name.split('.', 1)[1][:-1] + 'u', 2)
        self.made[name] = made
        return made


CODECS: dict[str, dict] = _Registry()
for _name in _NINTENDO:
    CODECS[_name] = {'decode': _bind(_nintendo_decode, _name), 'encode': _bind(_nintendo_encode, _name), 'terminated': True,
                     'commands': _bind(_nintendo_commands, _name)}
for _fill in (0x00, 0x20):
    for _header in ('le16', 'raw'):
        CODECS[f'lzss-{_fill:02x}-{_header}'] = {'decode': _bind(_lzss_decode, _fill, _header),
                                                 'encode': _bind(_lzss_encode, _fill, _header), 'terminated': _header != 'raw'}
    CODECS[f'lzss-{_fill:02x}-le16']['peek'] = (f'lzss-{_fill:02x}-raw', 2)
    CODECS[f'lzss-{_fill:02x}-raw']['exact'] = True
    # written by the family's encoder: the cheapest parse, lengthened to the size of the stream it replaces
    CODECS[f'lzss-{_fill:02x}-raw']['sized'] = True
    CODECS[f'lzss-{_fill:02x}-raw']['encode'] = (
        lambda raw, size=None, like=None, _p=gfx_families.lz_parse('lz~n.l1.oku.rfee' + ('+20' if _fill else '') + '.m3.n'):
        gfx_families.lz_encode(_p, raw, None, size, like))
    CODECS[f'lzss-{_fill:02x}-raw']['likes'] = True
CODECS['lz5'] = {'decode': _lz5_decode, 'encode': _lz5_encode, 'terminated': True}
CODECS['konami-snes'] = {'decode': _bind(_konami_snes_decode, True), 'encode': _bind(_konami_snes_encode, True),
                         'terminated': True, 'peek': ('konami-snes-body', 2)}
CODECS.made['konami-snes-body'] = {'decode': _bind(_konami_snes_decode, False), 'encode': _bind(_konami_snes_encode, False),
                                   'terminated': False}
CODECS['kosinski'] = {'decode': _kosinski_decode, 'encode': _kosinski_encode, 'terminated': True}
CODECS['kosinski-moduled'] = {'decode': _kosinskim_decode, 'encode': _kosinskim_encode, 'terminated': True}
CODECS['nemesis'] = {'decode': _nemesis_decode, 'encode': _nemesis_encode, 'terminated': True}
CODECS['enigma'] = {'decode': _enigma_decode, 'encode': _enigma_encode, 'terminated': True}
CODECS['comper'] = {'decode': _comper_decode, 'encode': _comper_encode, 'terminated': True}
CODECS['rle-konami'] = {'decode': _konami_decode, 'encode': _konami_encode, 'terminated': True}
CODECS['rle-pairs'] = {'decode': _pairs_decode, 'encode': _pairs_encode, 'terminated': True}
CODECS['packbits'] = {'decode': _packbits_decode, 'encode': _packbits_encode, 'terminated': False, 'exact': True,
                      'sized': True}
CODECS['rle-escape'] = {'decode': _bind(_escape_decode, True), 'encode': _escape_encode, 'terminated': True,
                        'peek': ('rle-escape-body', 0)}
CODECS.made['rle-escape-body'] = {'decode': _bind(_escape_decode, False), 'encode': _escape_encode, 'terminated': False}
CODECS.update(gfx_packers.CODECS)
CODECS.made.update(gfx_packers.BODIES)
CODECS['raw'] = {'decode': _raw_decode, 'encode': lambda raw: bytes(raw), 'terminated': False}

# Named members of the parameterised families (gfx_families): formats met in real games.
ALIASES = {
    'saxman': 'lz~le16c.l1.oku.rfee.m3.n',          # Sega (Sonic 2 sound driver and others): packed size, then Okumura LZSS
    'rle-sega-planes': 'rle~l.r0.l0.z.p4',          # Sega Master System (Phantasy Star and many more): four plane passes
}
for _name, _member in ALIASES.items():
    CODECS[_name] = CODECS[_member]

# Codecs worth trying first on each system (all the fixed ones are tried in the end).
PREFERRED = {
    'snes': ('lz2', 'lz2-le', 'lz3', 'hal', 'lz5', 'konami-snes', 'lzss-00-le16', 'lzss-20-le16'),
    'gb': ('hal', 'lz3', 'lz2', 'rle-konami', 'rle-escape', 'packbits'),
    'gbc': ('lz3', 'hal', 'lz2', 'rle-konami', 'rle-escape', 'packbits'),
    'nes': ('rle-konami', 'rle-escape', 'hal', 'lz2', 'packbits'),
    'genesis': ('nemesis', 'kosinski', 'enigma', 'comper', 'kosinski-moduled', 'saxman', 'lzss-00-le16'),
    'sms': ('rle-sega-planes', 'rle-pairs', 'packbits', 'lzss-00-le16'),
}
# Members of the parameterised families found in real games by trace/codec_survey.py search;
# recognise() tries them after the fixed codecs.
MEMBERS = {
    'snes': ('lz~le16.l1.oku.b0.m3.s',      # Sculptured Software: Super Star Wars trilogy, Boxing Legends of the Ring
             'lz~le16.m0.L4lle.b1.m3.s',    # SimAnt
             'lz~le16.m1.L4lbe.r1.m2.s',    # Wing Commander
             'lz~le16.l0.L4hle.b0.m3.s',    # Bahamut Lagoon
             'rle~l.r0.l0.z.p1'),           # Run Saber
    'gb': ('lz~le16.l1.L4lle.b0.m3.s',      # Tose: Dragon Warrior Monsters, Harvest Moon GB, Legend of the River King
           'lz~le16.l1.oku.b0.m3.s',        # Donkey Kong (1994)
           'rle~l.r0.l0.z.p1', 'rle~l.r0.l0.n.p1', 'rle~h.r0.l0.n.p1'),     # Cave Noire
    'gbc': ('lz~le16.l1.L4lle.b0.m3.s',     # Tose: Dragon Warrior I & II, III, Game & Watch Gallery 3, Harvest Moon GBC
            'lz~le16.l1.oku.b0.m3.s',
            'rle~l.r0.l0.z.p1', 'rle~h.r0.l0.n.p1', 'rle~l.r0.l0.n.p1'),    # Tetris DX; Magi Nation
    'nes': ('rle~l.r0.l0.z.p1', 'rle~h.r0.l0.n.p1', 'rle~l.r0.l0.n.p1'),
    'sms': ('rle~l.r0.l0.z.p1', 'rle~h.r0.l0.n.p1', 'rle~l.r0.l0.n.p1'),
    'genesis': (),
}
# Codecs that only recognise() runs (the plain search in graphics_trace would spend long on them).
_RECOGNISE_ONLY = ('raw', 'lz-ring256')


# Recognising a block runs the same decoder from the same place many times over (several
# layouts, several tiles of one scene), so results are kept per ROM. bytes objects remember
# their hash, which makes "the same ROM" cheap to tell.
_cache: dict = {}
_cache_rom = [None, 0]      # (hash, length) of the ROM the cache is for; bytes held


def decode(codec: str, data: bytes, start: int = 0, limit: int = MAX_OUT):
    """(unpacked bytes, stream bytes used); ValueError when the bytes at `start` are not a stream."""
    if not isinstance(data, bytes) or len(data) < 0x2000:
        return CODECS[codec]['decode'](data, start, limit)
    owner = (hash(data), len(data))
    if _cache_rom[0] != owner or _cache_rom[1] > 96 << 20:
        _cache.clear()
        _cache_rom[0], _cache_rom[1] = owner, 0
    key = (codec, start, limit)
    hit = _cache.get(key)
    if hit is None:
        try:
            hit = CODECS[codec]['decode'](data, start, limit)
            _cache_rom[1] += len(hit[0]) + 64
        except (ValueError, IndexError) as e:
            hit = e
            _cache_rom[1] += 64
        _cache[key] = hit
    if isinstance(hit, Exception):
        raise hit
    return hit


def encode(codec: str, raw: bytes, like: bytes | None = None) -> bytes:
    """Pack `raw`. `like` is the original stream being replaced: where a codec family has
    optional commands, only those the original used are emitted, and a result that would be
    shorter than the original is lengthened to the same size where the codec allows it."""
    entry = CODECS[codec]
    if 'map' in entry:
        return encode(entry['base'], map_contract(entry['map'], bytes(raw)), like)
    if like is not None and 'commands' in entry:
        stream = entry['encode'](bytes(raw), entry['commands'](like), len(like))
    elif like is not None and entry.get('exact'):
        # A bare stream has no end of its own: the game stops by a count kept elsewhere, and what
        # follows may be the rest of the same stream. Only a stream of exactly the old size is safe.
        stream = (entry['encode'](bytes(raw), len(like), like) if entry.get('likes') else
                  entry['encode'](bytes(raw), len(like)) if entry.get('sized') else entry['encode'](bytes(raw)))
        if len(stream) != len(like):
            raise ValueError(f'The edited data packs to {len(stream)} bytes and must be exactly {len(like)}: this '
                             'format has no end marker, so it can only be rewritten in the same space.')
    else:
        stream = entry['encode'](bytes(raw))
    again, used = entry['decode'](stream, 0, max(len(raw), 1))
    if again[:len(raw)] != bytes(raw) or (entry['terminated'] and (again != bytes(raw) or used != len(stream))):
        raise ValueError(f'{codec} encoder output failed its round-trip check')
    return stream


def reads_on_alike(codec: str, rom: bytes, edited: bytes, start: int, size: int, more: int = 0x400) -> bool:
    """A bare stream at `start` was replaced in `edited`. True when unpacking on past the block
    (`size` bytes of output) gives the same bytes from both ROMs: a game that keeps reading after
    the recognised stretch then sees what it saw before."""
    try:
        a = decode(codec, rom, start, size + more)[0]
    except (ValueError, IndexError):
        return True         # nothing follows that this codec can read
    try:
        b = CODECS[codec]['decode'](edited, start, size + more)[0]
    except (ValueError, IndexError):
        return False
    return a[size:] == b[size:]


def order_for(system: str) -> list[str]:
    first = [c for c in PREFERRED.get(system, ()) if c in CODECS]
    return first + [c for c in list(CODECS) if c not in first and c not in _RECOGNISE_ONLY
                    and '|' not in c and '~' not in c]


# ---- recognising a block from traced video memory ---------------------------------------
# graphics_trace.find_compressed_block calls recognise() when its own search finds nothing
# complete. It differs in three ways: stored-as-it-is data with made-up planes is found
# straight from the tags; stream starts come from every gap in the source offsets around
# the tile rather than from one walk; and each unpacked block is tried under the system's
# layouts (MAPS).

_HEAD = {'nemesis': 0x280, 'enigma': 8, 'rle-sega-planes': 2}


def _informative(d, i):
    return (d.tags[i] >> 28 & 7) in (1, 3) and d.data[i] not in (0x00, 0xFF)


def stream_anchors(d, start: int, length: int, window: int = 0x4000, gap: int = 0x100, most: int = 16) -> list[int]:
    """ROM offsets (header excluded) where the stream that produced d[start:start+length] may begin, likeliest first."""
    n = len(d.data)
    lo, hi = max(0, start - window), min(n, start + length + window)
    own = [d.tags[i] & 0x0FFFFFFF for i in range(start, start + length) if _informative(d, i)]
    r = 1
    while not own and r < 0x200:
        for i in (start - r, start + length - 1 + r):
            if lo <= i < hi and _informative(d, i):
                own.append(d.tags[i] & 0x0FFFFFFF)
        r += 1
    if not own:
        return []
    tlo = min(own)
    offs = sorted({d.tags[i] & 0x0FFFFFFF for i in range(lo, hi) if _informative(d, i)})
    out = []
    for g in (gap, 0x18):   # wide gaps first; then narrow ones, as a stray tag can sit just in front of a stream
        starts = [offs[0]] + [b for a, b in zip(offs, offs[1:]) if b - a > g]
        for x in [x for x in starts if x <= tlo][::-1][:most]:
            if x not in out:
                out.append(x)
    for x in sorted(set(own)):          # the tile's own lowest offsets: short streams, one per tile
        if x not in out and len(out) < 2 * most + 4:
            out.append(x)
    # Blocks often open with blank tiles, whose 00 and FF bytes were left out above; their tags
    # still say the stream begins a little earlier.
    weak = sorted({d.tags[i] & 0x0FFFFFFF for i in range(lo, hi)
                   if (d.tags[i] >> 28 & 7) in (1, 3) and d.data[i] in (0x00, 0xFF)})
    moved = []
    for x in out:
        for _ in range(4):
            k = bisect.bisect_left(weak, x)
            if k and x - weak[k - 1] <= 0x10:
                x = weak[bisect.bisect_left(weak, x - 0x10)]
            else:
                break
        if x not in moved:
            moved.append(x)
    return moved


def magic_starts(rom, skip, magic, anchors, most=3, reach=0x40000):
    """Where streams that open with `magic` begin (header excluded offsets), nearest in front of each anchor first.

    A stream that says what it is needs no guessing: the tile's bytes name stream bytes they were
    computed from, and the stream is one of the few that begin before those.
    """
    out = []
    for anchor in anchors:
        at = skip + anchor + 1
        for _ in range(most):
            at = rom.rfind(magic, max(skip, at - reach), at + len(magic) - 1)
            if at < 0:
                break
            if at - skip not in out:
                out.append(at - skip)
    return out


def _probe(d, start, length):
    target = bytes(d.data[start:start + length])
    if len(set(target)) > 2:
        return target, 0
    n = len(d.data)
    for r in range(8, 0x400, 8):
        for k in (start - r, start + r):
            if 0 <= k and k + 16 <= n and len(set(d.data[k:k + 16])) > 4:
                return bytes(d.data[k:k + 16]), k - start
    return None, 0


def _fit(d, out, start, length, target, probe, shift, bare=False):
    """Where `out` lies in the domain so that it reproduces the target and what surrounds it.

    A stream with an end marker or a size must agree with nine tenths of the 256 bytes on
    each side of the target (parts of a block are often overwritten later). The output of
    a bare stream runs on into whatever follows it in the ROM, so there the unbroken run of
    agreement around the target is taken instead, and must be at least three tiles long.
    Returns (score, domain index of out[0], first, last) with out[first:last] the part to keep.
    """
    best = None
    k = out.find(probe)
    tries = 0
    n = len(d.data)
    data = d.data
    while k >= 0 and tries < 8:
        tries += 1
        base = start + shift - k
        at = start - base
        if at >= 0 and at + length <= len(out) and out[at:at + length] == target:
            p, q = max(0, -base), min(len(out), n - base)
            if bare:
                lo, hi = at, at + length
                while lo > p and out[lo - 1] == data[base + lo - 1]:
                    lo -= 1
                while hi < q and out[hi] == data[base + hi]:
                    hi += 1
                if hi - lo >= max(48, 3 * length) and len(set(out[lo:hi])) > 4:
                    score = (lo == 0, False, hi - lo, -lo)
                    if best is None or score > best[0]:
                        best = (score, base, lo, hi)
            else:
                w0, w1 = max(p, at - 256), min(q, at + length + 256)
                if w1 - w0 >= 48:
                    near = sum(x == y for x, y in zip(out[w0:w1], data[base + w0:base + w1]))
                    if near * 10 >= (w1 - w0) * 9 and len(set(out[w0:w1])) > 2:
                        total = sum(x == y for x, y in zip(out[p:q], data[base + p:base + q]))
                        score = (near == w1 - w0, total == q - p, total, -p)
                        if best is None or score > best[0]:
                            best = (score, base, p, q)
        k = out.find(probe, k + 1)
    return best


def _recognise_raw(d, rom, skip, system, start, length, target):
    """Data stored as it is (perhaps with fewer planes than video memory holds)."""
    n = len(d.data)
    info = [(i - start, d.tags[i] & 0x0FFFFFFF) for i in range(start, start + length) if _informative(d, i)]
    if not info:
        return None
    rom_tagged = [(j, o) for j, o in info if (d.tags[start + j] >> 28 & 7) == 1]
    lo, hi = min(o for _, o in info), max(o for _, o in info)
    for text in ('',) + tuple(MAPS.get(system, ())):
        if text:
            m, k, entries = map_parse(text)
            if length % m:
                continue
            try:
                stored = map_contract(text, target)
            except ValueError:
                continue
        else:
            m = k = length
            entries = None
            stored = target
        if len(set(stored)) <= 2:
            continue
        cands = []
        for j, o in rom_tagged:         # a byte copied straight from the ROM says where its group is
            if entries is None:
                cands.append(o - j)
            else:
                g, jj = divmod(j, m)
                if entries[jj][0] >= 0:
                    cands.append(o - g * k - entries[jj][0])
        if len(stored) >= 12:
            at = rom.find(stored, skip + max(0, lo - 0x100), skip + hi + 0x100 + len(stored))
            if at >= 0:
                cands.append(at - skip)
        for r0 in dict.fromkeys(cands):
            if r0 < 0 or rom[skip + r0:skip + r0 + len(stored)] != stored:
                continue
            # grow over the neighbouring groups that also agree
            first, last = start, start + length     # domain span, whole groups
            f0 = r0
            while first - m >= 0 and f0 - k >= 0 and \
                    (map_expand(text, rom[skip + f0 - k:skip + f0]) if text else rom[skip + f0 - k:skip + f0]) == d.data[first - m:first] \
                    and start - first < 0x2000:
                first -= m
                f0 -= k
            f1 = r0 + len(stored)
            while last + m <= n and skip + f1 + k <= len(rom) and \
                    (map_expand(text, rom[skip + f1:skip + f1 + k]) if text else rom[skip + f1:skip + f1 + k]) == d.data[last:last + m] \
                    and last - start < 0x2000:
                last += m
                f1 += k
            if not text:
                # Equal bytes near a tagged offset are not yet a cause: either the tags themselves say
                # the tile was copied from there, or the agreement runs on for many tiles.
                told = sum(o == r0 + j for j, o in rom_tagged)
                if told * 2 < length and last - first < 256:
                    continue
            decoded = bytes(d.data[first:last])
            return {'codec': 'raw' + ('|' + text if text else ''), 'start': skip + f0, 'size': f1 - f0, 'decoded': decoded,
                    'domain_start': first, 'first': 0, 'last': len(decoded), 'complete': True}
    return None


def recognise(d, rom: bytes, skip: int, system: str, start: int, length: int, codecs=None, back: int = 8,
              anchors=None, layouts=None, exhaustive: bool = False) -> dict | None:
    """Find the stored block behind d[start:start+length] (d: a traced domain with .data and .tags).

    Returns None or {'codec', 'start' (file offset), 'size', 'decoded', 'domain_start', 'first',
    'last', 'complete'}: decoded[first:last] is what the domain holds from domain_start on, and
    `codec` (which may carry a layout: "lz2|3bpp") re-encodes it.
    """
    target = bytes(d.data[start:start + length])
    if len(set(target)) <= 1:
        return None
    plain = None
    if codecs is None:
        plain = _recognise_raw(d, rom, skip, system, start, length, target)
        # A short stretch stored as it is may be a literal block inside a packed stream; a codec
        # that explains the whole stream is the better answer, so look for one first.
        if plain and ('|' in plain['codec'] or plain['size'] >= 256):
            return plain
    probe, shift = _probe(d, start, length)
    if probe is None:
        return plain
    if anchors is None:
        anchors = stream_anchors(d, start, length)
    if not anchors:
        return plain
    whole = bytes(d.data)
    layouts = ('',) + tuple(MAPS.get(system, ())) if layouts is None else layouts
    best = None
    for name in (list(codecs) if codecs else order_for(system) + [c for c in _RECOGNISE_ONLY if c != 'raw']
                 + list(MEMBERS.get(system, ()))):
        entry = CODECS[name]
        terminated = entry['terminated']
        peek = entry.get('peek') or (None if terminated else (name, 0))
        seen = set()
        starts = [s for anchor in anchors for s in range(anchor, max(anchor - max(back, _HEAD.get(name, 0)), 0) - 1, -1)]
        if 'magic' in entry:
            starts = magic_starts(rom, skip, entry['magic'], anchors)
        for s in starts:
            if True:
                if s in seen:
                    continue
                seen.add(s)
                try:
                    if peek:
                        # most bytes are not a stream: look at a short piece of output before unpacking it all
                        head, _ = decode(peek[0], rom, skip + s + peek[1], 64)
                        if len(head) < 24 or not any(
                                (map_expand(t, head) if t else head)[:24] in whole for t in layouts):
                            continue
                    raw_out, used = decode(name, rom, skip + s, 0x10000 if terminated else 0x4000)
                except (ValueError, IndexError):
                    continue
                if used < 3:
                    continue
                for text in layouts:
                    out = map_expand(text, raw_out) if text else raw_out
                    fit = _fit(d, out, start, length, target, probe, shift, bare=not terminated)
                    if fit and (best is None or fit[0] > best[0]):
                        score, base, p, q = fit
                        full = name + ('|' + text if text else '')
                        size = used
                        if not terminated:
                            # keep only the stretch that agrees: the rest is not this stream's
                            try:
                                out, size = decode(full, rom, skip + s, q)
                            except (ValueError, IndexError):
                                continue
                            q = min(q, len(out))
                        best = (score, {'codec': full, 'start': skip + s, 'size': size,
                                        'decoded': out, 'domain_start': base + p, 'first': p, 'last': q,
                                        'complete': score[0]})
        if best and best[0][0] and (not exhaustive or best[0][1]):
            break       # (an exhaustive search goes on until something agrees everywhere)
    if plain and not (best and best[0][0] and CODECS[best[1]['codec']]['terminated']):
        return plain        # the tags name those ROM bytes; a bare stream is the weaker claim
    return best[1] if best else None


def search_families(d, rom: bytes, skip: int, system: str, start: int, length: int, most: int = 4, back: int = 4) -> dict | None:
    """Try every layout of the parameterised families (gfx_families) on the tile's likely stream starts.

    Slow (thousands of layouts); meant for studying a game offline. The codec named in the
    result is concrete: add it to MEMBERS to have it recognised from then on.
    """
    anchors = stream_anchors(d, start, length)[:most]
    if not anchors:
        return None
    whole = bytes(d.data)
    best = recognise(d, rom, skip, system, start, length, codecs=list(gfx_families.rle_grid()), back=back,
                     anchors=anchors, exhaustive=True)
    starts = sorted({s for a in anchors for s in range(max(a - back, 0), a + 1)}, reverse=True)
    for head in ('le16', 'be16', 'n'):
        body = 0 if head == 'n' else 2
        for flags in ('l1', 'm1', 'l0', 'm0'):
            if best and best['complete'] and CODECS[best['codec'].partition('|')[0]]['terminated']:
                return best
            # a start is worth the hundreds of layouts only if the literals it would hold are in video memory
            good = []
            for s in starts:
                runs = gfx_families.lz_literal_runs(flags[0] == 'm', int(flags[1]), rom, skip + s + body)
                if runs and all(any((map_expand(t, r) if t else r)[:len(r)] in whole for t in ('',)) for r in runs[:3]):
                    good.append(s)
            if not good:
                continue
            hit = recognise(d, rom, skip, system, start, length, codecs=list(gfx_families.lz_grid((head,), (flags,))),
                            back=0, anchors=good, layouts=('',), exhaustive=True)
            if hit and (best is None or (hit['complete'], hit['last'] - hit['first']) > (best['complete'], best['last'] - best['first'])):
                best = hit
    if best and best['codec'].startswith('lz~n.') and best['start'] - skip >= 2:
        # a bare stream may sit behind a packed-size word, which gives it an end
        body = best['codec'][len('lz~n.'):-len('.n')]
        for head in ('le16c', 'be16c', 'le16i', 'be16i'):
            framed = recognise(d, rom, skip, system, start, length, codecs=[f'lz~{head}.{body}.n'], back=0,
                               anchors=[best['start'] - skip - 2], layouts=('',))
            if framed and framed['complete']:
                return framed
    return best
