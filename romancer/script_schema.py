"""Strict declarative script schemas; support is not proof of game compatibility."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from . import contracts

SCHEMA_VERSION = 1
MAX_SCHEMA_JSON_BYTES = 4 * 1024 * 1024
MAX_EDITS_JSON_BYTES = 1024 * 1024
MAX_OUTPUT_JSON_BYTES = 8 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100000
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
MAX_REVISIONS = 16
MAX_RECORDS = 256
MAX_POINTERS = 512
MAX_RULES = 1024
MAX_SLOT_BYTES = 64 * 1024
MAX_TOTAL_RULE_BYTES = 256 * 1024
MAX_GLYPHS = 256
MAX_CONTROLS = 64
MAX_TOKENS = 4096
MAX_CHANGES = 1024
MAX_REPLACEMENT_SCALARS = 65536


def _integer(value, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{label} is outside the supported integer range')
    return value


def canonical_bytes(value: object, *, max_bytes: int) -> bytes:
    """Bounded canonical JSON: sorted keys, ordered arrays, compact ASCII escapes."""
    _integer(max_bytes, 'max_bytes', 1)
    nodes = 0
    string_bytes = 0
    active = set()

    def visit(item, depth):
        nonlocal nodes, string_bytes
        nodes += 1
        if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
            raise ValueError('JSON depth or node budget exceeded')
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active:
                raise ValueError('cyclic objects are not JSON')
            active.add(id(item))
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError('JSON object keys must be strings')
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(id(item))
        elif kind is str:
            if len(item) > max_bytes:
                raise ValueError('JSON byte budget exceeded')
            try:
                string_bytes += len(item.encode('utf-8'))
            except UnicodeEncodeError as exc:
                raise ValueError('JSON strings require valid Unicode scalars') from exc
            if string_bytes > max_bytes:
                raise ValueError('JSON byte budget exceeded')
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError('JSON numbers must be finite')
        elif kind not in (int, bool, type(None)):
            raise ValueError('value is not a plain JSON type')

    visit(value, 0)
    encoded = bytearray()
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    for piece in encoder.iterencode(value):
        if len(piece) > max_bytes - len(encoded):
            raise ValueError('canonical JSON byte budget exceeded')
        encoded.extend(piece.encode('ascii'))
    return bytes(encoded)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('JSON numbers must be finite')


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _assert_stable(path, stream, initial):
    if (_identity(os.fstat(stream.fileno())) != _identity(initial)
            or _identity(path.stat()) != _identity(initial)):
        raise ValueError('JSON input changed during capture')


def _read_bounded(stream, limit):
    raw = bytearray()
    while True:
        chunk = stream.read(min(READ_CHUNK_BYTES, limit + 1 - len(raw)))
        if not chunk:
            return bytes(raw)
        raw.extend(chunk)
        if len(raw) > limit:
            raise ValueError('JSON input exceeds byte budget')


def load_script_json(path: Path, *, max_bytes: int) -> dict:
    """Capture a stable bounded UTF-8 JSON object; never resolve schema fields."""
    _integer(max_bytes, 'max_bytes', 1)
    path = Path(path).absolute()
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('JSON input must be a regular file')
    if before.st_size > max_bytes:
        raise ValueError('JSON input exceeds byte budget')
    with path.open('rb', buffering=0) as stream:
        initial = os.fstat(stream.fileno())
        if _identity(initial) != _identity(before):
            raise ValueError('JSON input changed while opening')
        raw = _read_bounded(stream, max_bytes)
        if len(raw) != initial.st_size:
            raise ValueError('JSON input size changed during capture')
        _assert_stable(path, stream, initial)
        # A second bounded pass detects same-size rewrites with restored mtime.
        stream.seek(0)
        if _read_bounded(stream, max_bytes) != raw:
            raise ValueError('JSON input bytes changed during capture')
        _assert_stable(path, stream, initial)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    except RecursionError as exc:
        raise ValueError('JSON nesting exceeds supported depth') from exc
    if type(value) is not dict:
        raise ValueError('JSON input must be an object')
    canonical_bytes(value, max_bytes=max_bytes)
    return value


def _fields(value, required, optional=()):
    required = set(required)
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - set(optional):
        raise ValueError('unexpected or missing schema fields')


def _label(value, label, limit=128):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
        raise ValueError(f'{label} must be a nonblank label without controls (maximum {limit} scalars)')
    return value


def _list(value, label, maximum, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError(f'{label} must be a list within its item budget')
    return value


def _profile_limits(profile, size):
    _fields(profile, ('schema_version', 'id', 'version', 'system', 'accepted_sha256', 'rules'), ('provenance',))
    _list(profile['accepted_sha256'], 'accepted revisions', MAX_REVISIONS, 1)
    rules = _list(profile['rules'], 'profile rules', MAX_RULES)
    total = 0
    by_name = {}
    for rule in rules:
        _fields(rule, ('resource', 'offset', 'length', 'expected_hex'))
        name = _label(rule['resource'], 'rule resource', 256)
        if name in by_name:
            raise ValueError('duplicate profile resource label')
        offset = _integer(rule['offset'], 'rule offset')
        length = _integer(rule['length'], 'rule length', 1, MAX_TOTAL_RULE_BYTES)
        if offset > size or length > size - offset:
            raise ValueError('rule extends beyond artifact size')
        total += length
        if total > MAX_TOTAL_RULE_BYTES:
            raise ValueError('total rule bytes exceed budget')
        if type(rule['expected_hex']) is not str or len(rule['expected_hex']) != length * 2:
            raise ValueError('expected_hex must encode the complete rule length')
        by_name[name] = rule
    return by_name


def _format_limits(format_spec, rules):
    _fields(format_spec, ('family', 'version', 'encoding', 'controls', 'terminator', 'padding',
                          'records', 'pointers', 'guards'))
    _list(format_spec['records'], 'records', MAX_RECORDS, 1)
    _list(format_spec['pointers'], 'pointers', MAX_POINTERS, 0 if format_spec['family']=='fixed-slots-direct' else 1)
    _list(format_spec['controls'], 'controls', MAX_CONTROLS)
    _list(format_spec['guards'], 'guards', MAX_RULES)
    encoding = format_spec['encoding']
    if type(encoding) is not dict or 'kind' not in encoding:
        raise ValueError('encoding requires a kind')
    _label(encoding['kind'], 'encoding kind')
    if encoding['kind'] == 'single-byte':
        _fields(encoding, ('kind', 'glyphs'))
        _list(encoding['glyphs'], 'glyphs', MAX_GLYPHS)
    for record in format_spec['records']:
        _fields(record, ('id', 'rule', 'annotations'))
        name = _label(record['rule'], 'record rule', 256)
        if name in rules and rules[name]['length'] > MAX_SLOT_BYTES:
            raise ValueError('record slot exceeds 64 KiB')


def _validate_fixed(format_spec, rules, size, reasons):
    byte_classes = set()
    encoding = format_spec['encoding']
    if encoding['kind'] == 'single-byte':
        texts = set()
        for glyph in encoding['glyphs']:
            _fields(glyph, ('byte', 'text'))
            code = _integer(glyph['byte'], 'glyph byte', 0, 255)
            text = glyph['text']
            if type(text) is not str or len(text) != 1 or ord(text) < 32 or 127 <= ord(text) <= 159:
                raise ValueError('glyph text must be one Unicode scalar excluding C0/C1 controls')
            if code in byte_classes or text in texts:
                raise ValueError('glyph bytes and text outputs must be unique')
            byte_classes.add(code)
            texts.add(text)
    else:
        reasons.append('Unsupported encoding kind; encoding data is uninterpreted.')

    control_ids = set()
    for control in format_spec['controls']:
        _fields(control, ('id', 'opcode', 'argument_length', 'position_independent', 'layout_role'))
        identifier = _label(control['id'], 'control ID')
        opcode = _integer(control['opcode'], 'control opcode', 0, 255)
        _integer(control['argument_length'], 'control argument length', 0, 16)
        if type(control['position_independent']) is not bool:
            raise ValueError('control position_independent must be boolean')
        if control['layout_role'] not in ('opaque', 'line', 'page', 'pause'):
            raise ValueError('unsupported control layout_role')
        if identifier in control_ids or opcode in byte_classes:
            raise ValueError('duplicate control ID or overlapping byte classes')
        control_ids.add(identifier)
        byte_classes.add(opcode)
        if not control['position_independent']:
            reasons.append(f'Control {identifier} is position-dependent.')
    for name in ('terminator', 'padding'):
        _fields(format_spec[name], ('byte',))
        code = _integer(format_spec[name]['byte'], name + ' byte', 0, 255)
        if code in byte_classes:
            raise ValueError('glyph, control, terminator and padding byte classes must be disjoint')
        byte_classes.add(code)

    consumed = set()

    def claim(name):
        _label(name, 'rule reference', 256)
        if name not in rules or name in consumed:
            raise ValueError('unknown or multiply assigned profile rule')
        consumed.add(name)
        return rules[name]

    records = {}
    for record in format_spec['records']:
        identifier = _label(record['id'], 'record ID')
        if identifier in records:
            raise ValueError('duplicate record ID')
        records[identifier] = claim(record['rule'])
        annotations = record['annotations']
        _fields(annotations, ('label', 'speaker_label', 'speaker_provenance', 'layout_ref'))
        for name, value in annotations.items():
            if value is not None:
                _label(value, name, 256)
        if (annotations['speaker_label'] is None) != (annotations['speaker_provenance'] is None):
            raise ValueError('speaker label and provenance must be paired')

    pointer_ids = set()
    incoming = set()
    for pointer in format_spec['pointers']:
        _fields(pointer, ('id', 'rule', 'target_record', 'width', 'endian', 'base'))
        identifier = _label(pointer['id'], 'pointer ID')
        if identifier in pointer_ids:
            raise ValueError('duplicate pointer ID')
        pointer_ids.add(identifier)
        rule = claim(pointer['rule'])
        target = _label(pointer['target_record'], 'target record ID')
        if target not in records:
            raise ValueError('unknown pointer target record')
        width = _integer(pointer['width'], 'pointer width', 2, 4)
        if rule['length'] != width or pointer['endian'] not in ('little', 'big'):
            raise ValueError('pointer width/field length or endian mismatch')
        # Text schema convention: file offset = stored pointer + base.
        # CPU ROM windows therefore require a negative additive base.
        base = _integer(pointer['base'], 'pointer base', -0xffffffff, 0xffffffff)
        offset = records[target]['offset']
        stored = offset - base
        if not 0 <= offset < size or not 0 <= stored < 2 ** (8 * width):
            raise ValueError('pointer target is out of bounds or not representable')
        if int.from_bytes(bytes.fromhex(rule['expected_hex']), pointer['endian']) != stored:
            raise ValueError('pointer expected bytes do not target the exact record start')
        incoming.add(target)
    for guard in format_spec['guards']:
        claim(guard)
    if consumed != set(rules):
        raise ValueError('every profile rule must be assigned exactly once')
    if format_spec['family']=='fixed-slots-direct' and format_spec['pointers']:
        raise ValueError('direct fixed slots do not declare pointer relationships')
    if format_spec['family']!='fixed-slots-direct' and incoming != set(records):
        raise ValueError('every record requires a declared incoming pointer')


def validate_schema(schema: dict) -> dict:
    """Validate declarations, returning detached normalized data and capability reasons."""
    normalized = json.loads(canonical_bytes(schema, max_bytes=MAX_SCHEMA_JSON_BYTES))
    _fields(normalized, ('schema_version', 'id', 'version', 'artifact', 'profile', 'format'))
    if type(normalized['schema_version']) is not int or normalized['schema_version'] != SCHEMA_VERSION:
        raise ValueError('unsupported script envelope schema_version')
    _label(normalized['id'], 'schema ID')
    _label(normalized['version'], 'schema version label')
    artifact = normalized['artifact']
    _fields(artifact, ('kind', 'size', 'integrity'))
    _label(artifact['kind'], 'artifact kind')
    _label(artifact['integrity'], 'artifact integrity')
    size = _integer(artifact['size'], 'artifact size', 1, MAX_ARTIFACT_BYTES)
    rules = _profile_limits(normalized['profile'], size)
    format_spec = normalized['format']
    if type(format_spec) is not dict or not {'family', 'version'} <= format_spec.keys():
        raise ValueError('format requires family and version')
    _label(format_spec['family'], 'format family')
    _integer(format_spec['version'], 'format version', 1)
    known = format_spec['family'] in ('fixed-slots','fixed-slots-direct') and format_spec['version'] == 1
    if known:
        _format_limits(format_spec, rules)
    normalized['profile'] = contracts.validate_contract(normalized['profile'])['normalized_profile']
    rules = {rule['resource']: rule for rule in normalized['profile']['rules']}
    reasons = []
    if artifact['kind'] != 'flat-resource':
        reasons.append('Unsupported artifact kind; only declared standalone flat resources are writable.')
    if artifact['integrity'] != 'none':
        reasons.append('Unsupported artifact integrity obligations.')
    if known:
        _validate_fixed(format_spec, rules, size, reasons)
    else:
        reasons.append('Unsupported format family or version; format data is uninterpreted.')
    encoded = canonical_bytes(normalized, max_bytes=MAX_SCHEMA_JSON_BYTES)
    return {'normalized_schema': normalized, 'schema_sha256': hashlib.sha256(encoded).hexdigest(),
            'write_supported': not reasons, 'read_only_reasons': reasons}
