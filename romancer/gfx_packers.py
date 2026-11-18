"""Bit-stream packers met across many publishers' games; registered by gfx_codecs.

Each codec is decode(data, start=0, limit) -> (bytes, used) and encode(raw, ...) -> bytes,
as in gfx_codecs. These formats mix a bit stream with whole bytes, so what they unpack
is computed by the game's code rather than copied: the tracer reports such tiles as
derived, and only a decoder that reproduces them can tell which stream they came from.

  rnc1, rnc2   "RNC" + method byte, sizes and checksums, then the packed data.
               Method 1: Huffman-coded literal counts, distances and lengths, 16-bit words
               taken low bit first, literal bytes in between. Method 2: a byte-wise bit
               stream taken high bit first with fixed prefix codes.
"""
from __future__ import annotations

MAX_OUT = 0x10000
RNC_HEADER = 18
_RNC_MOST = 0x40000         # larger "unpacked sizes" are taken for chance, not for a stream


def common_prefix(raw: bytes, a: int, b: int, most: int) -> int:
    """How many bytes raw[a:] and raw[b:] share (a < b), up to `most` and the end of the data."""
    most = min(most, len(raw) - b)
    if most <= 0 or raw[a] != raw[b]:
        return 0
    k = 1
    step = 8
    while k < most:                     # doubling strides while they agree, then halving on the first miss
        step = min(step, most - k)
        if raw[a + k:a + k + step] == raw[b + k:b + k + step]:
            k += step
            step *= 2
        elif step == 1:
            break
        else:
            step //= 2
    return k


class MatchFinder:
    """Longest earlier match at a position, asked for in rising order of position (so that an
    encoder that skips over a long copy does not pay for the positions inside it)."""

    def __init__(self, raw: bytes, max_dist: int, max_len: int, min_len: int = 3, chain: int = 48):
        self.raw, self.max_dist, self.max_len, self.min_len, self.chain = raw, max_dist, max_len, min_len, chain
        self.key = min(min_len, 3)
        self.index: dict[bytes, list[int]] = {}
        self.filled = 0             # positions below this are in the index
        self.memo: dict[int, tuple] = {}

    def at(self, i: int) -> tuple:
        hit = self.memo.get(i)
        if hit is not None:
            return hit
        raw, key, index = self.raw, self.key, self.index
        while self.filled + key <= i:
            index.setdefault(raw[self.filled:self.filled + key], []).append(self.filled)
            self.filled += 1
        best = (0, 0)
        tried = 0
        for at in reversed(index.get(raw[i:i + key], ())):
            dist = i - at
            if dist > self.max_dist or tried >= self.chain:
                break
            tried += 1
            k = best[0]
            if k and raw[at + k:at + k + 1] != raw[i + k:i + k + 1]:
                continue
            k = common_prefix(raw, at, i, self.max_len)
            if k > best[0]:
                best = (k, dist)
                if k >= self.max_len:
                    break
        for dist in range(1, key):          # nearer than the key reaches: runs
            if i - dist >= 0:
                k = common_prefix(raw, i - dist, i, self.max_len)
                if k > best[0]:
                    best = (k, dist)
        if best[0] < self.min_len:
            best = (0, 0)
        self.memo[i] = best
        return best


def lz_matches(raw: bytes, max_dist: int, max_len: int, min_len: int = 3, chain: int = 48):
    """Longest earlier match at every position: a list of (length, distance), (0, 0) where there is none."""
    n = len(raw)
    out = [(0, 0)] * n
    index: dict[bytes, list[int]] = {}
    key = min(min_len, 3)
    for i in range(n):
        if i >= key:
            index.setdefault(raw[i - key:i], []).append(i - key)     # positions whose key ends before i
        # the entry for position i - key + 1 .. i - 1 overlaps i; a match may still start there
        best = (0, 0)
        cands = index.get(raw[i:i + key], ())
        tried = 0
        for at in reversed(cands):
            dist = i - at
            if dist > max_dist:
                break
            tried += 1
            if tried > chain:
                break
            k = 0
            while k < max_len and i + k < n and raw[at + k] == raw[i + k]:
                k += 1
            if k > best[0]:
                best = (k, dist)
                if k == max_len:
                    break
        # a run: the byte(s) just written, repeated (the distance is shorter than the key)
        for dist in range(1, key):
            if i - dist >= 0:
                k = 0
                while k < max_len and i + k < n and raw[i + k - dist] == raw[i + k]:
                    k += 1
                if k > best[0]:
                    best = (k, dist)
        out[i] = best if best[0] >= min_len else (0, 0)
    return out


