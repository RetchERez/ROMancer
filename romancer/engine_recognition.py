"""Read-only, bounded recognition of shared engine structures.

This is original role-based THUMB analysis, not an engine byte signature. It
recognizes one supported m4a-compatible song-selection calling convention and
cross-checks its referenced records. It neither executes code nor authorizes
edits. A negative result says nothing about other drivers or compiler variants.
"""
import hashlib
from bisect import bisect_right
from pathlib import Path
import re
import struct


MAX_ROM_BYTES = 32 * 1024 * 1024
MAX_FUNCTIONS = 65536
MAX_INSTRUCTIONS = 48
MAX_ANCHORS = 64
MAX_FINDINGS = 8
MAX_SONG_ENTRIES = 4096
MAX_TRACK_POINTERS = 65536
MAX_PLAYERS = 256
REFERENCE = ('https://github.com/vgmtrans/vgmtrans/blob/'
             '162d94c931e222bd3944a6652b8a920bc87e54c3/'
             'src/main/formats/MP2k/MP2kScanner.cpp')
STRUCTURE_REFERENCE = ('https://github.com/pret/pokeemerald/blob/'
                       '731ad5bfd6e6f265508d0efcca0ba42f9dcf5881/'
                       'include/gba/m4a_internal.h')


class _BudgetExceeded(Exception):
    pass


def _check(cancelled):
    if cancelled():
        raise KeyboardInterrupt('engine recognition cancelled')


def _u16(raw, offset):
    return struct.unpack_from('<H', raw, offset)[0]


def _u32(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0]


def _rom_pointer(value, size, length, alignment=1):
    # Check the bus region BEFORE converting its three ROM wait-state mirrors.
    if not 0x08000000 <= value < 0x0e000000:
        raise ValueError('not a GBA cartridge ROM pointer')
    offset = value & 0x01ffffff
    if offset % alignment or offset + length > size:
        raise ValueError('misaligned or out-of-range ROM pointer')
    return offset


def _ram_pointer(value):
    return (value % 4 == 0 and
            (0x02000000 <= value < 0x02040000 or
             0x03000000 <= value < 0x03008000))


def _shift(tag, amount, right=False):
    if tag == ('input',) and not right and amount == 16:
        return ('upper16',)
    if tag == ('upper16',) and right and amount in (13, 16):
        return ('song_index', 1 << (16-amount))
    if tag and tag[0] in ('song_index', 'player_index') and not right:
        factor = tag[-1] << amount
        if factor <= (8 if tag[0] == 'song_index' else 12):
            return tag[:-1] + (factor,)
    return None


def _add(left, right):
    for base, index in ((left, right), (right, left)):
        if not base or not index:
            continue
        if base[0] == 'rom' and index == ('song_index', 8):
            return ('entry', base[1])
        if base[0] == 'rom' and index[0] == 'player_index' and index[2] == 12:
            return ('player_entry', base[1], index[1])
    if (left and right and left[0] == right[0] == 'player_index' and
            left[1] == right[1] and left[2]+right[2] <= 12):
        return ('player_index', left[1], left[2]+right[2])
    return None


