"""Bounded supplied-bitmap measurements, not evidence of native font usage."""

import hashlib
import json
import ntpath
import os
from pathlib import Path
import stat

from . import ROMANCER_VERSION
from .script_schema import canonical_bytes

SCHEMA_VERSION = 1
METRICS_VERSION = 1
MAX_FONT_JSON_BYTES = 1024 * 1024
MAX_FONT_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
MAX_GLYPHS = 256
MAX_BITMAP_BYTES = 64 * 1024
MAX_ADVANCE_FIELDS = 256


class FontError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{label} is outside the supported integer range')
    return value


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError('unexpected or missing font schema fields')


def _label(value, label, limit=128):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
        raise ValueError(f'{label} must be a bounded nonblank label without controls')
    return value


def _provenance(value):
    _fields(value, ('origin', 'note', 'reference'))
    if value['origin'] not in ('profile_assertion', 'synthetic_fixture'):
        raise ValueError('unsupported provenance origin')
    _label(value['note'], 'provenance note', 512)
    if value['reference'] is not None:
        _label(value['reference'], 'provenance reference', 256)


def _dimensions(width, height, row_stride):
    _integer(width, 'bitmap width', 1, 32)
    _integer(height, 'bitmap height', 1, 32)
    _integer(row_stride, 'bitmap row stride', 1, 4)
    if row_stride != (width + 7) // 8:
        raise ValueError('bitmap row stride must equal ceil(width/8)')


