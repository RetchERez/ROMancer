"""Graphics compression codecs used by 8- and 16-bit console games.

Every codec is a pair of pure functions:

    decode(data, start=0, limit=0x10000) -> (decoded bytes, bytes consumed)
    encode(decoded) -> stream bytes

`decode` raises ValueError when the bytes at `start` are not a valid stream.
`encode` output always round-trips through `decode`; it is a plain greedy
encoder, so it may be larger than the original game's encoder produced.
romancer.graphics_trace matches these decoders against traced video memory
to recognise a compressed block, and re-encodes the block after an edit.

Families:
  lz2, lz2-le      Nintendo LC_LZ2 (Super Mario World / Zelda 3 offset order)
  lz3              Nintendo LC_LZ3 (Pokemon Gold/Silver/Crystal and relatives)
  hal              HAL Laboratory (Kirby, Adventures of Lolo, EarthBound)
  lzss-*           Okumura LZSS ring buffer, fill 00 or 20, optional 16-bit size
  kosinski         Sega Kosinski
  nemesis          Sega Nemesis (nibble run-length with a prefix code)
  enigma           Sega Enigma (tilemap words)
  packbits         PackBits run-length
  rle-konami       Konami run-length (NES era)
  rle-pairs        (count, value) pairs, zero count ends
"""
from __future__ import annotations

from collections import Counter

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


# ---- Okumura LZSS --------------------------------------------------------

def _lzss_decode(fill, header, data, start=0, limit=MAX_OUT):
    r = _Reader(data, start)
    want = None
    if header == 'le16':
        want = r.byte() | r.byte() << 8
        if not 0 < want <= limit:
            raise ValueError('size header is out of range')
    ring = bytearray([fill]) * 4096
    rp = 0xFEE
    out = bytearray()
    target = want if want is not None else limit
    while len(out) < target:
        if r.pos >= len(data):
            if want is None and out:
                break
            raise ValueError('stream is truncated')
        flags = r.byte()
        for bit in range(8):
            if len(out) >= target:
                break
            if flags >> bit & 1:
                if r.pos >= len(data):
                    if want is None:
                        return bytes(out), r.pos - start
                    raise ValueError('stream is truncated')
                b = r.byte()
                out.append(b)
                ring[rp] = b
                rp = (rp + 1) & 0xFFF
            else:
                if r.pos + 2 > len(data):
                    if want is None:
                        return bytes(out), r.pos - start
                    raise ValueError('stream is truncated')
                lo, hi = r.byte(), r.byte()
                at = lo | (hi & 0xF0) << 4
                for k in range((hi & 0x0F) + 3):
                    b = ring[(at + k) & 0xFFF]
                    out.append(b)
                    ring[rp] = b
                    rp = (rp + 1) & 0xFFF
    del out[target:]
    return bytes(out), r.pos - start


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
    n = len(raw)
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

    index: dict[bytes, list[int]] = {}
    indexed = 0
    i = 0
    while i < n:
        while indexed < i:
            index.setdefault(bytes(raw[indexed:indexed + 2]), []).append(indexed)
            indexed += 1
        best_len, best_at = 0, 0
        for at in reversed(index.get(bytes(raw[i:i + 2]), [])[-48:]):
            if i - at > 0x2000:
                break
            k = 0
            while k < 256 and i + k < n and raw[at + k] == raw[i + k]:
                k += 1
            if k > best_len:
                best_len, best_at = k, at
        dist = i - best_at
        if best_len >= 2 and best_len <= 5 and dist <= 256:
            put(0); put(0); put((best_len - 2) >> 1); put((best_len - 2) & 1)
            out.append((-dist) & 0xFF)
            i += best_len
        elif best_len >= 3:
            put(0); put(1)
            off = (-dist) & 0x1FFF
            if best_len <= 9:
                out += bytes((off & 0xFF, (off >> 5 & 0xF8) | (best_len - 2)))
            else:
                out += bytes((off & 0xFF, off >> 5 & 0xF8, best_len - 1))
            i += best_len
        else:
            put(1)
            out.append(raw[i])
            i += 1
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