def _anchor(raw, start, cancelled):
    """Prove indexed song/header + indexed player/info flow into one BL.

    Only a small straight-line THUMB subset is modeled. Unknown instructions,
    branches, calls before the proof, and loops stop analysis; no control flow
    or indirect ROM pointer is recursively followed.
    """
    registers = [None]*16
    registers[0] = ('input',)
    literals = []
    for step in range(MAX_INSTRUCTIONS):
        _check(cancelled)
        pc = start+2+step*2
        if pc+2 > len(raw):
            return None
        word = _u16(raw, pc)
        if word & 0xf800 in (0x0000, 0x0800):
            source, destination = (word >> 3) & 7, word & 7
            amount = (word >> 6) & 31
            if word & 0xf800 == 0x0800 and amount == 0:
                amount = 32
            registers[destination] = _shift(registers[source], amount,
                                           word & 0xf800 == 0x0800)
        elif word & 0xf800 == 0x4800:
            literal = ((pc+4) & ~3)+(word & 255)*4
            if literal+4 > len(raw):
                return None
            try:
                value = _rom_pointer(_u32(raw, literal), len(raw), 4, 4)
            except ValueError:
                return None
            registers[(word >> 8) & 7] = ('rom', value)
            literals.append(literal)
        elif word & 0xfe00 == 0x1800:
            registers[word & 7] = _add(registers[(word >> 3) & 7],
                                       registers[(word >> 6) & 7])
        elif word & 0xfe00 == 0x1c00:
            # ADD immediate zero is a low-register copy. Other arithmetic
            # loses the role; it must not silently retain a stale register.
            registers[word & 7] = (registers[(word >> 3) & 7]
                                   if (word >> 6) & 7 == 0 else None)
        elif word & 0xff00 == 0x4600:
            destination = (word & 7) | ((word >> 4) & 8)
            if destination == 15:
                return None
            registers[destination] = registers[(word >> 3) & 15]
        elif word & 0xf800 == 0x8800:
            base = registers[(word >> 3) & 7]
            offset = ((word >> 6) & 31)*2
            registers[word & 7] = (('player_index', base[1], 1)
                                   if base and base[0] == 'entry' and offset == 4
                                   else None)
        elif word & 0xf800 == 0x6800:
            base = registers[(word >> 3) & 7]
            offset = ((word >> 6) & 31)*4
            value = None
            if base and offset == 0:
                if base[0] == 'entry':
                    value = ('header', base[1])
                elif base[0] == 'player_entry':
                    value = ('info', base[1], base[2])
            registers[word & 7] = value
        elif word & 0xf800 == 0xf000:
            if pc+4 > len(raw) or _u16(raw, pc+2) & 0xf800 != 0xf800:
                return None
            high = word & 0x7ff
            if high & 0x400:
                high -= 0x800
            target = pc+4+(high << 12)+((_u16(raw, pc+2) & 0x7ff) << 1)
            info, header = registers[0], registers[1]
            if (not info or not header or info[0] != 'info' or
                    header != ('header', info[2]) or
                    not 0 <= target < len(raw)-1 or start <= target < pc+4):
                return None
            # Literal pools must not have been interpreted as instructions.
            if any(start <= literal < pc+4 for literal in literals):
                return None
            return {'offset': start, 'length': pc+4-start,
                    'player_table_offset': info[1],
                    'song_table_offset': info[2], 'call_target': target,
                    'literal_offsets': sorted(set(literals))}
        else:
            return None
    return None


def _track_prefix(raw, offset):
    """Return supported initial command width, never interpret music loops."""
    command = raw[offset]
    if 0x80 <= command <= 0xb1:
        return 1  # Wait or immediate end: no pointer operand.
    # These initial state setters have one byte of data. Unsupported initial
    # control-flow/extended commands are deliberately excluded, not guessed.
    if command in (0xba, 0xbb, 0xbc, 0xbd, 0xbe, 0xbf, 0xc0, 0xc1,
                   0xc2, 0xc3, 0xc4, 0xc5, 0xc8):
        if offset+2 > len(raw):
            return 0
        return 2 if command == 0xbc or raw[offset+1] < 0x80 else 0
    return 0


