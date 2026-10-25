"""Lossless, revision-bound fixed-slot scripts; no inferred game semantics."""

import hashlib
import json
import os
from pathlib import Path
import stat

from . import ROMANCER_VERSION
from .script_schema import canonical_bytes, validate_schema

CHUNK_SIZE = 64 * 1024
MAX_ARTIFACT = 64 * 1024 * 1024
MAX_EDITS = 1024 * 1024
MAX_REPORT = 8 * 1024 * 1024
MAX_TOKENS = 4096


class ScriptError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _result(operation):
    return {'schema_version': 1, 'tool_version': ROMANCER_VERSION,
            'scope': 'structured_script', 'operation': operation,
            'source_sha256': None, 'schema_sha256': None, 'source_size': None,
            'write_supported': False, 'ok': False, 'status': 'BLOCKED',
            'warnings': [], 'read_only_reasons': []}


def _failure(operation, exc, *, phase='validation', context=None):
    cancelled = isinstance(exc, KeyboardInterrupt)
    measured = {**(context or {}), **getattr(exc, 'script_context', {})}
    context = {key: value for key, value in measured.items()
               if key in {'source_sha256', 'schema_sha256', 'source_size'}}
    return {**_result(operation), **context, 'status': 'CANCELLED' if cancelled else 'BLOCKED',
            'cancelled': cancelled, 'phase': phase,
            'error_code': 'CANCELLED' if cancelled else getattr(exc, 'code', type(exc).__name__),
            'error': ('Operation cancelled' if cancelled else str(exc))[:2048]}


def _report_size(result):
    size = 1  # The CLI appends a newline to its pretty-printed JSON.
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2)
    for piece in encoder.iterencode(result):
        size += len(piece)
        if size > MAX_REPORT:
            raise ScriptError('REPORT_LIMIT', 'private script report exceeds 8 MiB')
    return size


def _bounded_result(result):
    _report_size(result)
    return result


