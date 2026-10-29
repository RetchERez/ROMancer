"""Source-bound FFL2 map inspection and fixed-width edit descriptions.

Format facts: daid/FFL2-Disassembly, revision a5c17a90d87d102a9a45d287042c9a36ffd06f97.
This is an original bounded decoder, not an event compiler. Cartridge data is
read from the user's local source. Structural decoding is not native validation.
The caller establishes owned artifact ancestry and submits edits to the normal
integrity planner; this module never writes a game file.
"""
import hashlib
import base64
import io
from collections import Counter
from pathlib import Path

from .asset_schema import number

ROOT_SHA256 = '2d89231f9e264a024d634bcf7d00de5a66d8a45f6f4ca33e1fc1602a35b9840b'
REFERENCE = 'https://github.com/daid/FFL2-Disassembly/tree/a5c17a90d87d102a9a45d287042c9a36ffd06f97'
SIZE = 262144
EDITABLE_HEADER = 0x486b
OP_NAMES = ('End', 'Point', 'Anchor', 'Rectangle outline', 'Rectangle fill',
            'Circle', 'Line', 'Checker background', 'Anchor span fill',
            'Continue line', 'State condition')


def _check(cancelled):
    if cancelled():
        raise KeyboardInterrupt


def _u16(raw, offset):
    return int.from_bytes(raw[offset:offset+2], 'little')


def transition(word):
    """Interpret only proven field dispatch tags; other references stay opaque."""
    number(word, 0, 65535)
    tag, low = word >> 8, word & 255
    if tag == 6 and low == 255:
        return {'kind': 'saved-return', 'word': word}
    if tag in (5, 6):
        return {'kind': 'arrival', 'table': 'main',
                'id': (((tag & 1) ^ 1) << 8) | low, 'word': word}
    if tag == 14:
        return {'kind': 'arrival', 'table': 'special', 'id': low, 'word': word,
                'supported': low < 32}
    return {'kind': 'event', 'word': word, 'tag': tag}


def _graph(raw, cancelled):
    if len(raw) != SIZE:
        raise ValueError('FFL2 map revision requires a 262144-byte cartridge')
    arrivals = []
    for table, base, count in (('main', 0x1c000, 511), ('special', 0x1ef80, 32)):
        for index in range(count):
            _check(cancelled)
            p = base+4*index
            h = _u16(raw, p)
            if not 0x4800 <= h < 0x6f80:
                raise ValueError('arrival points outside supported room headers')
            arrivals.append({'id': index, 'table': table, 'offset': p, 'header': h,
                             'x': raw[p+2] & 63, 'y': raw[p+3] & 63,
                             'facing': raw[p+2] >> 6, 'flags': raw[p+3] & 192,
                             'raw': raw[p:p+4].hex()})
    pointers = sorted({a['header'] for a in arrivals})
    rooms = []
    for index, header in enumerate(pointers):
        _check(cancelled)
        p = 0x18000+header
        bound = 0x18000+(pointers[index+1] if index+1 < len(pointers) else 0x6f80)
        if p+5 > bound:
            raise ValueError('truncated room header')
        mp, tileset, flags = _u16(raw, p), raw[p+2], raw[p+3]
        if mp >= 0x8000 or tileset >= 64:
            raise ValueError('unsupported room map pointer or tileset')
        q = p+4+(2 if flags & 64 else 0)
        if q >= bound:
            raise ValueError('truncated room optional header')
        count = raw[q]; q += 1
        if count > 32 or q+count*2 > bound:
            raise ValueError('room interaction count exceeds bounded header')
        links = [{'index': i, 'offset': q+2*i, 'word': _u16(raw, q+2*i),
                  'transition': transition(_u16(raw, q+2*i))} for i in range(count)]
        q += count*2
        sprites, objects = [], []
        if flags & 128:
            for _ in range(6):
                if q >= bound:
                    raise ValueError('truncated room sprite pages')
                b = raw[q]; q += 1
                if b == 255:
                    break
                sprites.append(b)
            for _ in range(256):
                _check(cancelled)
                if q >= bound:
                    raise ValueError('unterminated room object list')
                if raw[q] == 255:
                    q += 1
                    break
                if q+6 > bound:
                    raise ValueError('truncated room object')
                a, b, x, y, lo, hi = raw[q:q+6]
                objects.append({'offset': q, 'index': len(objects), 'x': x & 63,
                                'y': y & 63, 'condition': a, 'range': b,
                                'x_flags': x & 192, 'y_flags': y & 192,
                                'event': lo | ((hi & 15) << 8), 'flags': hi & 240,
                                'raw': raw[q:q+6].hex(),
                                'state_status': 'unconditional definition' if a == 0 and b == 15 else 'conditional definition; live state unobserved',
                                'editable': header == EDITABLE_HEADER and a == 0 and b == 15})
                q += 6
            else:
                raise ValueError('room object definition budget exceeded')
        rooms.append({'header': header, 'label': f'Room {header:04X}', 'offset': p,
                      'optional_header':raw[p+4:p+6].hex() if flags & 64 else None,
                      'end': q, 'map_pointer': mp, 'map_start': 0x20000+mp,
                      'tileset': tileset, 'flags': flags, 'links': links,
                      'sprite_pages': sprites, 'objects': objects,
                      'arrival_count': sum(a['header'] == header for a in arrivals),
                      'editable': header == EDITABLE_HEADER})
    starts = sorted({r['map_start'] for r in rooms})
    ends = {p: starts[i+1] if i+1 < len(starts) else 0x28000 for i, p in enumerate(starts)}
    for room in rooms:
        room['map_bound'] = ends[room['map_start']]
        room['shared_headers'] = [r['header'] for r in rooms if r['map_start'] == room['map_start']]
    return rooms, arrivals