def _tables(raw, anchor, cancelled):
    table, players = anchor['song_table_offset'], anchor['player_table_offset']
    if table == players:
        raise ValueError('song and player tables overlap')
    headers, player_records, tracks, tones = {}, {}, [], set()
    count = empty = nulls = nonempty = over_capacity = 0
    first_header = None
    # There is no universal m4a song-count field or null terminator. This first
    # implementation requires the run to meet its earliest referenced header;
    # it refuses to turn a first bad pointer into an invented complete count.
    for index in range(MAX_SONG_ENTRIES+1):
        _check(cancelled)
        entry = table+index*8
        if first_header is not None and entry == first_header and count:
            break
        if index == MAX_SONG_ENTRIES:
            raise _BudgetExceeded('song entry budget exhausted')
        if entry+8 > (first_header if first_header is not None else len(raw)):
            raise ValueError('no unambiguous supported song-table boundary')
        pointer = _u32(raw, entry)
        if pointer == 0:
            nulls += 1
            count += 1
            continue
        header = _rom_pointer(pointer, len(raw), 8, 4)
        if header >= table:
            first_header = min(first_header, header) if first_header is not None else header
        if table <= header < entry+8:
            raise ValueError('header overlaps table')
        player = _u16(raw, entry+4)
        if player >= MAX_PLAYERS:
            raise ValueError('unsupported player index')
        player_offset = players+player*12
        if player_offset+12 > len(raw) or player_offset < table < player_offset+12:
            raise ValueError('player record out of bounds or overlaps table')
        if player not in player_records:
            info, workspace = _u32(raw, player_offset), _u32(raw, player_offset+4)
            capacity = raw[player_offset+8]
            if not _ram_pointer(info) or not _ram_pointer(workspace) or not 1 <= capacity <= 16:
                raise ValueError('unsupported player RAM pointers/capacity')
            player_records[player] = (player_offset, capacity)
        if header not in headers:
            track_count, block_count = raw[header:header+2]
            if track_count > 16 or block_count != 0 or header+8+track_count*4 > len(raw):
                raise ValueError('unsupported or truncated song header')
            header_tracks = []
            if track_count:
                tones.add(_rom_pointer(_u32(raw, header+4), len(raw), 12, 4))
                for track in range(track_count):
                    _check(cancelled)
                    position = _rom_pointer(_u32(raw, header+8+track*4), len(raw), 1)
                    if not _track_prefix(raw, position):
                        raise ValueError('unsupported or malformed initial track command')
                    header_tracks.append(position)
            headers[header] = (track_count, header_tracks)
        track_count, header_tracks = headers[header]
        tracks.extend(header_tracks)
        if len(tracks) > MAX_TRACK_POINTERS:
            raise _BudgetExceeded('track-pointer budget exhausted')
        nonempty += bool(track_count)
        empty += not bool(track_count)
        over_capacity += track_count > player_records[player][1]
        count += 1
    if nonempty < 1 or count < 4:
        raise ValueError('insufficient independent song-table structure')
    table_end = table+count*8
    ranges = [(table, table_end)]
    ranges.extend((h, h+8+record[0]*4) for h, record in headers.items())
    ranges.extend((record[0], record[0]+12) for record in player_records.values())
    # Validate cross-record ownership after discovering every header, not just
    # the current header. No track may masquerade as table/header/player data.
    merged = []
    for start, end in sorted(ranges):
        if merged and start < merged[-1][1]:
            raise ValueError('referenced structures overlap')
        if merged and start == merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    starts = [start for start, _ in merged]
    spans = [(track, _track_prefix(raw, track)) for track in set(tracks)]
    spans.extend((tone, 12) for tone in tones)
    for position, length in spans:
        _check(cancelled)
        interval = bisect_right(starts, position+length-1)-1
        if interval >= 0 and position < merged[interval][1]:
            raise ValueError('track/voicegroup aliases structural storage')
    for start, end in ranges[1:]:
        if start < table_end and table < end:
            raise ValueError('song table overlaps another referenced structure')
    return {
        'song_table_offset': table, 'player_table_offset': players,
        'song_entries': count, 'nonempty_songs': nonempty,
        'empty_songs': empty, 'null_entries': nulls,
        'distinct_song_headers': len(headers), 'track_pointers': len(tracks),
        'distinct_track_pointers': len(set(tracks)), 'voicegroup_offsets': sorted(tones),
        'player_indices': sorted(player_records),
        'player_record_count': len(player_records),
        'player_table_span': max(p[0]+12 for p in player_records.values())-players,
        'over_capacity_song_declarations': over_capacity,
        'table_extent_evidence': 'first-referenced-header',
        'table_extent_runtime_verified': False,
        'track_validation': 'ROM bounds, structural ownership, supported first command only',
        'sequence_control_flow_verified': False,
        'structure_reference': STRUCTURE_REFERENCE,
    }