def lz_ladder(raw: bytes, max_dist: int, max_len: int, min_len: int = 2, chain: int = 96):
    """At every position, the matches worth choosing between: [(length, distance)] with both rising,
    each the nearest match of its length (a nearer copy costs fewer bits in most formats)."""
    n = len(raw)
    out = [()] * n
    index: dict[bytes, list[int]] = {}
    key = min(min_len, 3)
    for i in range(n):
        if i >= key:
            index.setdefault(raw[i - key:i], []).append(i - key)
        steps = []
        top = min_len - 1
        for dist in range(1, key):                  # nearer than the key reaches: runs
            if i - dist >= 0 and top < max_len:
                k = common_prefix(raw, i - dist, i, max_len)
                if k > top:
                    top = k
                    steps.append((k, dist))
        tried = 0
        for at in reversed(index.get(raw[i:i + key], ())):
            dist = i - at
            if dist > max_dist or tried >= chain or top >= max_len:
                break
            tried += 1
            if raw[at + top:at + top + 1] != raw[i + top:i + top + 1] and top >= key:
                continue                            # cannot be longer than what is already had
            k = common_prefix(raw, at, i, max_len)
            if k > top:
                top = k
                steps.append((k, dist))
        out[i] = tuple(steps)
    return out


def crc16_arc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = crc >> 1 ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _be32(data, at):
    return data[at] << 24 | data[at + 1] << 16 | data[at + 2] << 8 | data[at + 3]


def _rnc_header(data, start, method, limit):
    if data[start:start + 4] != b'RNC' + bytes([method]) or start + RNC_HEADER > len(data):
        raise ValueError('not an RNC stream')
    size, packed = _be32(data, start + 4), _be32(data, start + 8)
    if not 0 < size <= max(limit, MAX_OUT) or size > _RNC_MOST or not 0 < packed <= size + 0x400 \
            or start + RNC_HEADER + packed > len(data) + 2:
        raise ValueError('RNC sizes are out of range')
    return size, packed


def rnc_info(stream: bytes) -> dict:
    """The header fields an encoder keeps when it replaces `stream`."""
    return {'leeway': stream[16], 'chunks': stream[17]}


def _rnc_wrap(method, raw, body, chunks, like):
    leeway = like['leeway'] if like else 0
    head = b'RNC' + bytes([method]) + len(raw).to_bytes(4, 'big') + len(body).to_bytes(4, 'big') \
        + crc16_arc(raw).to_bytes(2, 'big') + crc16_arc(body).to_bytes(2, 'big') + bytes((leeway, chunks & 0xFF))
    return head + bytes(body)


# ---- method 1 ----------------------------------------------------------------------

class _Words:
    """16-bit little-endian words taken low bit first, with one word always looked at ahead;
    literal bytes are read from where that word is, and the look-ahead is then taken again."""
    __slots__ = ('data', 'pos', 'buf', 'count', 'end')

    def __init__(self, data, pos, end):
        self.data, self.pos, self.end = data, pos, end
        self.buf = self._word()
        self.count = 16

    def _word(self):
        p = self.pos
        if p > self.end + 2:
            raise ValueError('stream is truncated')
        d = self.data
        return (d[p] if p < len(d) else 0) | (d[p + 1] if p + 1 < len(d) else 0) << 8

    def read(self, n):
        v = self.buf & ((1 << n) - 1)
        self.buf >>= n
        self.count -= n
        if self.count < 16:
            self.pos += 2
            self.buf |= self._word() << self.count
            self.count += 16
        return v

    def literal(self, n):
        if self.pos + n > self.end + 2 or self.pos + n > len(self.data):
            raise ValueError('stream is truncated')
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        self.count -= 16
        self.buf &= (1 << self.count) - 1
        self.buf |= self._word() << self.count
        self.count += 16
        return chunk