def _load(path, original_path, cancelled):
    _check(cancelled)
    if Path(original_path).stat().st_size != SIZE or Path(path).stat().st_size != SIZE:
        raise ValueError('FFL2 map revision requires a 262144-byte cartridge')
    original = Path(original_path).read_bytes()
    if len(original) != SIZE or hashlib.sha256(original).hexdigest() != ROOT_SHA256:
        raise ValueError('FFL2 map definition requires the exact supported USA revision')
    raw = Path(path).read_bytes()
    _check(cancelled)
    roots, root_arrivals = _graph(original, cancelled)
    rooms, arrivals = _graph(raw, cancelled)
    immutable = ('header', 'offset', 'end', 'map_pointer', 'tileset', 'flags', 'sprite_pages','optional_header')
    def structure(room):
        return {**{k:room[k] for k in immutable},
                'link_slots':[(link['index'],link['offset']) for link in room['links']],
                'object_slots':[(obj['index'],obj['offset']) for obj in room['objects']]}
    if [structure(room) for room in rooms] != [structure(room) for room in roots]:
        raise ValueError('room pointers, counts, flags or sprite pages differ from the source')
    if [a['header'] for a in arrivals] != [a['header'] for a in root_arrivals]:
        raise ValueError('arrival destination header pointers are protected')
    return raw, original, rooms, arrivals, roots


def _commands(raw, start, end, cancelled):
    number(start, 0, len(raw)); number(end, 0, len(raw))
    if not 0 <= start < end <= len(raw):
        raise ValueError('map stream range exceeds source')
    p, result = start, []
    for _ in range(4096):
        _check(cancelled)
        q = p
        if p >= end:
            raise ValueError('map stream is missing its terminator')
        a = raw[p]; p += 1; op = a >> 4
        if op > 10:
            raise ValueError('unsupported map opcode')
        command = {'offset': q, 'op': op, 'name': OP_NAMES[op]}
        if op:
            if p >= end:
                raise ValueError('truncated map coordinate')
            b = raw[p]; p += 1
            command.update(x=b & 63, y=((a & 15) << 2) | (b >> 6))
            if op == 10:
                command.update(state_index=a & 15, minimum=b >> 4, maximum=b & 15)
            if op in (1, 3, 4, 5, 6, 9):
                if p >= end:
                    raise ValueError('truncated map tile operand')
                t = raw[p]; p += 1
                command['tile'] = t & 63
                if op != 1 and t & 192:
                    if p >= end or raw[p] >= 64:
                        raise ValueError('unsupported or truncated alternate map tile')
                    command['second_tile'] = raw[p]; p += 1
        command.update(size=p-q, raw=raw[q:p].hex())
        result.append(command)
        if op == 0:
            return result, p
    raise ValueError('map command budget exceeded')


