"""Menu-owned scalar placement over fresh, script-independent font measurements."""

from contextlib import contextmanager
import hashlib
import json
import ntpath
import os
from pathlib import Path
import stat

from . import font_metrics
from .script_schema import canonical_bytes

MAX_JSON = 1024 * 1024
MAX_PLACEMENTS = 2048


class MenuError(ValueError):
    def __init__(self, code, message, *, phase='validation', status='BLOCKED'):
        super().__init__(message)
        self.code, self.phase, self.status = code, phase, status


def _digest(value):
    return hashlib.sha256(canonical_bytes(value, max_bytes=MAX_JSON)).hexdigest()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _no_links(path):
    if os.name == 'nt' and (os.path.isreserved(path)
            or str(path).replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\'))):
        raise MenuError('UNSAFE_PATH', 'reserved or ambiguous source path')
    for entry in (path, *path.parents):
        if entry.is_symlink() or entry.is_junction():
            raise MenuError('UNSAFE_PATH', 'linked source ancestry is unsupported')


class _HeldFile:
    def __init__(self, path, stream, identity):
        self.path, self.stream, self.identity = path, stream, identity

    def assert_stable(self):
        _no_links(self.path)
        if (_identity(self.path.lstat()) != self.identity
                or _identity(os.fstat(self.stream.fileno())) != self.identity):
            raise MenuError('SOURCE_CHANGED', 'source pathname or held handle changed', phase='source_verification')


@contextmanager
def _held_file(source, limit):
    if os.name == 'nt':
        drive, root, _ = ntpath.splitroot(os.fspath(source))
        if drive and not root:
            raise MenuError('UNSAFE_PATH', 'drive-relative Windows source path is ambiguous')
    path = Path(source).absolute()
    _no_links(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise MenuError('SOURCE_BOUNDS', 'source must be an ordinary file within its byte limit')
    with path.open('rb', buffering=0) as stream:
        held = _HeldFile(path, stream, _identity(info))
        held.assert_stable()
        yield held
        held.assert_stable()


def _union(rectangles):
    rectangles = [rect for rect in rectangles if rect is not None]
    if not rectangles:
        return None
    return [min(r[0] for r in rectangles), min(r[1] for r in rectangles),
            max(r[2] for r in rectangles), max(r[3] for r in rectangles)]


def _translate(bounds, x, y):
    return None if bounds is None else [bounds[0] + x, bounds[1] + y, bounds[2] + x, bounds[3] + y]


class MenuMetrics:
    """Internal fresh measurement session; callers cannot supply saved metrics."""

    def __init__(self, held, measured, mapping):
        self._held = held
        self.identity = {'font_sha256': measured['source_sha256'], 'font_size': measured['source_size'],
                         'font_schema_sha256': measured['font_schema_sha256'], 'metrics_id': measured['metrics_id']}
        self.glyphs_by_id = {row['id']: row for row in measured['glyphs']}
        self.glyph_map = mapping
        self.glyph_map_sha256 = _digest(mapping)
        self.warnings = measured['warnings']
        self.source_identity = measured['source_identity']
        self.native_font_usage_verified = measured['native_font_usage_verified']
        self.native_render_verified = measured['native_render_verified']
        self._mapping = {row['scalar']: row['glyph_id'] for row in mapping}
        if any(identifier not in self.glyphs_by_id for identifier in self._mapping.values()):
            raise MenuError('MISSING_GLYPH', 'menu mapping names an unmeasured glyph ID', phase='mapping')
        self.placement_count = 0

    def assert_stable(self):
        self._held.assert_stable()

    def measure(self, text):
        if type(text) is not str:
            raise MenuError('TEXT_TYPE', 'display text must be a string')
        if len(text) > MAX_PLACEMENTS - self.placement_count:
            raise MenuError('PLACEMENT_LIMIT', 'menu placement budget exceeded', phase='measurement')
        self.placement_count += len(text)
        placements, x = [], 0
        for index, scalar in enumerate(text):
            identifier = self._mapping.get(scalar)
            if identifier is None:
                raise MenuError('MISSING_GLYPH', 'display scalar has no menu glyph mapping', phase='mapping')
            glyph = self.glyphs_by_id[identifier]
            bounds = _translate(glyph['ink_bounds'], x + glyph['bearing']['x'], glyph['bearing']['y'])
            placements.append({'scalar_index': index, 'scalar': scalar, 'glyph_id': identifier,
                               'x': x, 'y': 0, 'advance_px': glyph['advance_pixels'], 'ink_bounds': bounds})
            x += glyph['advance_pixels']
        return {'advance_px': x, 'ink_bounds': _union([row['ink_bounds'] for row in placements]),
                'placements': placements}


@contextmanager
def open_menu_metrics(font, font_schema, glyph_map):
    checked = font_metrics.validate_font_schema(font_schema)
    mapping = json.loads(canonical_bytes(glyph_map, max_bytes=MAX_JSON))
    if type(mapping) is not list or not 1 <= len(mapping) <= 256:
        raise MenuError('GLYPH_MAP', 'menu mapping must contain 1..256 rows')
    seen = set()
    for row in mapping:
        if (type(row) is not dict or set(row) != {'scalar', 'glyph_id', 'provenance'}
                or type(row['scalar']) is not str or len(row['scalar']) != 1
                or type(row['glyph_id']) is not str or row['scalar'] in seen):
            raise MenuError('GLYPH_MAP', 'invalid or duplicate menu scalar mapping')
        seen.add(row['scalar'])
    mapping.sort(key=lambda row: ord(row['scalar']))
    if not checked['measurement_supported']:
        raise MenuError('UNSUPPORTED_CODEC', 'font codec has no supported measurements', phase='measurement')
    with _held_file(font, 16 * 1024 * 1024) as held:
        measured = font_metrics.measure_font_stream(held.stream, checked['normalized_schema'])
        if measured['ok'] is not True or measured['status'] != 'MEASURED':
            error = measured['error']
            raise MenuError(error['code'], error['message'], phase=error['phase'], status=measured['status'])
        try:
            metrics = MenuMetrics(held, measured, mapping)
            metrics.assert_stable()
            yield metrics
            metrics.assert_stable()
        except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
            exc.menu_context = {'font_sha256': measured['source_sha256'],
                'font_size': measured['source_size'], 'font_schema_sha256': measured['font_schema_sha256'],
                'metrics_id': measured['metrics_id'], **getattr(exc, 'menu_context', {})}
            raise