def _rnc1_table(bits):
    num = bits.read(5)
    lens = [bits.read(4) for _ in range(num)]
    table = {}
    code = 0
    for width in range(1, 16):
        for value, w in enumerate(lens):
            if w == width:
                # the stream holds the code high bit first; taken low bit first that reads mirrored
                table[(width, int(f'{code:0{width}b}'[::-1], 2))] = value
                code += 1
        code <<= 1
    return table, max(lens, default=0)


def _rnc1_value(bits, table):
    tab, widest = table
    for width in range(1, widest + 1):
        value = tab.get((width, bits.buf & ((1 << width) - 1)))
        if value is not None:
            bits.read(width)
            if value >= 2:
                value = 1 << (value - 1) | bits.read(value - 1)
            return value
    raise ValueError('no such code')


def rnc1_decode(data, start=0, limit=MAX_OUT):
    size, packed = _rnc_header(data, start, 1, limit)
    bits = _Words(data, start + RNC_HEADER, start + RNC_HEADER + packed)
    bits.read(2)
    out = bytearray()
    while len(out) < size:
        raw, dist, length = _rnc1_table(bits), _rnc1_table(bits), _rnc1_table(bits)
        count = bits.read(16)
        if not count:
            raise ValueError('empty chunk')
        while True:
            n = _rnc1_value(bits, raw)
            if n:
                out += bits.literal(n)
            count -= 1
            if count <= 0:
                break
            back = _rnc1_value(bits, dist) + 1
            n = _rnc1_value(bits, length) + 2
            if back > len(out):
                raise ValueError('copy from before the start')
            if back >= n:
                out += out[len(out) - back:len(out) - back + n]
            else:
                for _ in range(n):
                    out.append(out[-back])
            if len(out) > size:
                raise ValueError('more data than the header says')
    if len(out) != size:
        raise ValueError('more data than the header says')
    return bytes(out), RNC_HEADER + packed


class _WordWriter:
    """The writer for _Words: a word is given a place in the stream at the moment the reader looks at it."""

    def __init__(self):
        self.out = bytearray(2)
        self.cur = None      # index of the word being filled, and how many of its bits are still free
        self.free = 0
        self.peek = 0        # index of the word the reader has looked at but not started

    def put(self, value, n):
        while n:
            if not self.free:
                self.cur, self.free = self.peek, 16
                self.peek = len(self.out)
                self.out += b'\0\0'
            take = min(n, self.free)
            word = self.out[self.cur] | self.out[self.cur + 1] << 8
            word |= (value & ((1 << take) - 1)) << (16 - self.free)
            self.out[self.cur] = word & 0xFF
            self.out[self.cur + 1] = word >> 8
            value >>= take
            n -= take
            self.free -= take

    def code(self, code, width):
        for k in range(width - 1, -1, -1):
            self.put(code >> k & 1, 1)

    def literal(self, chunk):
        del self.out[self.peek:]          # the bytes take the place of the word looked at ahead
        self.out += chunk
        self.peek = len(self.out)
        self.out += b'\0\0'

    def finish(self):
        del self.out[self.peek:]
        return self.out