def encode_map_commands(commands):
    """Rebuild the stored grammar; preserve only explicitly reserved operand bits.

    No allocation or ROM mutation occurs. Opaque bytes after End are not emitted.
    Decoding and serializing a stream does not prove its gameplay semantics.
    """
    if type(commands) is not list or not 1 <= len(commands) <= 4096:
        raise ValueError('map command count exceeds its budget')
    output=bytearray();expected=None
    for index,command in enumerate(commands):
        if type(command) is not dict:raise ValueError('map command must be a record')
        op=number(command.get('op'),0,10);offset=number(command.get('offset'),0,SIZE-1)
        text=command.get('raw')
        if type(text) is not str or len(text) not in (2,4,6,8) or any(c not in '0123456789abcdef' for c in text):raise ValueError('invalid stored map command bytes')
        original=bytes.fromhex(text)
        if original[0]>>4!=op or number(command.get('size'),1,4)!=len(original):raise ValueError('map command layout differs')
        if expected is not None and offset!=expected:raise ValueError('map command offsets have gaps or overlap')
        if op==0:
            if len(original)!=1 or index!=len(commands)-1:raise ValueError('map End must be the last single-byte record')
            data=bytes([original[0]&15])
        elif op==10:
            data=bytes([0xa0|number(command.get('state_index'),0,15),
                        number(command.get('minimum'),0,15)<<4|number(command.get('maximum'),0,15)])
        else:
            x=number(command.get('x'),0,63);y=number(command.get('y'),0,63)
            data=bytes([(op<<4)|(y>>2),((y&3)<<6)|x])
            if op in (1,3,4,5,6,9):
                if len(original)<3:raise ValueError('map tile operand is missing')
                flags=original[2]&192;data+=bytes([flags|number(command.get('tile'),0,63)])
                if op!=1 and flags:data+=bytes([number(command.get('second_tile'),0,63)])
                elif 'second_tile' in command:raise ValueError('map command has no alternate tile operand')
        if len(data)!=len(original):raise ValueError('map command serialization changed its width')
        output+=data;expected=offset+len(data)
    if commands[-1]['op']!=0:raise ValueError('map stream is missing End')
    return bytes(output)


def check_map_storage(raw,start,end,*,cancelled=lambda:False):
    """Independent no-op encoding check within an existing catalog-bounded range."""
    if type(raw) not in (bytes,bytearray) or len(raw)>SIZE:raise ValueError('map source exceeds the revision storage budget')
    commands,used_end=_commands(raw,start,end,cancelled)
    encoded=encode_map_commands(commands);_check(cancelled)
    original=bytes(raw[start:used_end])
    if encoded!=original:raise ValueError('map command storage failed its lossless roundtrip')
    return {'status':'byte_identical','codec':'ffl2-map-command-stream-v1','offset':start,
            'used_bytes':len(encoded),'command_count':len(commands),'range_bound_bytes':end-start,
            'protected_trailing_bytes':end-used_end,'stored_sha256':hashlib.sha256(original).hexdigest(),
            'encoded_sha256':hashlib.sha256(encoded).hexdigest(),'native_verified':False,'write_authorized':False}