def _digest(value):
    return hashlib.sha256(canonical_bytes(value, max_bytes=MAX_REPORT)).hexdigest()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _no_links(path):
    path = Path(path).absolute()
    if os.name == 'nt' and (os.path.isreserved(path)
            or str(path).replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\'))):
        raise ScriptError('UNSAFE_PATH', f'reserved or ambiguous Windows path: {path}')
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ScriptError('UNSAFE_PATH', f'linked path ancestry is not supported: {item}')
    return path


def _source_info(path):
    _no_links(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ARTIFACT:
        raise ScriptError('SOURCE_BOUNDS', 'source must be an ordinary file of 1..67108864 bytes')
    return info


def _assert_source(path, stream, initial):
    _no_links(path)
    if (_identity(path.lstat()) != _identity(initial)
            or _identity(os.fstat(stream.fileno())) != _identity(initial)):
        raise ScriptError('SOURCE_CHANGED', 'source pathname or held file changed')


def _hash_stream(stream, size):
    stream.seek(0)
    digest = hashlib.sha256()
    remaining = size
    while remaining:
        data = stream.read(min(CHUNK_SIZE, remaining))
        if not data:
            raise ScriptError('SOURCE_CHANGED', 'file truncated during hashing')
        remaining -= len(data)
        digest.update(data)
    if stream.read(1):
        raise ScriptError('SOURCE_CHANGED', 'file grew during hashing')
    return digest.hexdigest()


def _read_exact(stream, size):
    raw = bytearray()
    while len(raw) < size:
        chunk = stream.read(min(CHUNK_SIZE, size - len(raw)))
        if not chunk:
            raise ScriptError('SOURCE_CHANGED', 'file truncated while reading a declared range')
        raw.extend(chunk)
    return bytes(raw)


def _record_spec(record, rules):
    rule = rules[record['rule']]
    return {'id': record['id'], 'offset': rule['offset'], 'capacity': rule['length'],
            'annotations': record['annotations']}


def parse_slot(raw: bytes, record: dict, format_spec: dict) -> dict:
    """Parse an already bounded slot, retaining undecodable bytes as opaque data."""
    if type(raw) is not bytes or len(raw) != record['capacity']:
        raise ScriptError('SLOT_SIZE', 'slot bytes do not match the declared capacity')
    row = {**record, 'raw_hex': raw.hex(), 'tokens': [], 'segments': [],
           'used_bytes': None, 'padding_bytes': None, 'read_only_reasons': []}
    glyphs = {item['byte']: item['text'] for item in format_spec['encoding']['glyphs']}
    controls = {item['opcode']: item for item in format_spec['controls']}
    terminator, pad = format_spec['terminator']['byte'], format_spec['padding']['byte']

    def token(kind, start, end, **extra):
        row['tokens'].append({'kind': kind, 'offset': start, 'length': end - start,
                              'raw_hex': raw[start:end].hex(), **extra})
        if len(row['tokens']) + len(row['segments']) > MAX_TOKENS:
            raise ScriptError('TOKEN_LIMIT', 'script token/segment budget exceeded')

    def text(start, end):
        text_glyphs = [{'byte': raw[index], 'text': glyphs[raw[index]], 'offset': index}
                      for index in range(start, end)]
        row['segments'].append({'index': len(row['segments']), 'offset': start,
                                'length': end - start, 'raw_hex': raw[start:end].hex(),
                                'text': ''.join(item['text'] for item in text_glyphs)})
        token('text', start, end, glyphs=text_glyphs)

    index = start = 0
    reason = 'record has no terminator within its allocation'
    while index < len(raw):
        value = raw[index]
        if value == terminator:
            text(start, index)
            token('terminator', index, index + 1)
            if any(value != pad for value in raw[index + 1:]):
                reason = 'bytes after terminator are not the declared padding'
                break
            token('padding', index + 1, len(raw))
            row.update(used_bytes=index + 1, padding_bytes=len(raw) - index - 1)
            return row
        if value in controls:
            control = controls[value]
            end = index + 1 + control['argument_length']
            if end > len(raw):
                reason = 'truncated control arguments'
                break
            text(start, index)
            token('control', index, end, control_id=control['id'],
                  arguments_hex=raw[index + 1:end].hex(), layout_role=control['layout_role'])
            index = start = end
        elif value in glyphs:
            index += 1
        else:
            reason = f'unknown byte at record-relative offset {index}'
            break
    row.update(tokens=[{'kind': 'opaque', 'offset': 0, 'length': len(raw), 'raw_hex': raw.hex()}],
               segments=[], read_only_reasons=[reason])
    return row


def serialize_original(record_model: dict) -> bytes:
    return b''.join(bytes.fromhex(token['raw_hex']) for token in record_model['tokens'])


def _pointers(schema, rule_bytes):
    fmt = schema['format']
    rules = {item['resource']: item for item in schema['profile']['rules']}
    records = {item['id']: rules[item['rule']] for item in fmt['records']}
    rows = []
    for pointer in fmt['pointers']:
        raw = rule_bytes[pointer['rule']]
        stored = int.from_bytes(raw, pointer['endian'], signed=False)
        target = pointer['base'] + stored
        expected = records[pointer['target_record']]['offset']
        if (len(raw) != pointer['width'] or target != expected
                or not 0 <= target < schema['artifact']['size']
                or not 0 <= expected - pointer['base'] < 2 ** (8 * pointer['width'])):
            raise ScriptError('POINTER_TARGET', f'pointer does not target its declared record start: {pointer["id"]}')
        rows.append({**pointer, 'offset': rules[pointer['rule']]['offset'],
                     'raw_hex': raw.hex(), 'target_offset': target})
    return rows


def inspect_stream(stream, schema: dict) -> dict:
    """Internal held-source inspection; the caller owns closure and path checks."""
    context = {}
    try:
        return _inspect_stream(stream, schema, context)
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        exc.script_context = context
        raise


def _inspect_stream(stream, schema, context):
    validation = validate_schema(schema)
    context['schema_sha256'] = validation['schema_sha256']
    normalized = validation['normalized_schema']
    initial = os.fstat(stream.fileno())
    context['source_size'] = initial.st_size
    if (not stat.S_ISREG(initial.st_mode) or not 0 < initial.st_size <= MAX_ARTIFACT
            or initial.st_size != normalized['artifact']['size']):
        raise ScriptError('SOURCE_BOUNDS', 'source size does not match the declared resource')
    observed = _hash_stream(stream, initial.st_size)
    context['source_sha256'] = observed
    if observed not in normalized['profile']['accepted_sha256']:
        raise ScriptError('REVISION_MISMATCH', 'source is not an accepted complete resource revision')
    if _identity(os.fstat(stream.fileno())) != _identity(initial):
        raise ScriptError('SOURCE_CHANGED', 'source changed while measuring revision')
    rule_bytes = {}
    for rule in normalized['profile']['rules']:
        if rule['offset'] > initial.st_size - rule['length']:
            raise ScriptError('RULE_BOUNDS', 'rule extends outside the source')
        stream.seek(rule['offset'])
        actual = _read_exact(stream, rule['length'])
        if actual != bytes.fromhex(rule['expected_hex']):
            raise ScriptError('RULE_MISMATCH', f'full expected bytes differ: {rule["resource"]}')
        rule_bytes[rule['resource']] = actual
    doc = {**_result('inspect'), 'source_sha256': observed, 'source_size': initial.st_size,
           'source_identity': list(_identity(initial)), 'parser_version': 1,
           'schema_sha256': validation['schema_sha256'], 'records': [], 'pointers': [],
           'provenance': 'profile_assertion',
           'read_only_reasons': list(validation['read_only_reasons'])}
    doc['document_id'] = _digest({key: doc[key] for key in
                                 ('parser_version', 'schema_sha256', 'source_sha256', 'source_size')})
    if validation['write_supported']:
        doc['encoding_glyphs']=[g['text'] for g in normalized['format']['encoding']['glyphs']]
        rules = {item['resource']: item for item in normalized['profile']['rules']}
        doc['pointers'] = _pointers(normalized, rule_bytes)
        for record in normalized['format']['records']:
            parsed = parse_slot(rule_bytes[record['rule']], _record_spec(record, rules), normalized['format'])
            doc['records'].append(parsed)
            doc['read_only_reasons'].extend(f'{record["id"]}: {reason}' for reason in parsed['read_only_reasons'])
            if sum(len(row['tokens']) + len(row['segments']) for row in doc['records']) > MAX_TOKENS:
                raise ScriptError('TOKEN_LIMIT', 'script token/segment budget exceeded')
    else:
        doc['raw_rules'] = [{'resource': key, 'raw_hex': value.hex()} for key, value in rule_bytes.items()]
        doc['uninterpreted_schema'] = normalized
    if (_hash_stream(stream, initial.st_size) != observed
            or _identity(os.fstat(stream.fileno())) != _identity(initial)):
        raise ScriptError('SOURCE_CHANGED', 'source changed during script inspection')
    doc.update(ok=True, write_supported=not doc['read_only_reasons'],
               status='READ_ONLY' if doc['read_only_reasons'] else 'INSPECTED')
    return _bounded_result(doc)


def inspect_script(source: Path, schema: dict) -> dict:
    try:
        normalized = validate_schema(schema)['normalized_schema']
        path = Path(source).absolute()
        initial = _source_info(path)
        with path.open('rb', buffering=0) as stream:
            _assert_source(path, stream, initial)
            doc = inspect_stream(stream, normalized)
            _assert_source(path, stream, initial)
        return doc
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        return _failure('inspect', exc)


def _snapshot_edits(edits):
    return json.loads(canonical_bytes(edits, max_bytes=MAX_EDITS))


def compile_changes(document: dict, schema: dict, edits: dict) -> dict:
    """Internal proposal compiler; public file entry points always inspect anew."""
    validation = validate_schema(schema)
    normalized = validation['normalized_schema']
    edits = _snapshot_edits(edits)
    if not document['ok'] or not document['write_supported'] or not validation['write_supported']:
        raise ScriptError('READ_ONLY', 'unsupported or undecodable script cannot be edited or cloned')
    fields = {'schema_version', 'document_id', 'source_sha256', 'schema_sha256', 'changes'}
    if type(edits) is not dict or set(edits) != fields or type(edits['schema_version']) is not int or edits['schema_version'] != 1:
        raise ScriptError('EDIT_SCHEMA', 'edit request fields must exactly match schema version 1')
    for key in ('document_id', 'source_sha256', 'schema_sha256'):
        if edits[key] != document[key]:
            raise ScriptError('STALE_REQUEST', f'edit request does not match current {key}')
    if document['schema_sha256'] != validation['schema_sha256']:
        raise ScriptError('STALE_SCHEMA', 'schema changed after inspection')
    changes = edits['changes']
    if type(changes) is not list or len(changes) > 1024:
        raise ScriptError('EDIT_SCHEMA', 'changes must be a list with at most 1024 entries')
    records = {row['id']: row for row in document['records']}
    order = {key: index for index, key in enumerate(records)}
    replacements, deltas = {}, []
    encoding = {item['text']: item['byte'] for item in normalized['format']['encoding']['glyphs']}
    for change in changes:
        if type(change) is not dict or set(change) != {'record_id', 'segment', 'text'}:
            raise ScriptError('EDIT_SCHEMA', 'changes contain only record_id, segment and text')
        record_id, segment, text = change['record_id'], change['segment'], change['text']
        if (type(record_id) is not str or record_id not in records or type(segment) is not int
                or not 0 <= segment < len(records[record_id]['segments'])
                or type(text) is not str or len(text) > 65536):
            raise ScriptError('EDIT_TARGET', 'invalid record, segment or replacement text')
        key = (record_id, segment)
        if key in replacements:
            raise ScriptError('DUPLICATE_EDIT', 'each text segment can be changed only once')
        try:
            replacements[key] = bytes(encoding[scalar] for scalar in text)
        except KeyError:
            raise ScriptError('UNENCODABLE_TEXT', 'text contains an unmapped scalar; controls cannot be injected') from None
        deltas.append({**change, 'before_text': records[record_id]['segments'][segment]['text']})
    ordered = sorted(changes, key=lambda change: (order[change['record_id']], change['segment']))
    hunks, final_records = [], []
    fmt = normalized['format']
    for row in document['records']:
        before = bytes.fromhex(row['raw_hex'])
        parts, segment = [], 0
        for token in row['tokens']:
            if token['kind'] == 'text':
                parts.append(replacements.get((row['id'], segment), bytes.fromhex(token['raw_hex'])))
                segment += 1
            elif token['kind'] in {'control', 'terminator'}:
                parts.append(bytes.fromhex(token['raw_hex']))
        body = b''.join(parts)
        if len(body) > row['capacity']:
            raise ScriptError('CAPACITY', f'replacement exceeds fixed allocation: {row["id"]}')
        after = body + bytes([fmt['padding']['byte']]) * (row['capacity'] - len(body))
        if after != before:
            hunks.append({'record_id': row['id'], 'offset': row['offset'],
                          'before_hex': before.hex(), 'after_hex': after.hex()})
        spec = {key: row[key] for key in ('id', 'offset', 'capacity', 'annotations')}
        final_records.append(parse_slot(after if after != before else before, spec, fmt))
    hunks.sort(key=lambda hunk: hunk['offset'])
    plan = {**document, 'operation': 'plan', 'status': 'PLANNED' if hunks else 'NO_CHANGES',
            'plan_version': 1, 'tool_version': ROMANCER_VERSION, 'hunks': hunks,
            'normalized_changes': ordered, 'text_deltas': sorted(deltas, key=lambda row: (order[row['record_id']], row['segment'])),
            'final_records': final_records, 'changed_record_count': len(hunks),
            'changed_byte_count': sum(sum(a != b for a, b in zip(bytes.fromhex(h['before_hex']),
                                                               bytes.fromhex(h['after_hex']))) for h in hunks)}
    plan['plan_id'] = _digest({key: plan[key] for key in
                              ('plan_version', 'tool_version', 'document_id', 'normalized_changes', 'hunks')})
    return _bounded_result(plan)


def plan_script(source: Path, schema: dict, edits: dict) -> dict:
    context = None
    try:
        normalized = validate_schema(schema)['normalized_schema']
        edits = _snapshot_edits(edits)
        path = Path(source).absolute()
        initial = _source_info(path)
        with path.open('rb', buffering=0) as stream:
            _assert_source(path, stream, initial)
            doc = inspect_stream(stream, normalized)
            context = doc
            plan = compile_changes(doc, normalized, edits)
            _assert_source(path, stream, initial)
        return plan
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        return _failure('plan', exc, context=context)
