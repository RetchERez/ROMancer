"""Parameterised codec families: many one-off game formats are one layout of a common scheme.

A family member is named by its parameters, so a name found by the searcher
(trace/codec_survey.py search) is a complete, stable codec:

    lz~<header>.<flags>.<pack>.<mode>.m<minlen>.<end>     flag-byte LZSS
        header  n | le16 | be16 (unpacked size) | le16c | be16c (packed size, after the header)
                | le16i | be16i (packed size, header included)
        flags   l1 l0 m1 m0: flag bits taken LSB or MSB first; the value that means "literal"
        pack    oku            offset = b0 | (b1 & F0) << 4, length = b1 & 0F
                L<n><h|l><le|be>  the pair as a 16-bit word (le: b0 | b1 << 8), length in the
                               high or low n bits, offset in the rest
        mode    r<hex init>[+<hex fill>]  offset is a position in a ring that starts filled (with 00)
                b<bias>        offset + bias is a distance back from the write position
        end     s (size header) | n (runs to the size asked for) | z (a pair with offset field 0 ends it)
                | u (as n, without n's rule against copies from before the start; for looking, not for use)

    rle~<flag>.r<bias>.l<bias>.<end>.p<planes>            control-byte run length
        flag    h: bit 7 set is a run, clear a literal block; l: the reverse
        r, l    count = (control & 7F) + bias
        end     z | f | e (control byte 00 / FF / 80 ends) | n (none)
        planes  the stream holds that many passes; pass p fills bytes p, p + planes, ...

Each family has decode(params, data, start, limit) -> (bytes, used) and
encode(params, raw) -> bytes, plus parse(name) / name(params).
"""
from __future__ import annotations

MAX_OUT = 0x10000


# ---- flag-byte LZSS ---------------------------------------------------------

def lz_parse(name: str) -> dict:
    try:
        head, flags, pack, mode, minlen, end = name.split('~', 1)[1].split('.')
        p = {'header': head, 'msb': flags[0] == 'm', 'lit': int(flags[1]), 'pack': pack, 'minlen': int(minlen[1:]), 'end': end}
        if head not in ('n', 'le16', 'be16', 'le16c', 'be16c', 'le16i', 'be16i') or flags[0] not in 'lm' or end not in 'snzu':
            raise ValueError
        if pack == 'oku':
            p.update(lenbits=4, offbits=12)
        else:
            if pack[0] != 'L' or pack[-3] not in 'hl' or pack[-2:] not in ('le', 'be'):
                raise ValueError
            p.update(lenbits=int(pack[1:-3]), high=pack[-3] == 'h', le=pack[-2:] == 'le')
            p['offbits'] = 16 - p['lenbits']
        if mode[0] == 'r':
            init, _, fill = mode[1:].partition('+')
            p.update(ring=True, init=int(init, 16), fill=int(fill or '0', 16))
        elif mode[0] == 'b':
            p.update(ring=False, bias=int(mode[1:]))
        else:
            raise ValueError
        if (end == 's') != (head in ('le16', 'be16')):
            raise ValueError
        if (head[-1] in 'ci' and end != 'n') or (end == 'u' and head != 'n'):
            raise ValueError
        return p
    except (ValueError, IndexError):
        raise KeyError(name) from None


def _lz_pair(p, b0, b1):
    if p['pack'] == 'oku':
        return b0 | (b1 & 0xF0) << 4, b1 & 0x0F
    w = (b0 | b1 << 8) if p['le'] else (b0 << 8 | b1)
    n = p['lenbits']
    if p['high']:
        return w & ((1 << (16 - n)) - 1), w >> (16 - n)
    return w >> n, w & ((1 << n) - 1)


def _lz_unpair(p, off, length):
    if p['pack'] == 'oku':
        return off & 0xFF, (off >> 4 & 0xF0) | length
    n = p['lenbits']
    w = (length << (16 - n) | off) if p['high'] else (off << n | length)
    return (w & 0xFF, w >> 8) if p['le'] else (w >> 8, w & 0xFF)