def decode_map(raw, start, end, *, state=None, cancelled=lambda: False):
    """Decode terrain, original command provenance, and exact owned byte extent.

    State is an explicit mapping of state-nibble index to captured/selected value.
    Circle rendering uses the game's small-radius table and signed 16-bit
    recurrence for larger/zero radii. Opcode8 is fixed-column span fill,
    not a general connected-region flood fill.
    """
    if state is not None:
        if type(state) is not dict or len(state) > 32:
            raise ValueError('state must map nibble indexes to values 0..15')
        normalized = {}
        for key, value in state.items():
            if type(key) is str and key in {str(i) for i in range(32)}:
                key = int(key)
            if type(key) is not int or not 0 <= key < 32 or type(value) is not int or not 0 <= value < 16 or key in normalized:
                raise ValueError('state must map nibble indexes to values 0..15')
            normalized[key] = value
        state = normalized
    commands, owned_end = _commands(raw, start, end, cancelled)
    cells, provenance = [0]*4096, [None]*4096
    anchor, previous = (0, 0), (0, 0)
    executed = []
    def put(x, y, tile, offset):
        if not (0 <= x < 64 and 0 <= y < 64 and 0 <= tile < 64):
            raise ValueError('map drawing exceeds supported bounds')
        cells[y*64+x] = tile; provenance[y*64+x] = offset
    for c in commands:
        _check(cancelled)
        op, offset = c['op'], c['offset']
        executed.append(c)
        if op == 0:
            break
        x, y = c['x'], c['y']
        t = c.get('tile', 0); second = c.get('second_tile', t)
        if op == 10:
            index = c['state_index']
            if state is None or index not in state:
                raise ValueError(f'conditional map requires explicit state nibble {index}')
            if not c['minimum'] <= state[index] <= c['maximum']:
                break
        elif op == 1:
            put(x, y, t, offset)
        elif op == 2:
            anchor = (x, y)
        elif op == 7:
            for yy in range(64):
                _check(cancelled)
                for xx in range(64):
                    put(xx, yy, x if (xx+yy) % 2 == 0 else y, offset)
        elif op == 8:
            sx, sy = anchor; source = cells[sy*64+sx]
            for direction, first in ((1, sy), (-1, sy-1)):
                yy = first
                while 0 <= yy < 64 and cells[yy*64+sx] == source:
                    _check(cancelled)
                    for dx, initial in ((1, sx), (-1, sx-1)):
                        xx = initial
                        while 0 <= xx < 64 and cells[yy*64+xx] == source:
                            put(xx, yy, x, offset); xx += dx
                    yy += direction
        elif op == 5:
            sx, sy = anchor; radius = abs(x-sx)+abs(y-sy)
            if not 1 <= radius < 8:
                # Original fixed-point rotation, including its integer rounding,
                # word wrapping and zero-divisor quotient. The sampled routine
                # draws after updating both vector components, not before.
                vx=((x-sx)&255)<<8;vy=((y-sy)&255)<<8
                def quotient(value):
                    negative=bool(value&32768);magnitude=(-value)&65535 if negative else value
                    result=magnitude//radius if radius else 65535
                    return (-result if negative else result)&65535
                for _ in range(radius*8+1):
                    _check(cancelled)
                    vx=(vx+quotient(vy))&65535;vy=(vy-quotient(vx))&65535
                    xx=(sx+(vx>>8))&255;yy=(sy+(vy>>8))&255
                    if xx<64 and yy<64:put(xx,yy,t,offset)
                continue
            table = 0x2670+2*(radius-1)
            if table+2 > len(raw):
                raise ValueError('circle table exceeds source')
            q = _u16(raw, table)
            for _ in range(64):
                if q >= len(raw):
                    raise ValueError('circle data exceeds source')
                if raw[q] == 255:
                    break
                if q+2 > len(raw):
                    raise ValueError('truncated circle data')
                u, v = raw[q:q+2]; q += 2
                for xx, yy in ((sx+u, sy+v), (sx+v, sy-u), (sx-u, sy-v), (sx-v, sy+u)):
                    if 0 <= xx < 64 and 0 <= yy < 64:
                        put(xx, yy, t, offset)
            else:
                raise ValueError('circle data budget exceeded')
        elif op in (6, 9):
            sx, sy = previous if op == 9 else anchor
            previous = (x, y)
            dx, dy = abs(x-sx), abs(y-sy)
            stepx, stepy = 1 if x >= sx else -1, 1 if y >= sy else -1
            major, minor = max(dx, dy), min(dx, dy)
            accumulator = max(major//2, 1)
            for step in range(128):
                put(sx, sy, t if step % 2 == 0 else second, offset)
                if (sx, sy) == (x, y):
                    break
                accumulator += minor
                if accumulator > major:
                    sx += stepx; sy += stepy; accumulator -= major
                elif dx >= dy:
                    sx += stepx
                else:
                    sy += stepy
            else:
                raise ValueError('line drawing budget exceeded')
        else:
            sx, sy = anchor
            left, right = sorted((sx, x)); top, bottom = sorted((sy, y))
            if op == 4:
                for yy in range(top, bottom+1):
                    _check(cancelled)
                    for xx in range(left, right+1):
                        put(xx, yy, t if (xx-left+yy-top) % 2 == 0 else second, offset)
            elif op == 3:
                points = ([(xx, top) for xx in range(left, right+1)]
                          + [(right, yy) for yy in range(top+1, bottom+1)]
                          + [(xx, bottom) for xx in range(right-1, left-1, -1)]
                          + [(left, yy) for yy in range(bottom-1, top, -1)])
                for i, (xx, yy) in enumerate(points):
                    put(xx, yy, t if i % 2 == 0 else second, offset)
    return {'cells': cells, 'commands': commands, 'executed_offsets': [c['offset'] for c in executed],
            'end': owned_end, 'provenance': provenance, 'native_verified': False}


def _markers(cells, flags):
    marked, markers = list(cells), []
    count = flags & 15
    if count:
        for i, t in enumerate(cells):
            if 3 <= (t & 31) < 3+count:
                if len(markers) >= 32:
                    raise ValueError('generated map marker count exceeds runtime backing table')
                index = len(markers)
                markers.append({'index': index, 'x': i % 64, 'y': i//64, 'tile': t})
                marked[i] = (t & 32) | 64 | index
    return marked, markers


def _tiles(raw, tileset):
    result = []
    for tile in range(64):
        p = 0x8000+64*raw[0x1f800+32*tileset+(tile & 31)]
        pixels = [0]*256
        for q in range(4):
            for y in range(8):
                lo, hi = raw[p+q*16+y*2:p+q*16+y*2+2]
                for x in range(8):
                    pixels[((q//2)*8+y)*16+(q % 2)*8+x] = ((lo >> (7-x)) & 1) | (((hi >> (7-x)) & 1) << 1)
        result.append(pixels)
    return result


def _room(rooms, header):
    number(header, 0x4800, 0x6f7f)
    result = next((r for r in rooms if r['header'] == header), None)
    if result is None:
        raise ValueError('room header is absent from the actual arrival catalog')
    return result


def catalog(path, original_path, *, offset=0, limit=24, query='', cancelled=lambda: False):
    number(offset, 0, 10000); number(limit, 1, 256)
    if type(query) is not str or len(query) > 128:
        raise ValueError('invalid bounded room search')
    raw, _, rooms, arrivals, _ = _load(path, original_path, cancelled)
    filtered = [r for r in rooms if query.lower() in (r['label']+f" map {r['map_pointer']:04X}").lower()]
    summaries = [{k: r[k] for k in ('header', 'label', 'map_pointer', 'tileset', 'flags',
                                   'arrival_count', 'shared_headers', 'editable')}
                 | {'object_count': len(r['objects']), 'link_count': len(r['links'])}
                 for r in filtered[offset:offset+limit]]
    for summary, room in zip(summaries, filtered[offset:offset+limit]):
        _check(cancelled)
        try:
            decoded = decode_map(raw, room['map_start'], room['map_bound'], cancelled=cancelled)
            summary['thumbnail'] = _thumbnail(raw, room, decoded['cells'], cancelled)
        except ValueError as error:
            summary['thumbnail'] = {'status': 'unavailable', 'reason': str(error)}
    return {'rooms': summaries, 'total': len(filtered), 'offset': offset, 'limit': limit,
            'counts': {'rooms': len(rooms), 'maps': len({r['map_pointer'] for r in rooms}),
                       'arrivals': len(arrivals), 'objects': sum(len(r['objects']) for r in rooms)},
            'reference': REFERENCE, 'native_verified': False}


def _thumbnail(raw, room, cells, cancelled):
    from PIL import Image
    tiles = _tiles(raw, room['tileset'])
    # Noncertified rooms use explicit grayscale color-index visualization.
    # This is an inspection aid; no unobserved hardware palette is asserted.
    shades = (85, 255, 170, 0) if room['header'] == EDITABLE_HEADER else (255, 170, 85, 0)
    pixels = []
    for y in range(96):
        _check(cancelled)
        sy = y*1024//96
        for x in range(96):
            sx = x*1024//96
            tile = cells[(sy//16)*64+sx//16]
            pixels.append(shades[tiles[tile][(sy % 16)*16+sx % 16]])
    image = Image.new('L', (96, 96)); image.putdata(pixels)
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    return {'status': 'available', 'width': 96, 'height': 96,
            'data_url': 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii'),
            'palette_status': 'opening-atlas palette' if room['header'] == EDITABLE_HEADER else 'color-index grayscale; game palette unverified'}


def inspect_room(path, original_path, header, *, state=None, cancelled=lambda: False):
    raw, _, rooms, arrivals, _ = _load(path, original_path, cancelled)
    room = _room(rooms, header)
    for link in room['links']:
        ref = link['transition']
        link['destination'] = next((a for a in arrivals if ref['kind'] == 'arrival'
                                    and a['table'] == ref['table'] and a['id'] == ref['id']), None)
    result = {'room': room, 'objects': room['objects'], 'links': room['links'],
              'arrivals': [a for a in arrivals if a['header'] == header], 'reference': REFERENCE}
    try:result['storage']=check_map_storage(raw,room['map_start'],room['map_bound'],cancelled=cancelled)
    except ValueError as error:result['storage']={'status':'unsupported','reason':str(error),'write_authorized':False,'native_verified':False}
    try:
        decoded = decode_map(raw, room['map_start'], room['map_bound'], state=state, cancelled=cancelled)
        counts = Counter(decoded['provenance'])
        for command in decoded['commands']:
            command['final_cells'] = counts[command['offset']]
            command['editable'] = header == EDITABLE_HEADER and command['op'] in (1, 2, 3, 4, 5, 6, 9)
        marked, markers = _markers(decoded['cells'], room['flags'])
        behavior = list(raw[0x1f000+32*room['tileset']:0x1f020+32*room['tileset']])
        result['map'] = {**decoded, 'status': 'decoded', 'size': [64, 64], 'tile_size': 16,
                         'tiles': _tiles(raw, room['tileset']), 'behavior': behavior,
                         'marked_cells': marked, 'marker_cells': markers,
                         'palette': [[85]*3, [255]*3, [170]*3, [0]*3] if header == EDITABLE_HEADER else None,
                         'palette_status': 'opening-atlas native palette' if header == EDITABLE_HEADER else 'unverified palette; tile indexes decoded'}
    except ValueError as error:
        result['map'] = {'status': 'unsupported', 'reason': str(error), 'native_verified': False}
    return result


def _fields(change, allowed, required):
    if type(change) is not dict or set(change)-set(allowed.split()) or not set(required.split()) <= set(change):
        raise ValueError('missing or unknown fixed-width map edit fields')


def _coord(change, key, current):
    return number(change[key], 0, 63) if key in change else current


def plan_edits(path, original_path, header, changes, *, cancelled=lambda: False):
    """Return exact byte edits; no mutation. Every resulting build needs playtest.

    Initial terrain edits preserve all behavior values, tile region bits and
    trigger marker bindings. Conditional/story NPCs and saved-return links stay
    locked. Arrival coordinates may change only within the initial atlas.
    """
    if type(changes) is not list or not 1 <= len(changes) <= 64:
        raise ValueError('choose 1 to 64 bounded map edits')
    raw, original, rooms, arrivals, roots = _load(path, original_path, cancelled)
    room, root = _room(rooms, header), _room(roots, header)
    if header != EDITABLE_HEADER:
        raise ValueError('writable primitive scope is currently room 486B')
    for p, length in ((0x1f000+room['tileset']*32, 32),
                      (0x1f800+room['tileset']*32, 32), (0x2670, 0x65),
                      (0x1bb9, 0x26d5-0x1bb9), (0x338a, 0x344b-0x338a)):
        if raw[p:p+length] != original[p:p+length]:
            raise ValueError('map engine, collision or graphics lookup guard differs from source')
    for a, b in zip(room['objects'], root['objects']):
        if (a['condition'], a['range'], a['event'], a['flags'], a['x_flags'], a['y_flags']) != (
                b['condition'], b['range'], b['event'], b['flags'], b['x_flags'], b['y_flags']):
            raise ValueError('NPC conditions, references and packed flags are protected')
    before = decode_map(raw, room['map_start'], room['map_bound'], cancelled=cancelled)
    check_map_storage(raw,room['map_start'],room['map_bound'],cancelled=cancelled)
    baseline = decode_map(original, root['map_start'], root['map_bound'], cancelled=cancelled)
    shared_contexts=[r for r in rooms if r['map_start']==room['map_start']]
    for context in shared_contexts:
        for p in (0x1f000+context['tileset']*32,0x1f800+context['tileset']*32):
            if raw[p:p+32]!=original[p:p+32]:
                raise ValueError('shared map collision or graphics lookup differs from original')
    if [(c['offset'], c['op'], c['size']) for c in before['commands']] != [(c['offset'], c['op'], c['size']) for c in baseline['commands']]:
        raise ValueError('map command structure differs from original')
    for a, b in zip(before['commands'], baseline['commands']):
        if a['op'] not in (1, 2, 3, 4, 5, 6, 9) and a['raw'] != b['raw']:
            raise ValueError('unsupported map command operands are protected')
        if 'tile' in a and ((bytes.fromhex(a['raw'])[2] & 192) != (bytes.fromhex(b['raw'])[2] & 192)
                            or a.get('second_tile') != b.get('second_tile')):
            raise ValueError('alternate tile flags and operands are protected')
    for a, b in zip(room['links'], root['links']):
        if b['transition']['kind'] != 'arrival' or b['transition'].get('table') != 'main':
            if a['word'] != b['word']:
                raise ValueError('original scripts, special transitions and saved-return links are protected')
    work = bytearray(raw); edits, preview, spans = [], [], set()
    def edit(p, data, label):
        if any(i in spans for i in range(p, p+len(data))):
            raise ValueError('map edits overlap; combine changes to each record')
        spans.update(range(p, p+len(data)))
        old = raw[p:p+len(data)]
        if old != data:
            edits.append({'offset': p, 'before': old.hex(), 'after': data.hex()})
            preview.append({'label': label, 'offset': p, 'before': old.hex(), 'after': data.hex()})
            work[p:p+len(data)] = data
    for change in changes:
        _check(cancelled)
        if type(change) is not dict:
            raise ValueError('map edits must be structured records')
        kind = change.get('kind')
        if kind == 'command':
            _fields(change, 'kind offset x y tile', 'kind offset')
            number(change['offset'], 0, SIZE-1)
            c = next((c for c in before['commands'] if c['offset'] == change['offset']), None)
            if c is None or c['op'] not in (1, 2, 3, 4, 5, 6, 9):
                raise ValueError('select an existing editable point, anchor, rectangle, circle or line')
            if 'tile' in change and c['op'] == 2:
                raise ValueError('anchor commands have no tile operand')
            x, y = _coord(change, 'x', c['x']), _coord(change, 'y', c['y'])
            data = bytearray.fromhex(c['raw'])
            data[0] = (data[0] & 240) | (y >> 2)
            data[1] = ((y & 3) << 6) | x
            if 'tile' in change:
                tile = number(change['tile'], 0, 63)
                if (tile & 32) != (c['tile'] & 32):
                    raise ValueError('map region tile bit is protected')
                data[2] = (data[2] & 192) | tile
            edit(c['offset'], bytes(data), c['name'])
        elif kind == 'npc':
            _fields(change, 'kind offset x y', 'kind offset')
            npc = next((n for n in room['objects'] if n['offset'] == change['offset']), None)
            if npc is None or not npc['editable']:
                raise ValueError('select an unconditional existing NPC; story conditions are protected')
            data = bytearray.fromhex(npc['raw'])
            data[2] = npc['x_flags'] | _coord(change, 'x', npc['x'])
            data[3] = npc['y_flags'] | _coord(change, 'y', npc['y'])
            edit(npc['offset'], bytes(data), f"NPC {npc['index']+1} position")
        elif kind == 'arrival':
            _fields(change, 'kind table id x y', 'kind table id')
            number(change['id'], 0, 510)
            a = next((a for a in arrivals if a['table'] == change['table'] and a['id'] == change['id']), None)
            if a is None or a['table'] != 'main' or a['header'] != header:
                raise ValueError('select a main-table arrival into room 486B')
            data = bytearray.fromhex(a['raw'])
            data[2] = (data[2] & 192) | _coord(change, 'x', a['x'])
            data[3] = (data[3] & 192) | _coord(change, 'y', a['y'])
            edit(a['offset'], bytes(data), f"Arrival {a['id']:03X} position")
        elif kind == 'link':
            _fields(change, 'kind index arrival_id', 'kind index arrival_id')
            number(change['index'], 0, len(room['links'])-1)
            number(change['arrival_id'], 0, 510)
            link = room['links'][change['index']]
            if link['transition']['kind'] != 'arrival' or link['transition']['table'] != 'main':
                raise ValueError('event scripts, special transitions and saved-return links are protected')
            a = next(a for a in arrivals if a['table'] == 'main' and a['id'] == change['arrival_id'])
            if a['header'] != header:
                raise ValueError('new link destination must remain in the initial atlas')
            word = ((5 if a['id'] < 256 else 6) << 8) | (a['id'] & 255)
            edit(link['offset'], word.to_bytes(2, 'little'), f"Interaction {link['index']} destination")
        else:
            raise ValueError('unsupported map edit kind')
    after = decode_map(work, room['map_start'], room['map_bound'], cancelled=cancelled)
    check_map_storage(work,room['map_start'],room['map_bound'],cancelled=cancelled)
    behavior = raw[0x1f000+32*room['tileset']:0x1f020+32*room['tileset']]
    if any(behavior[a & 31] != behavior[b & 31] or (a & 32) != (b & 32)
           for a, b in zip(before['cells'], baseline['cells'])):
        raise ValueError('current map collision differs from the verified original context')
    if any(behavior[a & 31] != behavior[b & 31] or (a & 32) != (b & 32)
           for a, b in zip(before['cells'], after['cells'])):
        raise ValueError('initial primitive editing must preserve collision behavior and region bits')
    _, markers = _markers(before['cells'], room['flags'])
    _, new_markers = _markers(after['cells'], room['flags'])
    _, root_markers = _markers(baseline['cells'], root['flags'])
    if markers != root_markers:
        raise ValueError('current trigger marker ordering differs from original')
    if markers != new_markers:
        raise ValueError('terrain edit changes generated interaction marker ordering')
    def triggers(cells):
        return [(i, t, behavior[t & 31]) for i, t in enumerate(cells) if behavior[t & 31] & 192 == 192]
    if triggers(before['cells']) != triggers(baseline['cells']):
        raise ValueError('current trigger cells differ from the original context')
    if triggers(before['cells']) != triggers(after['cells']):
        raise ValueError('terrain edit changes an existing trigger cell')
    # Each header can use a different tileset/behavior table for the same stream.
    # Preserving only the selected room would silently change another room's
    # walkability, triggers or generated instance numbering.
    for context in shared_contexts:
        table=raw[0x1f000+context['tileset']*32:0x1f020+context['tileset']*32]
        for candidate in (before['cells'],after['cells']):
            if any(table[a&31]!=table[b&31] or (a&32)!=(b&32)
                   for a,b in zip(baseline['cells'],candidate)):
                raise ValueError('terrain edit changes collision in a shared map header')
            if _markers(candidate,context['flags'])[1]!=_markers(baseline['cells'],context['flags'])[1]:
                raise ValueError('terrain edit changes shared map interaction marker ordering')
            if [(i,t) for i,t in enumerate(candidate) if table[t&31]&192==192] != [
                    (i,t) for i,t in enumerate(baseline['cells']) if table[t&31]&192==192]:
                raise ValueError('terrain edit changes a shared map trigger cell')
    # Proven walkable floor is behavior01. Other movement modes stay opaque.
    for change in changes:
        if change['kind'] in ('npc', 'arrival'):
            if change['kind'] == 'npc':
                npc = next(n for n in room['objects'] if n['offset'] == change['offset'])
                x, y = _coord(change, 'x', npc['x']), _coord(change, 'y', npc['y'])
            else:
                a = next(a for a in arrivals if a['table'] == change['table'] and a['id'] == change['id'])
                x, y = _coord(change, 'x', a['x']), _coord(change, 'y', a['y'])
            if behavior[after['cells'][y*64+x] & 31] != 1:
                raise ValueError('position must be on proven walkable behavior01 terrain')
    if not edits:
        raise ValueError('no map changes to build')
    preview_rooms,preview_arrivals=_graph(work,cancelled)
    return {'edits': sorted(edits, key=lambda e: e['offset']), 'preview': preview,
            'preview_map':{'cells':after['cells'],'provenance':after['provenance']},
            'preview_objects':_room(preview_rooms,header)['objects'],
            'preview_arrivals':[a for a in preview_arrivals if a['header']==header],
            'header': header, 'shared_headers': room['shared_headers'],
            'changed_cells': sum(a != b for a, b in zip(before['cells'], after['cells'])),
            'requires_native_playtest': True, 'native_verified': False, 'reference': REFERENCE}
