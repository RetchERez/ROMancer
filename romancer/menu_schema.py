"""Strict declared menu inputs; validation grants no native or transaction evidence."""

import hashlib
import json

from .script_schema import canonical_bytes, validate_schema

SCHEMA_VERSION = 1
MAX_MENU_JSON_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 64
MAX_NUMERIC_FIELDS = 128
MAX_CASES = 32
MAX_GLYPH_MAP = 256
MAX_CELLS_PER_STATE = 8
MAX_VISIBLE_ROWS = 64
MAX_EMITTED_CELLS = 1024
MAX_GLYPH_PLACEMENTS = 2048
MAX_CAPTURE_PAIRS = 16
MAX_UNIQUE_CAPTURES = 32
MAX_ROI_PIXELS = 1048576
MAX_NAME_SCALARS = 128
MAX_LITERAL_SCALARS = 32


def _snapshot(value):
    return json.loads(canonical_bytes(value, max_bytes=MAX_MENU_JSON_BYTES))


def _digest(value):
    return hashlib.sha256(canonical_bytes(value, max_bytes=MAX_MENU_JSON_BYTES)).hexdigest()


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError('unexpected or missing menu fields')


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} is outside the supported integer range')
    return value


def _text(value, label, limit=128, *, empty=False):
    if (type(value) is not str or len(value) > limit or (not empty and not value.strip())
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
        raise ValueError(f'{label} requires bounded text without controls')
    return value


def _hash(value, label, length=64):
    if (type(value) is not str or len(value) != length
            or any(c not in '0123456789abcdef' for c in value)):
        raise ValueError(f'{label} requires {length} lowercase hex characters')
    return value


def _list(value, label, maximum, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError(f'{label} exceeds its item bounds')
    return value


def _provenance(value):
    _fields(value, ('origin', 'note', 'reference'))
    if value['origin'] not in ('profile_assertion', 'synthetic_fixture'):
        raise ValueError('unsupported menu provenance origin')
    _text(value['note'], 'provenance note', 512)
    if value['reference'] is not None:
        _text(value['reference'], 'provenance reference', 256)


def _unique_label(value, seen, label):
    value = _text(value, label)
    if value in seen:
        raise ValueError(f'duplicate {label}')
    seen.add(value)
    return value


def _glyph_map(rows):
    seen = set()
    for row in _list(rows, 'glyph map', MAX_GLYPH_MAP, 1):
        _fields(row, ('scalar', 'glyph_id', 'provenance'))
        scalar = _text(row['scalar'], 'mapped scalar', 1, empty=True)
        # Space is an explicit printable scalar, not a nonblank label.
        if len(scalar) != 1 or scalar in seen:
            raise ValueError('mapped scalars must be unique single scalars')
        seen.add(scalar)
        _text(row['glyph_id'], 'glyph ID')
        _provenance(row['provenance'])
    rows.sort(key=lambda row: ord(row['scalar']))


def _numeric(field, claimed_guards):
    _fields(field, ('id', 'source', 'codec', 'width', 'endian', 'maximum', 'format', 'role', 'provenance'))
    _text(field['id'], 'field ID')
    _provenance(field['provenance'])
    if field['role'] not in ('value', 'fee_preview'):
        raise ValueError('unsupported numeric role')
    source = field['source']
    if type(source) is not dict:
        raise ValueError('numeric source must be a tagged object')
    if source.get('kind') == 'resource_guard':
        _fields(source, ('kind', 'rule'))
        _unique_label(source['rule'], claimed_guards, 'numeric guard rule')
    elif source.get('kind') == 'case_bytes':
        _fields(source, ('kind',))
    else:
        raise ValueError('unsupported numeric source kind')
    codec = field['codec']
    if codec == 'uint':
        width = _integer(field['width'], 'uint width', 1, 4)
        if field['endian'] not in ('little', 'big'):
            raise ValueError('uint endian must be little or big')
        maximum = (1 << (8 * width)) - 1
    elif codec == 'packed-bcd':
        width = _integer(field['width'], 'BCD width', 1, 4)
        if field['endian'] != 'big':
            raise ValueError('packed BCD requires big endian')
        maximum = 10 ** (2 * width) - 1
    elif codec == 'ascii-decimal':
        width = _integer(field['width'], 'ASCII decimal width', 1, 10)
        if field['endian'] is not None:
            raise ValueError('ASCII decimal endian must be null')
        maximum = 10 ** width - 1
    else:
        raise ValueError('unsupported numeric codec')
    _integer(field['maximum'], 'numeric maximum', 0, min(maximum, 9999999999))
    format_spec = field['format']
    _fields(format_spec, ('digits', 'pad', 'prefix', 'suffix'))
    _integer(format_spec['digits'], 'display digits', 1, 10)
    if format_spec['pad'] not in ('none', 'space', 'zero'):
        raise ValueError('unsupported numeric padding')
    for part in ('prefix', 'suffix'):
        _text(format_spec[part], part, MAX_LITERAL_SCALARS, empty=True)


def _cell(cell, viewport, field_ids, *, empty=False):
    if type(cell) is not dict:
        raise ValueError('cell must be a tagged object')
    common = ('id', 'kind', 'box', 'align', 'style')
    kind = cell.get('kind')
    if kind == 'name':
        _fields(cell, (*common, 'record_id'))
        _text(cell['record_id'], 'name record ID')
    elif kind == 'number' and not empty:
        _fields(cell, (*common, 'field_id'))
        if _text(cell['field_id'], 'number field ID') not in field_ids:
            raise ValueError('number cell refers to an undeclared field')
    elif kind == 'literal':
        _fields(cell, (*common, 'text'))
        _text(cell['text'], 'literal text', MAX_LITERAL_SCALARS, empty=True)
    else:
        raise ValueError('unsupported cell kind')
    _text(cell['id'], 'cell ID')
    _text(cell['style'], 'cell style')
    if cell['align'] not in ('left', 'right'):
        raise ValueError('cell alignment must be left or right')
    box = cell['box']
    _fields(box, ('x', 'y', 'width', 'height'))
    for axis, dimension in (('x', 'width'), ('y', 'height')):
        _integer(box[axis], 'box ' + axis, 0, viewport[dimension])
        _integer(box[dimension], 'box ' + dimension, 1, 1024)
        if box[dimension] > viewport[dimension] - box[axis]:
            raise ValueError('cell rectangle extends outside viewport')


def _cells(cells, viewport, field_ids):
    identifiers, used_fields = set(), set()
    names, boxes = 0, []
    for cell in _list(cells, 'state cells', MAX_CELLS_PER_STATE, 1):
        _cell(cell, viewport, field_ids)
        _unique_label(cell['id'], identifiers, 'cell ID')
        names += cell['kind'] == 'name'
        if cell['kind'] == 'number':
            _unique_label(cell['field_id'], used_fields, 'numeric field within state')
        box = cell['box']
        for other in boxes:
            if (box['x'] < other['x'] + other['width'] and other['x'] < box['x'] + box['width']
                    and box['y'] < other['y'] + other['height'] and other['y'] < box['y'] + box['height']):
                raise ValueError('cell rectangles overlap within state')
        boxes.append(box)
    if names != 1:
        raise ValueError('each state requires exactly one name cell')


def _profile(profile):
    normalized = _snapshot(profile)
    _fields(normalized, ('schema_version', 'id', 'version', 'model', 'script_schema_sha256',
                        'viewport', 'row_step_px', 'line_height_px', 'entries', 'numeric_fields',
                        'empty', 'glyph_map', 'provenance'))
    _integer(normalized['schema_version'], 'schema_version', SCHEMA_VERSION, SCHEMA_VERSION)
    for name in ('id', 'version', 'model'):
        _text(normalized[name], name)
    _hash(normalized['script_schema_sha256'], 'script schema hash')
    _provenance(normalized['provenance'])
    viewport = normalized['viewport']
    _fields(viewport, ('width', 'height'))
    for dimension in ('width', 'height'):
        _integer(viewport[dimension], 'viewport ' + dimension, 1, 1024)
    _integer(normalized['row_step_px'], 'row step', 1, 1024)
    _integer(normalized['line_height_px'], 'line height', 1, 64)
    _glyph_map(normalized['glyph_map'])
    entries = _list(normalized['entries'], 'entries', MAX_ENTRIES)
    fields = _list(normalized['numeric_fields'], 'numeric fields', MAX_NUMERIC_FIELDS)
    if normalized['model'] != 'fixed-menu-v1':
        return normalized
    field_ids, guards = set(), set()
    for field in fields:
        _numeric(field, guards)
        _unique_label(field['id'], field_ids, 'numeric field ID')
    entry_ids = set()
    for entry in entries:
        _fields(entry, ('id', 'kind', 'states', 'provenance'))
        _unique_label(entry['id'], entry_ids, 'entry ID')
        if entry['kind'] not in ('item', 'spell', 'other'):
            raise ValueError('unsupported entry kind')
        _provenance(entry['provenance'])
        _fields(entry['states'], ('selected', 'unselected'))
        for cells in entry['states'].values():
            _cells(cells, viewport, field_ids)
    if normalized['empty'] is not None:
        _cell(normalized['empty'], viewport, field_ids, empty=True)
    return normalized


def validate_menu_profile(profile: dict, script_schema: dict) -> dict:
    """Bind strict menu declarations to a validated v37 schema, without reading a font."""
    normalized = _profile(profile)
    checked = validate_schema(script_schema)
    if normalized['script_schema_sha256'] != checked['schema_sha256']:
        raise ValueError('menu profile is bound to a different script schema')
    script = checked['normalized_schema']
    format_spec = script['format']
    reasons = []
    if normalized['model'] != 'fixed-menu-v1':
        reasons.append('Unsupported menu model; menu data remains uninterpreted.')
    if script['artifact']['kind'] != 'flat-resource' or script['artifact']['integrity'] != 'none':
        reasons.append('Menu inspection requires a standalone flat resource without integrity obligations.')
    if format_spec['family'] != 'fixed-slots' or format_spec['version'] != 1:
        reasons.append('Menu inspection requires the supported v37 fixed-slot family.')
    if (normalized['model'] == 'fixed-menu-v1'
            and format_spec['family'] == 'fixed-slots' and format_spec['version'] == 1):
        records = {record['id'] for record in format_spec['records']}
        rules = {rule['resource']: rule for rule in script['profile']['rules']}
        guards = set(format_spec['guards'])
        for field in normalized['numeric_fields']:
            if field['source']['kind'] == 'resource_guard':
                rule = field['source']['rule']
                if rule not in guards or rules[rule]['length'] != field['width']:
                    raise ValueError('numeric fields must consume complete matching-width v37 guards')
        cells = [cell for entry in normalized['entries'] for state in entry['states'].values() for cell in state]
        if normalized['empty'] is not None:
            cells.append(normalized['empty'])
        for cell in cells:
            if cell['kind'] == 'name' and cell['record_id'] not in records:
                raise ValueError('name cell refers to an undeclared v37 record')
    return {'normalized': normalized, 'sha256': _digest(normalized), 'supported': not reasons,
            'read_only_reasons': reasons, 'glyph_map_sha256': _digest(normalized['glyph_map'])}


def _known_placements(cell, fields):
    if cell['kind'] == 'literal':
        return len(cell['text'])
    if cell['kind'] == 'name':
        return 0  # Source parsing and actual name/placement accounting belong to the service.
    field = fields[cell['field_id']]
    fmt = field['format']
    actual_min = 1 if fmt['pad'] == 'none' else fmt['digits']
    maximum_digits = len(str(field['maximum']))
    probe = maximum_digits if fmt['pad'] == 'none' else max(maximum_digits, fmt['digits'])
    return actual_min + probe + 2 * (len(fmt['prefix']) + len(fmt['suffix']))


def validate_menu_cases(cases: dict, normalized_profile: dict) -> dict:
    """Validate chosen-state byte inputs and preflight known expansion, not pixel fit."""
    profile = _profile(normalized_profile)
    if profile['model'] != 'fixed-menu-v1':
        raise ValueError('cases require a supported menu model')
    normalized = _snapshot(cases)
    _fields(normalized, ('schema_version', 'profile_sha256', 'cases'))
    _integer(normalized['schema_version'], 'schema_version', SCHEMA_VERSION, SCHEMA_VERSION)
    if _hash(normalized['profile_sha256'], 'profile hash') != _digest(profile):
        raise ValueError('cases are bound to a different menu profile')
    entries = {entry['id']: entry for entry in profile['entries']}
    fields = {field['id']: field for field in profile['numeric_fields']}
    case_ids, cell_count, placements = set(), 0, 0
    for case in _list(normalized['cases'], 'cases', MAX_CASES):
        _fields(case, ('id', 'entries', 'selected_entry', 'dynamic_values', 'provenance'))
        _unique_label(case['id'], case_ids, 'case ID')
        _provenance(case['provenance'])
        row_ids, cells = set(), []
        for entry_id in _list(case['entries'], 'visible rows', MAX_VISIBLE_ROWS):
            _unique_label(entry_id, row_ids, 'case entry ID')
            if entry_id not in entries:
                raise ValueError('case refers to an undeclared entry')
            state = 'selected' if entry_id == case['selected_entry'] else 'unselected'
            cells.extend(entries[entry_id]['states'][state])
        if case['selected_entry'] is not None:
            if _text(case['selected_entry'], 'selected entry ID') not in row_ids:
                raise ValueError('selected entry must belong to the case rows')
        if not row_ids and profile['empty'] is not None:
            cells.append(profile['empty'])
        required = {cell['field_id'] for cell in cells if cell['kind'] == 'number'
                    and fields[cell['field_id']]['source']['kind'] == 'case_bytes'}
        supplied = set()
        for value in _list(case['dynamic_values'], 'dynamic values', MAX_NUMERIC_FIELDS):
            _fields(value, ('field_id', 'raw_hex'))
            identifier = _unique_label(value['field_id'], supplied, 'dynamic field ID')
            if identifier not in required:
                raise ValueError('dynamic field is unused, undeclared or a resource override')
            _hash(value['raw_hex'], 'dynamic bytes', fields[identifier]['width'] * 2)
        if supplied != required:
            raise ValueError('missing required dynamic field bytes')
        cell_count += len(cells)
        placements += sum(_known_placements(cell, fields) for cell in cells)
        if cell_count > MAX_EMITTED_CELLS or placements > MAX_GLYPH_PLACEMENTS:
            raise ValueError('case expansion exceeds operation cell or glyph budget')
    return {'normalized': normalized, 'sha256': _digest(normalized)}


def _selector(value, *, target):
    names = ('capture_id', 'build_id', 'png_sha256', 'rgb_sha256')
    _fields(value, (*names, 'source_role', 'font_role') if target else names)
    _hash(value['capture_id'], 'capture ID', 32)
    for name in ('build_id', 'png_sha256', 'rgb_sha256'):
        _hash(value[name], name)
    if target:
        for name in ('source_role', 'font_role'):
            _text(value[name], name)


def validate_menu_comparison(request: dict) -> dict:
    """Validate request syntax/ROI budgets only; stored native evidence is checked later."""
    normalized = _snapshot(request)
    _fields(normalized, ('schema_version', 'expected_preview_id', 'pairs'))
    _integer(normalized['schema_version'], 'schema_version', SCHEMA_VERSION, SCHEMA_VERSION)
    _hash(normalized['expected_preview_id'], 'expected preview ID')
    identifiers, captures, pixels = set(), set(), 0
    for pair in _list(normalized['pairs'], 'capture pairs', MAX_CAPTURE_PAIRS, 1):
        _fields(pair, ('id', 'case_id', 'target', 'reference', 'region', 'relation', 'provenance'))
        _unique_label(pair['id'], identifiers, 'pair ID')
        _text(pair['case_id'], 'case ID')
        _provenance(pair['provenance'])
        if pair['relation'] not in ('equal', 'different'):
            raise ValueError('comparison relation must be equal or different')
        _selector(pair['target'], target=True)
        _selector(pair['reference'], target=False)
        if pair['target']['capture_id'] == pair['reference']['capture_id']:
            raise ValueError('a capture cannot be compared with itself')
        captures.update((pair['target']['capture_id'], pair['reference']['capture_id']))
        region = _list(pair['region'], 'region', 4, 4)
        x, y, width, height = region
        _integer(x, 'region x', 0, 4095)
        _integer(y, 'region y', 0, 4095)
        _integer(width, 'region width', 1, 4096)
        _integer(height, 'region height', 1, 4096)
        if width > 4096 - x or height > 4096 - y:
            raise ValueError('region exceeds maximum supported image dimensions')
        pixels += width * height
        if pixels > MAX_ROI_PIXELS or len(captures) > MAX_UNIQUE_CAPTURES:
            raise ValueError('comparison exceeds capture or aggregate pixel budget')
    return {'normalized': normalized, 'sha256': _digest(normalized)}