def lz_decode(p, data, start=0, limit=MAX_OUT, notes=None):
    """A stream with no header and no end marker is held to a stricter rule: a copy from before
    the start of the output is an error (unless the ring starts with a fill other than 00, which
    real streams lean on). Without that, almost any bytes decode as such a stream."""
    strict = p['header'] == 'n' and p['end'] == 'n'
    pos = start
    n = len(data)
    target = limit
    stop = n
    head = p['header']
    sized = False
    if head != 'n':
        if pos + 2 > n:
            raise ValueError('stream is truncated')
        v = (data[pos] | data[pos + 1] << 8) if head[:2] == 'le' else (data[pos] << 8 | data[pos + 1])
        pos += 2
        if head[-1] in 'ci':
            if head[-1] == 'i':
                v -= 2
            if v < 2 or pos + v > n:
                raise ValueError('size header is out of range')
            stop = pos + v
        else:
            if not 0 < v <= limit:
                raise ValueError('size header is out of range')
            target = v
            sized = True
    out = bytearray()
    ring = p.get('ring')
    mask = (1 << p['offbits']) - 1
    if ring:
        init, fill = p['init'] & mask, p['fill']
    minlen = p['minlen']
    msb, lit, end = p['msb'], p['lit'], p['end']
    done = False
    until_end = end == 'z'
    while (until_end or len(out) < target) and not done:
        if until_end and len(out) > limit:
            raise ValueError('output exceeds the limit')
        if pos >= stop:
            if sized:
                raise ValueError('stream is truncated')
            break
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if len(out) >= target and not until_end:
                break
            f = (flags >> (7 - bit) if msb else flags >> bit) & 1
            if f == lit:
                if pos >= stop:
                    if sized:
                        raise ValueError('stream is truncated')
                    done = True
                    break
                out.append(data[pos])
                pos += 1
                continue
            if pos + 2 > stop:
                if sized:
                    raise ValueError('stream is truncated')
                done = True
                break
            off, length = _lz_pair(p, data[pos], data[pos + 1])
            pos += 2
            if end == 'z' and off == 0:
                done = True
                break
            length += minlen
            here = len(out)
            if ring:
                dist = (init + here - off) & mask
                if dist == 0:
                    dist = mask + 1
            else:
                dist = off + p['bias']
                if dist <= 0:
                    if strict and here >= 32:
                        pos -= 2
                        done = True
                        break
                    raise ValueError('bad distance')
            src = here - dist
            if src < 0:
                if strict and not (ring and fill):
                    if here >= 32:
                        pos -= 2            # whatever follows a bare stream is not part of it
                        done = True
                        break
                    raise ValueError('copy reaches outside the output')
                if not ring:
                    fill = 0                # games that count back from the write position read 00 there
                if notes is not None:
                    notes.add('prestart')
                for k in range(src, src + length):
                    out.append(out[k] if k >= 0 else fill)
            elif dist >= length:
                out += out[src:src + length]
            else:
                for k in range(length):
                    out.append(out[src + k])
    if not out:
        raise ValueError('empty stream')
    if until_end:
        if not done or len(out) > limit:
            raise ValueError('no terminator')
    elif len(out) > target:
        del out[target:]
    if head[-1] in 'ci':
        pos = stop
    return bytes(out), pos - start


