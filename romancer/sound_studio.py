"""Validated sample resources and the identified original Hillside music driver."""
import base64,hashlib,json,math
from .asset_schema import fields,number,label
from .script_schema import canonical_bytes
from .sound_codecs import decode_sample, encode_sample, wav_bytes, read_wav


def inspect_sound(raw, definition, source_sha256):
    if type(definition) is not dict:
        raise ValueError('sound definition must be a JSON object')
    if type(raw) is not bytes or not 1 <= len(raw) <= 64 * 1024 ** 2 or hashlib.sha256(raw).hexdigest() != source_sha256 or (definition.get('source_sha256') != source_sha256):
        raise ValueError('sound definition source differs')
    d = json.loads(canonical_bytes(definition, max_bytes=128 * 1024))
    fields(d, 'schema_version source_sha256 samples songs')
    number(d['schema_version'], 1, 1)
    if type(d['samples']) is not list or len(d['samples']) > 16 or type(d['songs']) is not list or (len(d['songs']) > 16):
        raise ValueError('sound resource count exceeds budget')
    if not d['samples'] and (not d['songs']):
        raise ValueError('declare a supported sample or identified song')
    ranges = []
    ids = set()
    samples = []
    songs = []
    decoded_total = 0

    def storage(offset, length, name):
        number(offset, 0, len(raw) - 1)
        number(length, 1, min(65536, len(raw)))
        if offset + length > len(raw):
            raise ValueError('sound allocation exceeds source')
        if any((offset < b and offset + length > a for a, b, _ in ranges)):
            raise ValueError('sound resources overlap')
        ranges.append((offset, offset + length, name))

    def identity(r):
        label(r['id'])
        label(r['name'])
        if r['id'] in ids:
            raise ValueError('duplicate sound ID')
        ids.add(r['id'])
    for s in d['samples']:
        fields(s, 'id name offset length codec sample_rate initial_level')
        identity(s)
        number(s['sample_rate'], 1000, 96000)
        number(s['initial_level'], 0, 127)
        storage(s['offset'], s['length'], s['id'])
        values = decode_sample(raw[s['offset']:s['offset'] + s['length']], s['codec'], s['initial_level'])
        decoded_total += len(values)
        if decoded_total > 131072:
            raise ValueError('total decoded sound exceeds budget')
        step = max(1, math.ceil(len(values) / 512))
        peaks = [[min(values[i:i + step]), max(values[i:i + step])] for i in range(0, len(values), step)]
        samples.append({**s, 'sample_count': len(values), 'duration_seconds': len(values) / s['sample_rate'], 'peaks': peaks, 'encoding_lossy': s['codec'] in ('nes-dpcm', 'gb-wave4', 'snes-brr'), 'preview_scope': 'Decoded mono sample; hardware filters, envelopes, loops and driver mixing are not emulated.'})
    for song in d['songs']:
        fields(song, 'id name driver offset count stride tempo ticks_per_beat channels')
        identity(song)
        if song['driver'] == 'hillside-pulse-v1':
            from .studio_examples import make_studio_example
            example = make_studio_example()
            expected = example['raw']
            length = example['driver_length']
            pitch = 14864
            pitch_end = 15120
            sequence = 14352
        elif song['driver'] == 'mossy-pulse-v1':
            from .studio_runtime import make_collision_studio_rom
            example = make_collision_studio_rom()
            expected = example['data']
            length = example['program_size']
            pitch = example['pitch_offset']
            pitch_end = pitch + 76 * 2
            sequence = example['music_offset']
        else:
            raise ValueError('music driver is not supported for sequence editing')
        if len(raw) != len(expected) or raw[:16] != expected[:16] or raw[16:16 + length] != expected[16:16 + length] or (raw[16394:16400] != expected[16394:16400]) or (raw[pitch:pitch_end] != expected[pitch:pitch_end]):
            raise ValueError('Original music driver code, vectors or pitch table differs')
        if (song['offset'], song['count'], song['stride'], song['tempo'], song['ticks_per_beat'], song['channels']) != (sequence, 16, 6, 150, 24, 1):
            raise ValueError('Original music driver layout differs from its verified format')
        if any((a < 16 + length and b > 16 or (a < pitch_end and b > pitch) for a, b, _ in ranges)):
            raise ValueError('sound allocation overlaps identified driver code')
        storage(song['offset'], song['count'] * song['stride'], song['id'])
        events = []
        for i in range(song['count']):
            at = song['offset'] + i * 6
            note = raw[at]
            duration = int.from_bytes(raw[at + 1:at + 3], 'little')
            volume, channel, instrument = raw[at + 3:at + 6]
            number(note, 33, 108)
            number(duration, 1, 6000)
            number(volume, 0, 127)
            number(channel, 0, 0)
            number(instrument, 0, 0)
            events.append({'note': note, 'duration': duration, 'volume': volume, 'channel': channel, 'instrument': instrument})
        songs.append({**song, 'events': events, 'sequence_edit_supported': True, 'driver_scope': 'Identified original practice driver; no commercial music-driver format is inferred.'})
    return {'ok': True, 'document_id': hashlib.sha256(canonical_bytes(d, max_bytes=128 * 1024)).hexdigest(), 'source_sha256': source_sha256, 'definition': d, 'samples': samples, 'songs': songs, 'ranges': [{'offset': a, 'length': b - a, 'name': n} for a, b, n in ranges]}