def _code_lengths(freq: dict, most: int = 15) -> dict:
    """Huffman code widths (at most `most` bits) for the symbols of `freq`."""
    if not freq:
        return {}
    if len(freq) == 1:
        return {next(iter(freq)): 1}
    f = dict(freq)
    while True:
        heap = sorted((n, [s]) for s, n in f.items())
        width = dict.fromkeys(f, 0)
        while len(heap) > 1:
            a, b = heap[0], heap[1]
            for s in a[1] + b[1]:
                width[s] += 1
            heap = sorted(heap[2:] + [(a[0] + b[0], a[1] + b[1])], key=lambda x: x[0])
        if max(width.values()) <= most:
            return width
        f = {s: (n + 1) // 2 for s, n in f.items()}


def _canonical(width: dict) -> dict:
    """symbol -> (code, width), numbered as the unpacker numbers them."""
    out = {}
    code = 0
    for w in range(1, 16):
        for s in sorted(width):
            if width[s] == w:
                out[s] = (code, w)
                code += 1
        code <<= 1
    return out


def _symbol(value):
    """(symbol, extra bits, how many) for a count, a distance or a length."""
    if value < 2:
        return value, 0, 0
    n = value.bit_length()
    return n, value - (1 << (n - 1)), n - 1


def _rnc1_parse(raw, ladder, run_bits, dist_bits, len_bits):
    """Cheapest split into literals and copies under the given code widths ({symbol: bits}; a
    copy also pays `run_bits` for the count of literals in front of it). Returns the tuples
    (literal bytes, (length, distance) or None), the last one without a copy."""
    n = len(raw)
    INF = 1 << 60
    spare_d = max(dist_bits.values()) + 2
    spare_l = max(len_bits.values()) + 2
    cost = [INF] * (n + 1)
    step = [(1, 0)] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        c, how = cost[i + 1] + 8, (1, 0)
        low = 2
        for k, dist in ladder[i]:
            d = dist - 1
            ds = d if d < 2 else d.bit_length()
            dcost = run_bits + dist_bits.get(ds, spare_d) + (ds - 1 if ds >= 2 else 0)
            for length in (range(low, k + 1) if k <= 12 else list(range(low, 13)) + [k - 1, k]):
                if length < low:
                    continue
                v = length - 2
                ls = v if v < 2 else v.bit_length()
                bits = dcost + len_bits.get(ls, spare_l) + (ls - 1 if ls >= 2 else 0)
                if cost[i + length] + bits < c:
                    c, how = cost[i + length] + bits, (length, dist)
            low = k + 1
        cost[i], step[i] = c, how
    tuples = []
    i = start = 0
    while i < n:
        k, dist = step[i]
        if k > 1:
            tuples.append((raw[start:i], (k, dist)))
            i += k
            start = i
        else:
            i += 1
            if i - start >= 0x7000:         # more than one count can say: close the chunk here
                tuples.append((raw[start:i], None))
                start = i
    tuples.append((raw[start:n], None))
    return tuples


def _rnc1_widths(tuples):
    """Code widths the tuples would get: (average bits of a literal count, {distance symbol: bits}, {length symbol: bits})."""
    fr, fd, fl = {}, {}, {}
    for lit, match in tuples:
        sym = _symbol(len(lit))[0]
        fr[sym] = fr.get(sym, 0) + 1
        if match:
            sym = _symbol(match[1] - 1)[0]
            fd[sym] = fd.get(sym, 0) + 1
            sym = _symbol(match[0] - 2)[0]
            fl[sym] = fl.get(sym, 0) + 1
    wr = _code_lengths(fr)
    runs = sum(fr.values())
    return (sum(wr[x] * fr[x] for x in fr) / runs if runs else 3), _code_lengths(fd) or {0: 4}, _code_lengths(fl) or {0: 4}


def rnc1_encode(raw, like=None, size=None):
    """Three rounds of: cheapest parse under the code widths of the round before, then new widths; the smallest wins."""
    raw = bytes(raw)
    n = len(raw)
    if not 0 < n <= _RNC_MOST:
        raise ValueError('data is too long for this codec')
    ladder = lz_ladder(raw, 0x8000, 0x1000, 2, chain=128)
    widths = (3, {x: 4 + (x > 8) for x in range(16)}, {x: 3 + (x > 3) for x in range(16)})
    best = None
    for _ in range(3):
        tuples = _rnc1_parse(raw, ladder, *widths)
        stream = _rnc1_emit(raw, tuples, like)
        if best is None or len(stream) < len(best):
            best = stream
        widths = _rnc1_widths(tuples)
    return best


def _rnc1_emit(raw, tuples, like):
    chunks, cur = [], []
    for t in tuples:
        cur.append(t)
        if t[1] is None or len(cur) >= 0x7FF:
            if t[1] is not None:
                # close the chunk with an empty literal run after this match
                chunks.append(cur + [(b'', None)])
            else:
                chunks.append(cur)
            cur = []
    if len(chunks) > 255:
        raise ValueError('data is too long for this codec')
    w = _WordWriter()
    w.put(0, 2)
    for chunk in chunks:
        fr, fd, fl = {}, {}, {}
        for lit, match in chunk:
            s = _symbol(len(lit))[0]
            fr[s] = fr.get(s, 0) + 1
            if match:
                s = _symbol(match[1] - 1)[0]
                fd[s] = fd.get(s, 0) + 1
                s = _symbol(match[0] - 2)[0]
                fl[s] = fl.get(s, 0) + 1
        codes = []
        for f in (fr, fd, fl):
            width = _code_lengths(f)
            num = max(width) + 1 if width else 0
            w.put(num, 5)
            for s in range(num):
                w.put(width.get(s, 0), 4)
            codes.append(_canonical(width))
        w.put(len(chunk), 16)
        for lit, match in chunk:
            fields = [(codes[0], len(lit))]
            if match:
                fields += [(codes[1], match[1] - 1), (codes[2], match[0] - 2)]
            for k, (table, value) in enumerate(fields):
                s, extra, bits = _symbol(value)
                w.code(*table[s])
                if bits:
                    w.put(extra, bits)
                if k == 0 and lit:
                    w.literal(lit)
    return _rnc_wrap(1, raw, w.finish(), len(chunks), like)


# ---- method 2 ----------------------------------------------------------------------

class _ByteBits:
    """Bits taken high bit first from bytes that are fetched only when a bit is wanted; whole bytes in between."""
    __slots__ = ('data', 'pos', 'end', 'cur', 'left')

    def __init__(self, data, pos, end):
        self.data, self.pos, self.end = data, pos, end
        self.cur = self.left = 0

    def byte(self):
        if self.pos >= self.end or self.pos >= len(self.data):
            raise ValueError('stream is truncated')
        b = self.data[self.pos]
        self.pos += 1
        return b

    def bit(self):
        if not self.left:
            self.cur = self.byte()
            self.left = 8
        self.left -= 1
        return self.cur >> self.left & 1


def rnc2_decode(data, start=0, limit=MAX_OUT):
    size, packed = _rnc_header(data, start, 2, limit)
    s = _ByteBits(data, start + RNC_HEADER, start + RNC_HEADER + packed)
    bit, byte = s.bit, s.byte
    bit(); bit()
    out = bytearray()
    while True:
        if len(out) > size:
            raise ValueError('more data than the header says')
        if not bit():
            out.append(byte())
            continue
        n = 2
        high = 0
        far = False
        if not bit():
            n = n << 1 | bit()
            if bit():
                n = (n - 1) << 1 | bit()
                if n == 9:
                    count = 0
                    for _ in range(4):
                        count = count << 1 | bit()
                    count = (count + 3) * 4
                    if s.pos + count > s.end:
                        raise ValueError('stream is truncated')
                    out += data[s.pos:s.pos + count]
                    s.pos += count
                    continue
            far = True
        elif bit():
            n += 1
            if bit():
                n = byte()
                if not n:
                    if bit():
                        continue
                    break
                n += 8
            far = True
        if far and bit():
            high = bit()
            if bit():
                high = high << 1 | bit() | 4
                if not bit():
                    high = high << 1 | bit()
            elif not high:
                high = 2 | bit()
        back = (high << 8 | byte()) + 1
        if back > len(out):
            raise ValueError('copy from before the start')
        if back >= n:
            out += out[len(out) - back:len(out) - back + n]
        else:
            for _ in range(n):
                out.append(out[-back])
    if len(out) != size:
        raise ValueError('more data than the header says')
    return bytes(out), RNC_HEADER + packed


class _ByteBitWriter:
    def __init__(self):
        self.out = bytearray()
        self.at = None
        self.left = 0

    def bits(self, *values):
        for v in values:
            if not self.left:
                self.at = len(self.out)
                self.out.append(0)
                self.left = 8
            self.left -= 1
            self.out[self.at] |= v << self.left

    def byte(self, b):
        self.out.append(b)


_RNC2_LEN = {4: (0, 0), 5: (1, 0), 6: (0, 1, 0), 7: (0, 1, 1), 8: (1, 1, 0)}


def _rnc2_high(w, high):
    if high == 0:
        w.bits(0)
    elif high == 1:
        w.bits(1, 1, 0)
    elif high < 4:
        w.bits(1, 0, 0, high & 1)
    elif high < 8:
        w.bits(1, high >> 1 & 1, 1, high & 1, 1)
    else:
        w.bits(1, high >> 2 & 1, 1, high >> 1 & 1, 0, high & 1)


def _rnc2_high_bits(high):
    return 1 if high == 0 else 3 if high == 1 else 4 if high < 4 else 5 if high < 8 else 6


def _rnc2_cost(length, dist):
    """Bits a copy takes, or None when the format has no such copy."""
    if length == 2:
        return 11 if dist <= 256 else None
    high = _rnc2_high_bits((dist - 1) >> 8) + 8
    if length == 3:
        return 4 + high
    if length <= 8:
        return 2 + len(_RNC2_LEN[length]) + high
    return 12 + high


def rnc2_encode(raw, like=None, size=None):
    """The cheapest split into literals (9 bits) and copies; runs of twelve literals or more go out as blocks."""
    raw = bytes(raw)
    n = len(raw)
    if not 0 < n <= _RNC_MOST:
        raise ValueError('data is too long for this codec')
    ladder = lz_ladder(raw, 0x1000, 263, 2)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    step = [(1, 0)] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        c, how = cost[i + 1] + 9, (1, 0)
        low = 2
        for k, dist in ladder[i]:
            for length in range(low, k + 1) if k <= 12 else list(range(low, min(k, 12) + 1)) + [k - 1, k]:
                if length < low:
                    continue
                bits = _rnc2_cost(length, dist)
                if bits is not None and cost[i + length] + bits < c:
                    c, how = cost[i + length] + bits, (length, dist)
            low = k + 1
        cost[i], step[i] = c, how
    w = _ByteBitWriter()
    w.bits(0, 0)
    i = 0
    run = 0             # literals waiting to be written

    def flush(upto):
        nonlocal run
        at = upto - run
        while run >= 12:
            count = min(run // 4, 18)
            w.bits(1, 0, 1, 1, 1, *(count - 3 >> k & 1 for k in (3, 2, 1, 0)))
            for b in raw[at:at + count * 4]:
                w.byte(b)
            at += count * 4
            run -= count * 4
        for b in raw[at:upto]:
            w.bits(0)
            w.byte(b)
        run = 0

    while i < n:
        k, dist = step[i]
        if k == 1:
            run += 1
            i += 1
            continue
        flush(i)
        high, low = divmod(dist - 1, 256)
        if k == 2:
            w.bits(1, 1, 0)
        elif k == 3:
            w.bits(1, 1, 1, 0)
            _rnc2_high(w, high)
        elif k <= 8:
            w.bits(1, 0, *_RNC2_LEN[k])
            _rnc2_high(w, high)
        else:
            w.bits(1, 1, 1, 1)
            w.byte(k - 8)
            _rnc2_high(w, high)
        w.byte(low)
        i += k
    flush(n)
    w.bits(1, 1, 1, 1)
    w.byte(0)
    w.bits(0)
    return _rnc_wrap(2, raw, w.out, 1, like)


CODECS = {
    'rnc1': {'decode': rnc1_decode, 'encode': rnc1_encode, 'terminated': True, 'commands': rnc_info, 'magic': b'RNC\x01'},
    'rnc2': {'decode': rnc2_decode, 'encode': rnc2_encode, 'terminated': True, 'commands': rnc_info, 'magic': b'RNC\x02'},
}


# ---- bit-stream LZSS over a 256-byte ring (Quintet: ActRaiser, Soul Blazer, Illusion of Gaia, ...) ----
# Unpacked size (16 bits, low byte first), then bits taken high bit first: 1 + eight bits is a
# literal; 0 + eight bits (ring position) + four bits (length - 2) copies from the ring, which
# starts filled with 20 and is written from position EF.

class _MsbBits:
    __slots__ = ('data', 'pos', 'bit')

    def __init__(self, data, pos):
        self.data, self.pos, self.bit = data, pos, 0

    def read(self, n):
        v = 0
        data = self.data
        for _ in range(n):
            if self.pos >= len(data):
                raise ValueError('stream is truncated')
            v = v << 1 | (data[self.pos] >> (7 - self.bit) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit = 0
                self.pos += 1
        return v

    def used(self, start):
        return self.pos - start + (1 if self.bit else 0)


def ring256_decode(data, start=0, limit=MAX_OUT, framed=True):
    if start + 3 > len(data):
        raise ValueError('stream is truncated')
    size = limit
    if framed:
        size = data[start] | data[start + 1] << 8
        if not 0 < size <= limit:
            raise ValueError('size header is out of range')
    bits = _MsbBits(data, start + 2 if framed else start)
    out = bytearray()
    while len(out) < size:
        if bits.read(1):
            out.append(bits.read(8))
        else:
            at = bits.read(8)
            n = bits.read(4) + 2
            here = len(out)
            dist = (0xEF + here - at) & 0xFF or 0x100
            for k in range(here - dist, here - dist + n):
                out.append(out[k] if k >= 0 else 0x20)
    del out[size:]
    return bytes(out), bits.used(start)


def ring256_encode(raw):
    raw = bytes(raw)
    n = len(raw)
    if not 0 < n <= 0xFFFF:
        raise ValueError('data is too long for this codec')
    found = lz_matches(raw, 0x100, 17, 2)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    step = [1] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        c, k = cost[i + 1] + 9, 1
        for length in range(2, found[i][0] + 1):
            if cost[i + length] + 13 < c:
                c, k = cost[i + length] + 13, length
        cost[i], step[i] = c, k
    acc = bits = 0
    out = bytearray((n & 0xFF, n >> 8))
    i = 0

    def put(value, width):
        nonlocal acc, bits
        acc = acc << width | value
        bits += width
        while bits >= 8:
            bits -= 8
            out.append(acc >> bits & 0xFF)
        acc &= (1 << bits) - 1

    while i < n:
        k = step[i]
        if k == 1:
            put(0x100 | raw[i], 9)
        else:
            put((0xEF + i - found[i][1]) & 0xFF, 9)
            put(k - 2, 4)
        i += k
    if bits:
        put(0, 8 - bits)
    return bytes(out)


# ---- flag-byte LZ with one-byte near copies and literal runs (Konami on the Mega Drive) ----
# Unpacked size (16 bits, high byte first), then flag bytes taken low bit first: 0 is a literal;
# 1 is a command byte c: 1F ends the stream; below 80 a copy of (c & 1F) + 3 bytes from
# ((c & 60) << 3 | next byte) back; 80-BF a copy of (c >> 4 & 3) + 2 bytes from c & 0F back;
# C0 and up (c & 3F) + 8 literal bytes.

def lzkn_decode(data, start=0, limit=MAX_OUT):
    n = len(data)
    if start + 3 > n:
        raise ValueError('stream is truncated')
    size = data[start] << 8 | data[start + 1]
    if not 0 < size <= limit:
        raise ValueError('size header is out of range')
    pos = start + 2
    out = bytearray()
    while True:
        if pos >= n:
            raise ValueError('stream is truncated')
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if pos >= n:
                raise ValueError('stream is truncated')
            c = data[pos]
            pos += 1
            if not flags >> bit & 1:
                out.append(c)
                continue
            if c == 0x1F:
                if len(out) != size:
                    raise ValueError('stream does not unpack to its stated size')
                return bytes(out), pos - start
            if c >= 0xC0:
                count = (c & 0x3F) + 8
                if pos + count > n:
                    raise ValueError('stream is truncated')
                out += data[pos:pos + count]
                pos += count
                continue
            if c >= 0x80:
                count, dist = (c >> 4 & 3) + 2, c & 0x0F
            else:
                if pos >= n:
                    raise ValueError('stream is truncated')
                count, dist = (c & 0x1F) + 3, (c & 0x60) << 3 | data[pos]
                pos += 1
            if not 0 < dist <= len(out):
                raise ValueError('copy from before the start')
            for _ in range(count):
                out.append(out[-dist])
            if len(out) > size:
                raise ValueError('stream does not unpack to its stated size')


def lzkn_encode(raw):
    raw = bytes(raw)
    n = len(raw)
    if not 0 < n <= 0xFFFF:
        raise ValueError('data is too long for this codec')
    far = lz_matches(raw, 0x3FF, 34, 2)
    near = lz_matches(raw, 0x0F, 5, 2)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    step = [(1, 0, 0)] * (n + 1)        # (bytes covered, kind: 0 literal 1 near 2 far 3 literal run, distance)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        c, how = cost[i + 1] + 9, (1, 0, 0)
        for length in range(2, near[i][0] + 1):
            if cost[i + length] + 9 < c:
                c, how = cost[i + length] + 9, (length, 1, near[i][1])
        k, dist = far[i]
        for length in range(3, k + 1):
            if (length - 3) | (dist >> 3 & 0x60) == 0x1F:
                continue                # that command byte is the end marker
            if cost[i + length] + 17 < c:
                c, how = cost[i + length] + 17, (length, 2, dist)
        for length in (8, 16, 32, 71):
            if i + length <= n and cost[i + length] + 9 + 8 * length < c:
                c, how = cost[i + length] + 9 + 8 * length, (length, 3, 0)
        cost[i], step[i] = c, how
    out = bytearray((n >> 8, n & 0xFF))
    tokens = 8
    flag_at = 0
    i = 0

    def flag(bit):
        nonlocal tokens, flag_at
        if tokens == 8:
            flag_at = len(out)
            out.append(0)
            tokens = 0
        out[flag_at] |= bit << tokens
        tokens += 1

    while i < n:
        length, kind, dist = step[i]
        if kind == 0:
            flag(0)
            out.append(raw[i])
        elif kind == 1:
            flag(1)
            out.append(0x80 | (length - 2) << 4 | dist)
        elif kind == 2:
            flag(1)
            out += bytes(((length - 3) | (dist >> 3 & 0x60), dist & 0xFF))
        else:
            flag(1)
            out.append(0xC0 | (length - 8))
            out += raw[i:i + length]
        i += length
    flag(1)
    out.append(0x1F)
    return bytes(out)


CODECS.update({
    'lz-ring256': {'decode': ring256_decode, 'encode': ring256_encode, 'terminated': True, 'peek': ('lz-ring256-body', 2)},
    'lz-konami-md': {'decode': lzkn_decode, 'encode': lzkn_encode, 'terminated': True},
})
# Any bytes unpack as a ring-256 stream, so a recogniser looks at the start of the body first.
BODIES = {'lz-ring256-body': {'decode': lambda data, start=0, limit=MAX_OUT: ring256_decode(data, start, limit, False),
                              'encode': lambda raw: ring256_encode(raw)[2:], 'terminated': False}}