def lz_encode(p, raw, allowed=None, size=None):
    """Cheapest split into literals (9 bits) and pairs (17 bits).

    `allowed`: what lz_features() found in the stream being replaced. A copy of 00 bytes from
    before the start of the output is only written when the original did the same (or the
    format's ring starts filled, where it is always safe): a game need not handle it.
    """
    raw = bytes(raw)
    n = len(raw)
    if not n or n > 0xFFFF:
        raise ValueError('data is too long for this codec')
    mask = (1 << p['offbits']) - 1
    maxlen = (1 << p['lenbits']) - 1 + p['minlen']
    minlen = max(2, p['minlen'])
    ring = p.get('ring')
    bias = 0 if ring else p['bias']
    if ring:
        maxdist, mindist = mask, 1          # a distance of the whole ring is left alone
        fill = p['fill']
        before = True
    else:
        maxdist = mask + bias
        mindist = max(1, bias + (1 if p['end'] == 'z' else 0))
        fill = 0
        before = bool(allowed and 'prestart' in allowed)
    if p['header'] == 'n' and p['end'] == 'n' and not (ring and fill):
        before = False                      # lz_decode holds bare streams to that
    # longest match at each position: (length, distance)
    best = [(0, 0)] * n
    index: dict[bytes, list[int]] = {}
    for i in range(n):
        if i >= 1:
            index.setdefault(raw[i - 1:i - 1 + minlen], []).append(i - 1)
        top, far = 0, 0
        for at in reversed(index.get(raw[i:i + minlen], [])[-64:]):
            dist = i - at
            if dist > maxdist:
                break
            if dist < mindist:
                continue
            k = 0
            while k < maxlen and i + k < n and raw[at + k] == raw[i + k]:
                k += 1
            if k > top:
                top, far = k, dist
                if k == maxlen:
                    break
        if before and raw[i] == fill:
            k = 1
            while k < maxlen and i + k < n and raw[i + k] == fill:
                k += 1
            if k > top and mindist <= i + k <= maxdist:
                top, far = k, i + k         # wholly in front of the output
        if top >= minlen:
            best[i] = (top, far)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    step = [1] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        c, k = cost[i + 1] + 9, 1
        top = best[i][0]
        for length in range(minlen, top + 1):
            if cost[i + length] + 17 < c:
                c, k = cost[i + length] + 17, length
        cost[i], step[i] = c, k
    msb, lit = p['msb'], p['lit']
    if size is not None and p['header'] == 'n' and p['end'] == 'n':
        _lz_pad(step, n, minlen, size)
    body = bytearray()
    i = 0
    tokens = 8
    flag_at = 0
    while i < n:
        if tokens == 8:
            flag_at = len(body)
            body.append(0xFF if lit else 0x00)      # unused bits read as literals, which copy nothing
            tokens = 0
        bit = (0x80 >> tokens) if msb else (1 << tokens)
        tokens += 1
        if step[i] == 1:
            body.append(raw[i])
        else:
            body[flag_at] ^= bit
            dist = best[i][1]
            off = (p['init'] + i - dist) & mask if ring else dist - bias
            body += bytes(_lz_unpair(p, off, step[i] - p['minlen']))
        i += step[i]
    if p['end'] == 'z':
        # a pair whose offset field is 0; it needs a flag bit of its own
        if tokens == 8:
            flag_at = len(body)
            body.append(0xFF if lit else 0x00)
            tokens = 0
        body[flag_at] ^= (0x80 >> tokens) if msb else (1 << tokens)
        body += bytes(_lz_unpair(p, 0, 0))
    head = p['header']
    if head == 'n':
        return bytes(body)
    v = len(body) + 2 if head[-1] == 'i' else len(body) if head[-1] == 'c' else n
    if v > 0xFFFF:
        raise ValueError('data is too long for this codec')
    return (bytes((v & 0xFF, v >> 8)) if head[:2] == 'le' else bytes((v >> 8, v & 0xFF))) + bytes(body)


def _lz_pad(step, n, minlen, size):
    """Make the parse in `step` longer until the stream is `size` bytes: a bare stream has no end
    of its own, so its replacement must fill the same space. A copy gives up bytes at its end to
    literals (each one byte and one flag more), or becomes literals altogether (which moves the
    flag count without the same cost, so that a size a new flag byte would jump over is still
    reached). Left as it is when the stream is already that long or longer, or no mix fits."""
    pairs = []
    lits = 0
    i = 0
    while i < n:
        if step[i] == 1:
            lits += 1
        else:
            pairs.append((step[i], i))
        i += step[i]
    count = len(pairs)
    if lits + 2 * count + (lits + count + 7) // 8 >= size:
        return
    by_length = sorted(pairs)
    room = sum(k - minlen for k, _ in pairs)
    forced = 0
    for burst in range(0, min(count, 24) + 1):      # copies turned into literals, shortest first
        if burst:
            forced += by_length[burst - 1][0] - minlen
        lo = lits + burst * minlen + 2 * (count - burst)
        tokens = lits + count + burst * (minlen - 1)
        for shrink in range(forced, room + 1):
            total = lo + shrink + (tokens + shrink + 7) // 8
            if total >= size:
                break
        else:
            continue
        if total != size:
            continue
        left = shrink - forced
        for k, at in by_length[:burst]:
            for j in range(at, at + k):
                step[j] = 1
        for k, at in by_length[burst:]:
            take = min(left, k - minlen)
            if take:
                step[at] = k - take
                for j in range(at + k - take, at + k):
                    step[j] = 1
                left -= take
        return