def measure_bitmap(raw: bytes, *, width: int, height: int, row_stride: int) -> dict:
    """Measure MSB-first row-packed ink; bounds exclude unused low padding bits."""
    _dimensions(width, height, row_stride)
    if type(raw) is not bytes or len(raw) != row_stride * height:
        raise ValueError('bitmap requires exactly row_stride*height bytes')
    padding_mask = (1 << ((8 - width % 8) % 8)) - 1
    xmin, ymin, xmax, ymax, pixels = width, height, -1, -1, 0
    for y in range(height):
        if raw[(y + 1) * row_stride - 1] & padding_mask:
            raise ValueError('unused low bitmap bits must be zero')
        for x in range(width):
            if raw[y * row_stride + x // 8] & (128 >> (x % 8)):
                pixels += 1
                xmin, ymin = min(xmin, x), min(ymin, y)
                xmax, ymax = max(xmax, x), max(ymax, y)
    return {'ink_bounds': [xmin, ymin, xmax + 1, ymax + 1] if pixels else None,
            'ink_pixels': pixels, 'bitmap_sha256': hashlib.sha256(raw).hexdigest()}


def validate_font_schema(schema: dict) -> dict:
    """Return a detached strict descriptor; unknown codecs never grant measurement."""
    encoded = canonical_bytes(schema, max_bytes=MAX_FONT_JSON_BYTES)
    normalized = json.loads(encoded)
    _fields(normalized, ('schema_version', 'id', 'version', 'source', 'codec', 'glyphs', 'provenance'))
    _integer(normalized['schema_version'], 'schema_version', SCHEMA_VERSION, SCHEMA_VERSION)
    _label(normalized['id'], 'font ID')
    _label(normalized['version'], 'font version')
    _label(normalized['codec'], 'font codec')
    _provenance(normalized['provenance'])
    source = normalized['source']
    _fields(source, ('sha256', 'size'))
    size = _integer(source['size'], 'font size', 1, MAX_FONT_BYTES)
    digest = source['sha256']
    if (type(digest) is not str or len(digest) != 64
            or any(c not in '0123456789abcdef' for c in digest)):
        raise ValueError('source sha256 must be lowercase SHA-256')
    glyphs = normalized['glyphs']
    if type(glyphs) is not list or not 1 <= len(glyphs) <= MAX_GLYPHS:
        raise ValueError('glyph count exceeds supported bounds')
    identifiers, ranges = set(), []
    total_bitmap = total_fields = 0
    for glyph in glyphs:
        _fields(glyph, ('id', 'bitmap', 'bearing', 'advance', 'provenance'))
        identifier = _label(glyph['id'], 'glyph ID')
        if identifier in identifiers:
            raise ValueError('duplicate glyph ID')
        identifiers.add(identifier)
        _provenance(glyph['provenance'])
        bitmap = glyph['bitmap']
        _fields(bitmap, ('offset', 'width', 'height', 'row_stride'))
        _dimensions(bitmap['width'], bitmap['height'], bitmap['row_stride'])
        offset = _integer(bitmap['offset'], 'bitmap offset', 0, size)
        length = bitmap['height'] * bitmap['row_stride']
        if length > size - offset:
            raise ValueError('bitmap range extends beyond font size')
        ranges.append((offset, offset + length))
        total_bitmap += length
        _fields(glyph['bearing'], ('x', 'y'))
        for axis in ('x', 'y'):
            _integer(glyph['bearing'][axis], 'bearing ' + axis, -64, 64)
        advance = glyph['advance']
        if type(advance) is not dict:
            raise ValueError('advance must be a tagged object')
        if advance.get('kind') == 'u8':
            _fields(advance, ('kind', 'offset'))
            offset = _integer(advance['offset'], 'advance offset', 0, size - 1)
            ranges.append((offset, offset + 1))
            total_fields += 1
        elif advance.get('kind') == 'declared':
            _fields(advance, ('kind', 'pixels', 'provenance'))
            _integer(advance['pixels'], 'advance pixels', 0, 128)
            _provenance(advance['provenance'])
        else:
            raise ValueError('advance kind must be u8 or declared')
    if total_bitmap > MAX_BITMAP_BYTES or total_fields > MAX_ADVANCE_FIELDS:
        raise ValueError('bitmap or advance storage budget exceeded')
    end = 0
    for start, stop in sorted(ranges):
        if start < end:
            raise ValueError('bitmap and advance ranges must be disjoint')
        end = stop
    supported = normalized['codec'] == 'mono-row-msb-v1'
    return {'normalized_schema': normalized, 'font_schema_sha256': hashlib.sha256(encoded).hexdigest(),
            'measurement_supported': supported,
            'read_only_reasons': [] if supported else ['Unsupported font codec; no measurements available.']}


def _result():
    return {'schema_version': SCHEMA_VERSION, 'scope': 'native_font_metrics',
            'operation': 'measure', 'tool_version': ROMANCER_VERSION,
            'metrics_version': METRICS_VERSION, 'ok': False, 'status': 'BLOCKED',
            'source_sha256': None, 'source_size': None, 'font_schema_sha256': None,
            'metrics_id': None, 'glyphs': [], 'native_font_usage_verified': False,
            'native_render_verified': False, 'warnings': [], 'error': None}


def _failure(exc, phase, *, held=False):
    cancelled = isinstance(exc, KeyboardInterrupt)
    result = {**_result(), 'status': 'CANCELLED' if cancelled else 'BLOCKED',
              'error': {'phase': phase,
                        'code': 'CANCELLED' if cancelled else getattr(exc, 'code', type(exc).__name__),
                        'message': 'Operation cancelled' if cancelled else str(exc)[:2048]}}
    if held:
        result['source_identity'] = None
    return result


def _identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def _no_links(path):
    if os.name == 'nt':
        drive, root, _ = ntpath.splitroot(os.fspath(path))
        if drive and not root:
            raise FontError('UNSAFE_PATH', 'drive-relative Windows font path is ambiguous')
    path = Path(path).absolute()
    if os.name == 'nt' and (os.path.isreserved(path)
            or str(path).replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\'))):
        raise FontError('UNSAFE_PATH', 'reserved or ambiguous Windows font path')
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise FontError('UNSAFE_PATH', 'linked font path ancestry is not supported')
    return path


def _file_info(info):
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FONT_BYTES:
        raise FontError('SOURCE_BOUNDS', 'font must be an ordinary file of 1..16777216 bytes')
    return info


def _assert_source(path, stream, identity):
    _no_links(path)
    if _identity(path.lstat()) != identity or _identity(os.fstat(stream.fileno())) != identity:
        raise FontError('SOURCE_CHANGED', 'font pathname or held file changed')


def _hash_stream(stream, size):
    stream.seek(0)
    digest = hashlib.sha256()
    remaining = size
    while remaining:
        data = stream.read(min(READ_CHUNK_BYTES, remaining))
        if not data:
            raise FontError('SOURCE_CHANGED', 'font truncated during hashing')
        remaining -= len(data)
        digest.update(data)
    if stream.read(1):
        raise FontError('SOURCE_CHANGED', 'font grew during hashing')
    return digest.hexdigest()


def _read_range(stream, offset, size):
    stream.seek(offset)
    raw = bytearray()
    while len(raw) < size:
        data = stream.read(min(READ_CHUNK_BYTES, size - len(raw)))
        if not data:
            raise FontError('SOURCE_CHANGED', 'font truncated while reading a declared range')
        raw.extend(data)
    return bytes(raw)


def _bounded_result(result):
    canonical_bytes(result, max_bytes=MAX_REPORT_BYTES)
    size = 1  # Reserve the CLI's trailing newline after indented JSON.
    for piece in json.JSONEncoder(sort_keys=True, ensure_ascii=True, allow_nan=False,
                                  indent=2).iterencode(result):
        size += len(piece)
        if size > MAX_REPORT_BYTES:
            raise FontError('REPORT_LIMIT', 'font report exceeds byte budget')
    return result


def _measure(stream, checked, context):
    schema = checked['normalized_schema']
    if not checked['measurement_supported']:
        raise FontError('UNSUPPORTED_CODEC', checked['read_only_reasons'][0])
    context['phase'] = 'source_validation'
    initial = _file_info(os.fstat(stream.fileno()))
    identity = _identity(initial)
    if initial.st_size != schema['source']['size']:
        raise FontError('REVISION_MISMATCH', 'font size does not match descriptor')
    digest = _hash_stream(stream, initial.st_size)
    if digest != schema['source']['sha256']:
        raise FontError('REVISION_MISMATCH', 'font SHA-256 does not match descriptor')
    if _identity(os.fstat(stream.fileno())) != identity:
        raise FontError('SOURCE_CHANGED', 'held font changed during initial hash')
    context['phase'] = 'measurement'
    rows = []
    for glyph in schema['glyphs']:
        bitmap, advance = glyph['bitmap'], glyph['advance']
        raw = _read_range(stream, bitmap['offset'], bitmap['row_stride'] * bitmap['height'])
        measured = measure_bitmap(raw, width=bitmap['width'], height=bitmap['height'],
                                  row_stride=bitmap['row_stride'])
        if advance['kind'] == 'u8':
            field = _read_range(stream, advance['offset'], 1)
            pixels = _integer(field[0], 'measured advance pixels', 0, 128)
            advance_field = {'offset': advance['offset'], 'raw_hex': field.hex()}
            origin, provenance = 'measured_u8', glyph['provenance']
        else:
            pixels, advance_field = advance['pixels'], None
            origin, provenance = 'declared_pixels', advance['provenance']
        rows.append({'id': glyph['id'],
            'bitmap': {**bitmap, 'raw_hex': raw.hex(), 'bitmap_sha256': measured['bitmap_sha256']},
            'ink_bounds': measured['ink_bounds'], 'ink_pixels': measured['ink_pixels'],
            'bearing': glyph['bearing'], 'advance_pixels': pixels, 'advance_origin': origin,
            'advance_field': advance_field,
            'provenance': {'glyph': glyph['provenance'], 'advance': provenance}})
    context['phase'] = 'source_verification'
    if (_hash_stream(stream, initial.st_size) != digest
            or _identity(os.fstat(stream.fileno())) != identity):
        raise FontError('SOURCE_CHANGED', 'font content or identity changed during measurement')
    payload = {'metrics_version': METRICS_VERSION, 'font_schema_sha256': checked['font_schema_sha256'],
               'source_sha256': digest, 'source_size': initial.st_size, 'glyphs': rows}
    context['phase'] = 'result'
    result = {**_result(), **payload, 'ok': True, 'status': 'MEASURED',
              'metrics_id': hashlib.sha256(canonical_bytes(payload, max_bytes=MAX_REPORT_BYTES)).hexdigest(),
              'source_identity': identity,
              'warnings': ['Supplied bitmap measurements and explicit advances do not verify native usage or rendering.']}
    _bounded_result(result)
    if _identity(os.fstat(stream.fileno())) != identity:
        raise FontError('SOURCE_CHANGED', 'held font changed before result completion')
    return result


def measure_font_stream(stream, schema: dict) -> dict:
    """Internal held-file API. Caller owns closure and final pathname cross-checks."""
    context = {'phase': 'validation'}
    try:
        return _measure(stream, validate_font_schema(schema), context)
    except (ValueError, OSError, KeyboardInterrupt) as exc:
        return _failure(exc, context['phase'], held=True)


def measure_font(source: Path, schema: dict) -> dict:
    """Read-only measurement with final path/handle checks for ordinary changes."""
    context = {'phase': 'validation'}
    try:
        checked = validate_font_schema(schema)
        context['phase'] = 'source_validation'
        path = _no_links(source)
        before = _file_info(path.lstat())
        with path.open('rb', buffering=0) as stream:
            _assert_source(path, stream, _identity(before))
            result = _measure(stream, checked, context)
            identity = result.pop('source_identity')
            _bounded_result(result)
            context['phase'] = 'source_verification'
            _assert_source(path, stream, identity)
            return result
    except (ValueError, OSError, KeyboardInterrupt) as exc:
        return _failure(exc, context['phase'])