def plan_sound(raw, definition, document_id, changes, source_sha256):
    doc = inspect_sound(raw, definition, source_sha256)
    if doc['document_id'] != document_id:
        raise ValueError('sound review document is stale')
    if type(changes) is not list or not 1 <= len(changes) <= 256:
        raise ValueError('review 1 to256sound changes')
    edits = []
    seen = set()
    lossy = []
    for c in changes:
        if type(c) is not dict:
            raise ValueError('sound changes must be JSON objects')
        if c.get('kind') == 'sample':
            fields(c, 'kind sample_id operation value wav_base64')
            s = next((s for s in doc['samples'] if s['id'] == c['sample_id']), None)
            if s is None:
                raise ValueError('unknown sample')
            key = ('sample', s['id'])
            at = s['offset']
            before = raw[at:at + s['length']]
            values = decode_sample(before, s['codec'], s['initial_level'])
            if c['operation'] == 'gain':
                number(c['value'], 0, 400)
                values = [max(-32768, min(32767, round(v * c['value'] / 100))) for v in values]
            elif c['operation'] == 'reverse':
                values.reverse()
            elif c['operation'] == 'silence':
                values = [0] * len(values)
            elif c['operation'] == 'replace_wav':
                if type(c['wav_base64']) is not str or len(c['wav_base64']) > 3 * 1024 ** 2:
                    raise ValueError('WAV input exceeds byte budget')
                try:
                    wave = base64.b64decode(c['wav_base64'], validate=True)
                except ValueError as exc:
                    raise ValueError('invalid WAV base64') from exc
                values = read_wav(wave, s['sample_rate'], len(values))
            else:
                raise ValueError('unknown sample operation')
            after = encode_sample(values, s['codec'], s['initial_level'], loop=bool(before[-9] & 2) if s['codec'] == 'snes-brr' else False)
            if len(after) != len(before):
                raise ValueError('encoded sample exceeds declared allocation')
            if s['encoding_lossy']:
                lossy.append(s['id'])
        elif c.get('kind') == 'note':
            fields(c, 'kind song_id index field value')
            song = next((s for s in doc['songs'] if s['id'] == c['song_id']), None)
            if song is None:
                raise ValueError('unknown or unsupported music driver')
            number(c['index'], 0, song['count'] - 1)
            bounds = {'note': (0, 1, 33, 108), 'duration': (1, 2, 1, 6000), 'volume': (3, 1, 0, 127)}
            if c['field'] not in bounds:
                raise ValueError('this driver field is not editable')
            offset, width, low, high = bounds[c['field']]
            number(c['value'], low, high)
            at = song['offset'] + c['index'] * song['stride'] + offset
            before = raw[at:at + width]
            after = c['value'].to_bytes(width, 'little')
            key = ('note', song['id'], c['index'], c['field'])
        else:
            raise ValueError('unknown sound edit')
        if key in seen:
            raise ValueError('duplicate sound edit')
        seen.add(key)
        if before != after:
            edits.append({'offset': at, 'before': before.hex(), 'after': after.hex()})
    if not edits:
        raise ValueError('no changed sound bytes')
    return {'ok': True, 'edits': sorted(edits, key=lambda e: e['offset']), 'lossy_reencoded_samples': lossy, 'source_sha256': source_sha256, 'document_id': document_id}


def preview_sound(raw, definition, source_sha256, kind, resource_id, changes=None):
    doc = inspect_sound(raw, definition, source_sha256)
    if changes:
        plan = plan_sound(raw, definition, doc['document_id'], changes, source_sha256)
        copy = bytearray(raw)
        for e in plan['edits']:
            copy[e['offset']:e['offset'] + len(e['before']) // 2] = bytes.fromhex(e['after'])
        raw = bytes(copy)
    if kind == 'sample':
        s = next((s for s in doc['samples'] if s['id'] == resource_id), None)
        if s is None:
            raise ValueError('unknown sample')
        values = decode_sample(raw[s['offset']:s['offset'] + s['length']], s['codec'], s['initial_level'])
        return (wav_bytes(values, s['sample_rate']), {'kind': 'sample', 'sample_rate': s['sample_rate'], 'sample_frames': len(values), 'truncated': False, 'preview_scope': s['preview_scope']})
    if kind != 'song':
        raise ValueError('choose a sample or an identified song')
    song = next((s for s in doc['songs'] if s['id'] == resource_id), None)
    if song is None:
        raise ValueError('unknown music driver')
    rate = 22050
    values = []
    total = 0
    limit = rate * 20
    for i in range(song['count']):
        at = song['offset'] + i * 6
        note = raw[at]
        duration = int.from_bytes(raw[at + 1:at + 3], 'little')
        volume = raw[at + 3] >> 3
        pitch = 7184 + (note - 33) * 2 if song['driver'] == 'mossy-pulse-v1' else 14864 + note * 2
        period = int.from_bytes(raw[pitch:pitch + 2], 'little')
        frequency = 1789773 / (16 * (period + 1))
        count = round((duration + 1 if song['driver'] == 'mossy-pulse-v1' else duration) / 60 * rate)
        total += count
        for n in range(min(count, limit - len(values))):
            values.append(round((1 if n * frequency / rate % 1 < 0.5 else -1) * volume / 15 * 10000))
    return (wav_bytes(values, rate), {'kind': 'song', 'sample_rate': rate, 'sample_frames': len(values), 'truncated': total > limit, 'preview_scope': 'Reference pulse preview, up to20seconds. Native playback verifies the actual driver, mixer and timing.'})