def lz_features(p, stream):
    """What a stream does that not every game's unpacker need handle: {'prestart'} when it copies
    from before the start of the output."""
    notes = set()
    try:
        lz_decode(p, stream, 0, MAX_OUT, notes)
    except ValueError:
        pass
    return notes


def lz_literal_runs(msb, lit, data, pos, tokens=48, least=4):
    """Runs of at least `least` literal bytes among the first tokens of a flag-byte stream at `pos`.

    Every layout of the family spends one byte on a literal and two on a pair, so this needs
    only the flag order and polarity. The searcher drops a start whose literal runs are not
    in video memory before trying the hundreds of layouts that share those two parameters.
    """
    runs = []
    cur = bytearray()
    n = len(data)
    count = 0
    while count < tokens and pos < n:
        flags = data[pos]
        pos += 1
        for bit in range(8):
            f = (flags >> (7 - bit) if msb else flags >> bit) & 1
            count += 1
            if f == lit:
                if pos >= n:
                    break
                cur.append(data[pos])
                pos += 1
            else:
                if len(cur) >= least:
                    runs.append(bytes(cur))
                cur = bytearray()
                pos += 2
    if len(cur) >= least:
        runs.append(bytes(cur))
    return runs


def lz_grid(headers=('n',), only_flags=None):
    """Layouts the searcher tries: bare streams, and with `headers` those behind an unpacked-size word
    (a framed stream may copy zeros from before its start, which a bare one is not allowed)."""
    packs = ['oku'] + [f'L{n}{hl}{e}' for n in (4, 3, 5, 6) for hl in 'hl' for e in ('le', 'be')]
    for head, flags in ((h, f) for h in headers for f in (only_flags or ('l1', 'm1', 'l0', 'm0'))):
        for pack in packs:
            lenbits = 4 if pack == 'oku' else int(pack[1:-3])
            size = 1 << (16 - lenbits)
            inits = sorted({size - (1 << lenbits) - 2, size - (1 << lenbits) - 1, size - (1 << lenbits), 0, 1, size - 1})
            modes = [f'r{x:x}' for x in inits] + ['b0', 'b1', 'b2']
            for mode in modes:
                for minlen in (3, 2, 1):
                    yield f'lz~{head}.{flags}.{pack}.{mode}.m{minlen}.{"n" if head == "n" else "s"}'


# ---- control-byte run length ----------------------------------------------------

_RLE_END = {'z': 0x00, 'f': 0xFF, 'e': 0x80, 'n': None}


def rle_parse(name: str) -> dict:
    try:
        flag, r, l, end, planes = name.split('~', 1)[1].split('.')
        if flag not in 'hl' or r[0] != 'r' or l[0] != 'l' or end not in _RLE_END or planes[0] != 'p':
            raise ValueError
        p = {'run_high': flag == 'h', 'rb': int(r[1:]), 'lb': int(l[1:]), 'end': end, 'planes': int(planes[1:])}
        if not 1 <= p['planes'] <= 8:
            raise ValueError
        return p
    except (ValueError, IndexError):
        raise KeyError(name) from None


def _rle_pass(p, data, pos, limit):
    out = bytearray()
    end = _RLE_END[p['end']]
    n = len(data)
    while True:
        if pos >= n:
            if end is None and out:
                break
            raise ValueError('stream is truncated')
        c = data[pos]
        pos += 1
        if end is not None and c == end:
            break
        high = bool(c & 0x80)
        k = (c & 0x7F) + (p['rb'] if high == p['run_high'] else p['lb'])
        if k <= 0 or pos + (1 if high == p['run_high'] else k) > n:
            if end is None and len(out) >= 16:
                pos -= 1                # whatever follows a bare stream is not part of it
                break
            raise ValueError('zero-length block' if k <= 0 else 'stream is truncated')
        if high == p['run_high']:
            out += bytes([data[pos]]) * k
            pos += 1
        else:
            out += data[pos:pos + k]
            pos += k
        if end is None:
            if len(out) >= limit:
                break
        elif len(out) > limit:
            raise ValueError('output exceeds the limit')
    return out, pos