def recognize_engines(path, expected_sha256, system_id, *, cancelled=lambda: False):
    """Hash a <=32 MiB source and return bounded read-only engine findings.

    Identity/input errors raise ValueError; cancellation raises KeyboardInterrupt.
    Other systems explicitly return NOT_IMPLEMENTED. MATCH is static evidence
    for this supported role/layout subset, never engine-version or native proof.
    """
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('expected_sha256 must be an exact SHA-256 identity')
    if not isinstance(system_id, str) or not system_id or len(system_id) > 32:
        raise ValueError('system_id must be a short nonempty string')
    _check(cancelled)
    source = Path(path)
    if source.stat().st_size > MAX_ROM_BYTES:
        raise ValueError('engine recognition source exceeds 32 MiB budget')
    digest, data = hashlib.sha256(), bytearray()
    with source.open('rb') as stream:
        while True:
            _check(cancelled)
            chunk = stream.read(1024*1024)
            if not chunk:
                break
            if len(data)+len(chunk) > MAX_ROM_BYTES:
                raise ValueError('engine recognition source exceeds 32 MiB budget')
            digest.update(chunk)
            data.extend(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha256.lower():
        raise ValueError('engine recognition source SHA-256 mismatch')
    result = {'ok': True, 'status': 'NOT_IMPLEMENTED', 'source_sha256': actual,
              'system_id': system_id, 'findings': [], 'write_authorized': False}
    if system_id != 'gba':
        result['scope'] = 'No recognizer is implemented for this system.'
        return result
    result['status'] = 'NO_MATCH'
    result['scope'] = ('Only the supported straight-line THUMB m4a selection and '
                       'bounded table layout are checked; other engines and variants are not ruled out.')
    raw = bytes(data)
    del data
    anchors, functions = {}, 0
    try:
        # PUSH with LR is an instruction-role entry point, not an opaque engine
        # signature. Byte search avoids a Python halfword walk over 32 MiB.
        cursor = raw.find(b'\xb5', 1)
        while cursor >= 0:
            _check(cancelled)
            if cursor % 2:
                functions += 1
                if functions > MAX_FUNCTIONS:
                    raise _BudgetExceeded('function candidate budget exhausted')
                anchor = _anchor(raw, cursor-1, cancelled)
                if anchor:
                    key = anchor['song_table_offset'], anchor['player_table_offset']
                    anchors.setdefault(key, []).append(anchor)
                    if sum(map(len, anchors.values())) > MAX_ANCHORS or len(anchors) > MAX_FINDINGS:
                        raise _BudgetExceeded('anchor/finding budget exhausted')
            cursor = raw.find(b'\xb5', cursor+1)
        findings = []
        for group in anchors.values():
            _check(cancelled)
            try:
                evidence = _tables(raw, group[0], cancelled)
            except (ValueError, struct.error):
                continue
            evidence['anchor_count'] = len(group)
            evidence['call_targets'] = sorted({a['call_target'] for a in group})
            evidence['literal_offsets'] = sorted({p for a in group for p in a['literal_offsets']})
            locations = [{'offset': a['offset'], 'length': a['length'],
                          'label': 'Indexed song/player selection code'} for a in group]
            locations.extend(({'offset': evidence['song_table_offset'],
                               'length': evidence['song_entries']*8, 'label': 'Song table'},
                              {'offset': evidence['player_table_offset'],
                               'length': evidence['player_table_span'], 'label': 'Referenced player-table span'}))
            findings.append({'family': 'gba-m4a', 'label': 'M4A-compatible audio structures',
                             'confidence': 'code-and-structure', 'engine_version_verified': False,
                             'runtime_verified': False, 'locations': locations,
                             'evidence': evidence, 'reference': REFERENCE})
        if len(findings) > 1:
            result['status'] = 'AMBIGUOUS'
            result['candidate_table_pairs'] = len(findings)
        elif findings:
            result.update(status='MATCH', findings=findings)
    except _BudgetExceeded as error:
        result.update(status='BUDGET_EXCEEDED', findings=[], budget_reason=str(error))
    _check(cancelled)
    return result