def _packbits_encode(raw):
    out = bytearray()
    lit = bytearray()

    def flush():
        for p in range(0, len(lit), 128):
            chunk = lit[p:p + 128]
            out.append(len(chunk) - 1)
            out.extend(chunk)
        lit.clear()

    for value, k in _runs(raw, 128):
        if k >= 3:
            flush()
            out += bytes((257 - k, value))
        else:
            lit += bytes([value]) * k
    flush()
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

    for value, k in _runs(raw, 0x80):
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


# ---- registry ---------------------------------------------------------------

def _bind(fn, *head):
    return lambda *args, **kw: fn(*head, *args, **kw)


CODECS: dict[str, dict] = {}
for _name in _NINTENDO:
    CODECS[_name] = {'decode': _bind(_nintendo_decode, _name), 'encode': _bind(_nintendo_encode, _name), 'terminated': True,
                     'commands': _bind(_nintendo_commands, _name)}
for _fill in (0x00, 0x20):
    for _header in ('le16', 'raw'):
        CODECS[f'lzss-{_fill:02x}-{_header}'] = {'decode': _bind(_lzss_decode, _fill, _header),
                                                 'encode': _bind(_lzss_encode, _fill, _header), 'terminated': _header != 'raw'}
CODECS['kosinski'] = {'decode': _kosinski_decode, 'encode': _kosinski_encode, 'terminated': True}
CODECS['nemesis'] = {'decode': _nemesis_decode, 'encode': _nemesis_encode, 'terminated': True}
CODECS['enigma'] = {'decode': _enigma_decode, 'encode': _enigma_encode, 'terminated': True}
CODECS['rle-konami'] = {'decode': _konami_decode, 'encode': _konami_encode, 'terminated': True}
CODECS['rle-pairs'] = {'decode': _pairs_decode, 'encode': _pairs_encode, 'terminated': True}
CODECS['packbits'] = {'decode': _packbits_decode, 'encode': _packbits_encode, 'terminated': False}

# Codecs worth trying first on each system (all are tried in the end).
PREFERRED = {
    'snes': ('lz2', 'lz2-le', 'lz3', 'hal', 'lzss-00-le16', 'lzss-20-le16'),
    'gb': ('hal', 'lz3', 'lz2', 'rle-konami', 'packbits'),
    'gbc': ('lz3', 'hal', 'lz2', 'rle-konami', 'packbits'),
    'nes': ('rle-konami', 'hal', 'lz2', 'packbits'),
    'genesis': ('nemesis', 'kosinski', 'enigma', 'lzss-00-le16'),
    'sms': ('rle-pairs', 'packbits', 'lzss-00-le16'),
}


def decode(codec: str, data: bytes, start: int = 0, limit: int = MAX_OUT):
    return CODECS[codec]['decode'](data, start, limit)


def encode(codec: str, raw: bytes, like: bytes | None = None) -> bytes:
    """Pack `raw`. `like` is the original stream being replaced: where a codec family has
    optional commands, only those the original used are emitted, and a result that would be
    shorter than the original is lengthened to the same size where the codec allows it."""
    if like is not None and 'commands' in CODECS[codec]:
        stream = CODECS[codec]['encode'](bytes(raw), CODECS[codec]['commands'](like), len(like))
    else:
        stream = CODECS[codec]['encode'](bytes(raw))
    again, used = CODECS[codec]['decode'](stream, 0, max(len(raw), 1))
    if again[:len(raw)] != bytes(raw) or (CODECS[codec]['terminated'] and (again != bytes(raw) or used != len(stream))):
        raise ValueError(f'{codec} encoder output failed its round-trip check')
    return stream


def order_for(system: str) -> list[str]:
    first = [c for c in PREFERRED.get(system, ()) if c in CODECS]
    return first + [c for c in CODECS if c not in first]