def rle_decode(p, data, start=0, limit=MAX_OUT):
    planes = p['planes']
    pos = start
    parts = []
    for _ in range(planes):
        part, pos = _rle_pass(p, data, pos, limit // planes + 1 if p['end'] == 'n' else limit)
        parts.append(part)
    if planes == 1:
        out = parts[0]
        if p['end'] == 'n':
            del out[limit:]
    else:
        size = len(parts[0])
        if any(len(x) != size for x in parts):
            if p['end'] != 'n':
                raise ValueError('the passes differ in length')
            size = min(len(x) for x in parts)
        out = bytearray(size * planes)
        for k, part in enumerate(parts):
            out[k::planes] = part[:size]
    if not out:
        raise ValueError('empty stream')
    return bytes(out), pos - start


def _rle_one(p, raw, size=None):
    end = _RLE_END[p['end']]
    run_bit = 0x80 if p['run_high'] else 0
    lit_bit = 0x80 ^ run_bit

    def fields(bias, bit):
        """Usable count-field values for a block, avoiding the end marker."""
        return [c for c in range(0x80) if c + bias > 0 and (end is None or (c | bit) != end)]
    run_fields = fields(p['rb'], run_bit)
    lit_fields = fields(p['lb'], lit_bit)
    run_min, run_max = run_fields[0] + p['rb'], run_fields[-1] + p['rb']
    lit_min, lit_max = lit_fields[0] + p['lb'], lit_fields[-1] + p['lb']
    # tokens: [is_run, bytes]; a run's bytes are all the same
    tokens = []
    i = 0
    n = len(raw)
    if lit_min == 1 and run_min <= 2:
        # the usual case: the cheapest split into runs (2 bytes each) and literal blocks (1 + length)
        INF = 1 << 30
        run_end = [INF] * (n + 1)       # cheapest stream for raw[:i] that ends with a run (or is empty)
        lit_end = [INF] * (n + 1)       # ... that ends inside a literal block
        back = [0] * (n + 1)            # where the run that ends at i began
        opened = [False] * (n + 1)      # whether the literal block's byte i-1 opened a new block
        run_end[0] = 0
        k = 0
        for i in range(n):
            if k <= 1:                  # bytes equal to raw[i] from i on, capped
                k = 1
                while k < run_max and i + k < n and raw[i + k] == raw[i]:
                    k += 1
            else:
                k -= 1
                if k == run_max - 1 and i + k < n and raw[i + k] == raw[i]:
                    k += 1
            here = min(run_end[i], lit_end[i])
            if lit_end[i] + 1 <= run_end[i] + 2:
                lit_end[i + 1], opened[i + 1] = lit_end[i] + 1, False
            else:
                lit_end[i + 1], opened[i + 1] = run_end[i] + 2, True
            for r in range(max(run_min, 2), k + 1):
                if here + 2 < run_end[i + r]:
                    run_end[i + r] = here + 2
                    back[i + r] = i
        i = n
        in_lit = lit_end[n] < run_end[n]
        while i > 0:
            if in_lit:
                j = i
                while not opened[j]:
                    j -= 1
                j -= 1
                tokens.append([False, raw[j:i]])
                i, in_lit = j, False
            else:
                j = back[i]
                tokens.append([True, raw[j:i]])
                i, in_lit = j, lit_end[j] < run_end[j]
        tokens.reverse()
        i = n
    while i < n:
        k = 1
        while k < run_max and i + k < n and raw[i + k] == raw[i]:
            k += 1
        if k >= max(3, run_min):
            tokens.append([True, raw[i:i + k]])
            i += k
        elif tokens and not tokens[-1][0]:
            tokens[-1][1] += raw[i:i + 1]
            i += 1
        else:
            tokens.append([False, raw[i:i + 1]])
            i += 1
    # a literal block too short to store borrows bytes from the runs beside it
    k = 0
    while k < len(tokens):
        is_run, body = tokens[k]
        if is_run or len(body) >= lit_min:
            k += 1
            continue
        if k + 1 < len(tokens):
            nxt = tokens[k + 1]
            take = len(nxt[1]) if not nxt[0] or len(nxt[1]) - (lit_min - len(body)) < run_min else lit_min - len(body)
            tokens[k][1] = body + nxt[1][:take]
            nxt[1] = nxt[1][take:]
            if not nxt[1]:
                del tokens[k + 1]
        elif k > 0:
            prev = tokens[k - 1]
            take = len(prev[1]) if not prev[0] or len(prev[1]) - (lit_min - len(body)) < run_min else lit_min - len(body)
            tokens[k][1] = prev[1][len(prev[1]) - take:] + body
            prev[1] = prev[1][:len(prev[1]) - take]
            if not prev[1]:
                del tokens[k - 1]
                k -= 1
        else:
            raise ValueError('data this short cannot be stored in this format')
    if size is not None:
        # lengthen to exactly `size` bytes: splitting a literal block costs one byte, splitting a run two,
        # and a run stored as a literal block costs its length less one
        def cost():
            total = 0 if end is None else 1
            for is_run, body in tokens:
                total += 2 if is_run else len(body) + 1 + (len(body) - 1) // lit_max
            return total
        short = size - cost()
        k = 0
        while short > 0 and k < len(tokens):
            is_run, body = tokens[k]
            if not is_run and 2 * lit_min <= len(body) <= lit_max:
                tokens[k:k + 1] = [[False, body[:lit_min]], [False, body[lit_min:]]]
                short -= 1
                k += 1
            elif is_run and short >= 2 and len(body) >= 2 * run_min:
                tokens[k:k + 1] = [[True, body[:run_min]], [True, body[run_min:]]]
                short -= 2
                k += 1
            elif is_run and lit_min <= len(body) <= min(lit_max, short + 1):
                tokens[k][0] = False
                short -= len(body) - 1
            else:
                k += 1
        if short:
            raise ValueError(f'the data does not pack to exactly {size} bytes in this format')
    out = bytearray()
    for is_run, body in tokens:
        if is_run:
            out += bytes((run_bit | (len(body) - p['rb']), body[0]))
            continue
        q = 0
        while q < len(body):
            k = min(lit_max, len(body) - q)
            rest = len(body) - q - k
            if 0 < rest < lit_min:
                k -= lit_min - rest
            out.append(lit_bit | (k - p['lb']))
            out += body[q:q + k]
            q += k
    if end is not None:
        out.append(end)
    return bytes(out)


def rle_encode(p, raw, size=None):
    """`size`: make the stream exactly that long (one pass only), or raise ValueError."""
    raw = bytes(raw)
    planes = p['planes']
    if not raw or len(raw) % planes:
        raise ValueError('data must be whole groups of bytes')
    if size is not None:
        if planes != 1:
            raise ValueError('an exact size is only kept for one pass')
        return _rle_one(p, raw, size)
    return b''.join(_rle_one(p, raw[k::planes]) for k in range(planes))


def rle_grid():
    for flag in 'lh':
        for rb in (0, 1, 2, 3):
            for lb in (0, 1):
                for end in 'zfen':
                    for planes in (1, 2, 4):
                        if end == 'n' and planes > 1:
                            continue
                        yield f'rle~{flag}.r{rb}.l{lb}.{end}.p{planes}'


# ---- family table ---------------------------------------------------------------

FAMILIES = {
    'lz': (lz_parse, lz_decode, lz_encode, lambda p: p['end'] not in 'nu' or p['header'][-1] in 'ci'),
    'rle': (rle_parse, rle_decode, rle_encode, lambda p: p['end'] != 'n'),
}


def build(name: str):
    """(decode(data, start, limit), encode(raw), terminated) for a family member's name; KeyError if it is not one."""
    family = name.split('~', 1)[0]
    if '~' not in name or family not in FAMILIES:
        raise KeyError(name)
    parse, dec, enc, terminated = FAMILIES[family]
    p = parse(name)
    return (lambda data, start=0, limit=MAX_OUT: dec(p, data, start, limit)), (lambda raw, *more: enc(p, raw, *more)), terminated(p)


def features(name: str):
    """commands(stream) for a family member whose encoder takes what the original stream used, or None."""
    if name.startswith('lz~'):
        p = lz_parse(name)
        return lambda stream: lz_features(p, stream)
    return None
