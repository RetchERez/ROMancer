"""Declared menu inspection and preview; no transaction or native-render claims."""

from contextlib import contextmanager
import json

from . import ROMANCER_VERSION, font_metrics, script
from .menu_metrics import MenuError, _digest, _held_file, _translate, open_menu_metrics
from .menu_schema import validate_menu_profile, validate_menu_cases
from .script_schema import canonical_bytes, validate_schema

MAX_REPORT = 8 * 1024 * 1024
MAX_CELLS = 1024
IDENTITIES = ('source_sha256', 'source_size', 'schema_sha256', 'document_id',
              'menu_document_id', 'profile_sha256', 'glyph_map_sha256', 'font_sha256',
              'font_size', 'font_schema_sha256', 'metrics_id', 'cases_sha256', 'preview_id')
CAUGHT = (ValueError, OSError, KeyboardInterrupt, RecursionError)


def _result(operation):
    return {'schema_version': 1, 'tool_version': ROMANCER_VERSION, 'menu_version': 1,
            'preview_version': 1, 'scope': 'declared_menu', 'operation': operation,
            **dict.fromkeys(IDENTITIES), 'status': 'BLOCKED', 'ok': False,
            'written': False, 'cancelled': False, 'preview_status': 'NOT_RUN' if operation == 'inspect' else 'BLOCKED',
            'comparison_status': 'NOT_RUN', 'transaction_status': 'NOT_RUN',
            'actual_transaction_verified': False, 'native_render_verified': False,
            'native_font_usage_verified': False, 'state_semantics_verified': False,
            'requested_scope': operation, 'exercised_scope': [], 'warnings': [],
            'read_only_reasons': [], 'diagnostics': [], 'error': None}


def _error(exc):
    cancelled = isinstance(exc, KeyboardInterrupt) or getattr(exc, 'status', None) == 'CANCELLED'
    return {'code': 'CANCELLED' if cancelled else getattr(exc, 'code', type(exc).__name__),
            'phase': getattr(exc, 'phase', 'validation'),
            'message': 'Operation cancelled' if cancelled else str(exc)[:512]}


def _failure(operation, exc, context=None):
    measured = {**(context or {}), **getattr(exc, 'menu_context', {}),
                **getattr(exc, 'script_context', {})}
    result = _result(operation)
    result.update({key: measured[key] for key in IDENTITIES if key in measured})
    result['error'] = _error(exc)
    result['cancelled'] = result['error']['code'] == 'CANCELLED'
    result['status'] = 'CANCELLED' if result['cancelled'] else getattr(exc, 'status', 'BLOCKED')
    if operation == 'preview':
        result['preview_status'] = 'FAIL' if result['status'] == 'FAIL' else 'BLOCKED'
    return result


def _bounded(result):
    try:
        canonical_bytes(result, max_bytes=MAX_REPORT)
        size = 1
        for piece in json.JSONEncoder(sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2).iterencode(result):
            size += len(piece)
            if size > MAX_REPORT:
                raise ValueError('pretty JSON exceeds byte budget')
    except (ValueError, RecursionError) as exc:
        raise MenuError('REPORT_LIMIT', 'menu result exceeds the byte or node budget', phase='report') from exc
    return result


def _status(statuses):
    return 'BLOCKED' if 'BLOCKED' in statuses else 'FAIL' if 'FAIL' in statuses else 'PASS'


def _numeric_row(field, raw=None, offset=None):
    row = {**field, 'offset': offset, 'raw_hex': None if raw is None else raw.hex(),
           'value': None, 'status': 'NOT_RUN', 'diagnostics': []}
    if raw is not None:
        try:
            row['value'] = decode_menu_number(raw, field)
            row['status'] = 'PASS'
        except MenuError as exc:
            row.update(status=exc.status, diagnostics=[_error(exc)])
    return row


@contextmanager
def _inspection_inputs(source, script_schema, profile):
    context = {}
    try:
        schema, checked = _declarations(script_schema, profile)
        normalized = checked['normalized']
        context.update(profile_sha256=checked['sha256'], glyph_map_sha256=checked['glyph_map_sha256'])
        with _held_file(source, 64 * 1024 * 1024) as held:
            document = script.inspect_stream(held.stream, schema)
            context.update({key: document[key] for key in IDENTITIES if key in document})
            context['menu_document_id'] = _digest({'menu_version': 1, 'tool_version': ROMANCER_VERSION,
                'document_id': document['document_id'], 'profile_sha256': checked['sha256']})
            result = {**_result('inspect'), **context, 'script': document,
                      'profile': normalized, 'numeric_fields': [],
                      'read_only_reasons': checked['read_only_reasons']}
            if checked['supported']:
                rules = {row['resource']: row for row in schema['profile']['rules']}
                for field in normalized['numeric_fields']:
                    raw, offset = None, None
                    if field['source']['kind'] == 'resource_guard':
                        rule = rules[field['source']['rule']]
                        offset = rule['offset']
                        held.stream.seek(offset)
                        raw = held.stream.read(field['width'])
                        if raw != bytes.fromhex(rule['expected_hex']):
                            raise MenuError('SOURCE_CHANGED', 'numeric guard changed after inspection', phase='source_verification')
                    result['numeric_fields'].append(_numeric_row(field, raw, offset))
                status = _status([row['status'] for row in result['numeric_fields']])
                result.update(status='INSPECTED' if status == 'PASS' else status, ok=status == 'PASS',
                              exercised_scope=['revision', 'name_spans', 'resource_numeric_fields'])
            else:
                result.update(status='READ_ONLY', ok=True, exercised_scope=['revision', 'raw_script'])
            yield held, result, checked
            held.assert_stable()
    except CAUGHT as exc:
        exc.menu_context = {**context, **getattr(exc, 'menu_context', {})}
        raise


def inspect_menu(source, script_schema: dict, profile: dict) -> dict:
    """Inspect declared spans without writing or asserting preview/engine behavior."""
    context = {}
    try:
        with _inspection_inputs(source, script_schema, profile) as (_, result, _checked):
            context = result
            _bounded(result)
        return result
    except CAUGHT as exc:
        return _bounded(_failure('inspect', exc, context))


def _declarations(script_schema, profile):
    validated = validate_schema(script_schema)
    schema = validated['normalized_schema']
    checked = validate_menu_profile(profile, schema)
    if not validated['write_supported']:
        checked['supported'] = False
        checked['read_only_reasons'] = list(dict.fromkeys(
            checked['read_only_reasons'] + validated['read_only_reasons']))
    return schema, checked


def _name(record):
    if (record['read_only_reasons'] or len(record['segments']) != 1
            or any(token['kind'] not in ('text', 'terminator', 'padding') for token in record['tokens'])):
        raise MenuError('UNSUPPORTED_NAME_CONTROL', 'name must be one complete control-free text segment')
    text = record['segments'][0]['text']
    if len(text) > 128:
        raise MenuError('NAME_LIMIT', 'name exceeds 128 display scalars')
    return text


def _contains(outer, inner):
    return outer[0] <= inner[0] <= inner[2] <= outer[2] and outer[1] <= inner[1] <= inner[3] <= outer[3]


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _render(text, cell, row_y, profile, metrics):
    run = metrics.measure(text)
    box = cell['box']
    x, y = box['x'], box['y'] + row_y
    bounds = [x, y, x + box['width'], y + box['height']]
    viewport = [0, 0, profile['viewport']['width'], profile['viewport']['height']]
    pen_x = x if cell['align'] == 'left' else bounds[2] - run['advance_px']
    placements = [{**row, 'x': row['x'] + pen_x, 'y': y,
                   'ink_bounds': _translate(row['ink_bounds'], pen_x, y)} for row in run['placements']]
    diagnostics = []

    def fail(code, message):
        if not any(row['code'] == code for row in diagnostics):
            diagnostics.append({'code': code, 'phase': 'geometry', 'message': message})

    extent = [pen_x, y, pen_x + run['advance_px'], y + profile['line_height_px']]
    if run['advance_px'] > box['width']:
        fail('ADVANCE_OVERFLOW', 'pen extent exceeds cell width')
    if profile['line_height_px'] > box['height']:
        fail('LINE_HEIGHT_OVERFLOW', 'reserved line height exceeds cell height')
    if not _contains(viewport, bounds) or not _contains(viewport, extent):
        fail('VIEWPORT_OVERFLOW', 'cell or pen/line extent exceeds viewport')
    for placement in placements:
        ink = placement['ink_bounds']
        if ink is not None:
            if not _contains(bounds, ink):
                fail('INK_CLIP', 'glyph ink exceeds its cell')
            if not _contains(viewport, ink):
                fail('VIEWPORT_OVERFLOW', 'glyph ink exceeds viewport')
    return {'text': text, 'advance_px': run['advance_px'], 'pen_origin': [pen_x, y],
            'box_bounds': bounds, 'ink_bounds': _translate(run['ink_bounds'], pen_x, y),
            'placements': placements, 'status': 'FAIL' if diagnostics else 'PASS', 'diagnostics': diagnostics}


def _preview_cases(result, cases, metrics):
    profile = result['profile']
    records = {row['id']: row for row in result['script']['records']}
    fields = {row['id']: row for row in result['numeric_fields']}
    entries = {row['id']: row for row in profile['entries']}
    coverage = {'entries': {key: {'selected': 'NOT_RUN', 'unselected': 'NOT_RUN'} for key in entries},
                'fields': {key: {'zero': 'NOT_RUN', 'maximum': 'NOT_RUN', 'declared_maximum_probe': 'NOT_RUN'} for key in fields},
                'empty_list': 'NOT_RUN'}
    result.update(cases=[], coverage=coverage, glyphs=[])
    count, used = 0, set()

    def covered(previous, current):
        return current if previous == 'NOT_RUN' else _status([previous, current])

    for case in cases['cases']:
        row = {key: case[key] for key in ('id', 'entries', 'selected_entry')}
        row.update(status='PASS', cells=[], diagnostics=[])
        dynamic = {item['field_id']: bytes.fromhex(item['raw_hex']) for item in case['dynamic_values']}
        definitions = []
        for index, entry_id in enumerate(case['entries']):
            state = 'selected' if case['selected_entry'] == entry_id else 'unselected'
            definitions.extend((cell, index * profile['row_step_px'], entry_id, state)
                               for cell in entries[entry_id]['states'][state])
        if not case['entries'] and profile['empty'] is not None:
            definitions.append((profile['empty'], 0, None, 'empty'))
        for cell, row_y, entry_id, state in definitions:
            count += 1
            if count > MAX_CELLS:
                raise MenuError('CELL_LIMIT', 'menu emitted cell budget exceeded')
            output = {**cell, 'case_id': case['id'], 'entry_id': entry_id, 'state': state,
                      'status': 'BLOCKED', 'geometry_status': 'NOT_RUN', 'diagnostics': [],
                      'declared_maximum_probe': None}
            number = None
            try:
                if cell['kind'] == 'name':
                    record = records[cell['record_id']]
                    output['name_span'] = {key: record[key] for key in ('id', 'offset', 'capacity', 'raw_hex', 'used_bytes', 'padding_bytes')}
                    text = _name(record)
                elif cell['kind'] == 'literal':
                    text = cell['text']
                else:
                    field = fields[cell['field_id']]
                    number = (_numeric_row(field, dynamic[field['id']]) if field['source']['kind'] == 'case_bytes' else field)
                    output['numeric'] = number
                    if number['status'] != 'PASS':
                        error = number['diagnostics'][0]
                        raise MenuError(error['code'], error['message'], phase=error['phase'], status=number['status'])
                    text = format_menu_number(number['value'], field)
                output.update(_render(text, cell, row_y, profile, metrics))
                output['geometry_status'] = output['status']
            except MenuError as exc:
                output.update(status=exc.status, diagnostics=[_error(exc)])
            if cell['kind'] == 'number':
                field = fields[cell['field_id']]
                probe = {'value': field['maximum'], 'hypothetical': True}
                try:
                    probe.update(_render(format_menu_number(field['maximum'], field), cell, row_y, profile, metrics))
                except MenuError as exc:
                    probe.update(status=exc.status, diagnostics=[_error(exc)])
                output['declared_maximum_probe'] = probe
                output['status'] = _status([output['status'], probe['status']])
                field_coverage = coverage['fields'][field['id']]
                field_coverage['declared_maximum_probe'] = covered(field_coverage['declared_maximum_probe'], probe['status'])
                if number is not None and number['status'] == 'PASS':
                    for key, value in (('zero', 0), ('maximum', field['maximum'])):
                        if number['value'] == value:
                            field_coverage[key] = covered(field_coverage[key], output['geometry_status'] if output['geometry_status'] != 'NOT_RUN' else output['status'])
            for rendering in (output, output['declared_maximum_probe'] or {}):
                used.update(placement['glyph_id'] for placement in rendering.get('placements', []))
            row['cells'].append(output)
        for index, cell in enumerate(row['cells']):
            a = cell['box']
            # Check declared rectangles even when text measurement was blocked.
            row_y = 0 if cell['entry_id'] is None else case['entries'].index(cell['entry_id']) * profile['row_step_px']
            rect = [a['x'], a['y'] + row_y, a['x'] + a['width'], a['y'] + row_y + a['height']]
            cell['box_bounds'] = rect
            for other in row['cells'][:index]:
                if _overlap(rect, other['box_bounds']):
                    row['diagnostics'].append({'code': 'CELL_OVERLAP', 'phase': 'geometry',
                                               'message': 'declared cells overlap',
                                               'cells': [other['id'], cell['id']]})
        row['status'] = _status([cell['status'] for cell in row['cells']] + (['FAIL'] if row['diagnostics'] else []))
        for entry_id in case['entries']:
            state = 'selected' if case['selected_entry'] == entry_id else 'unselected'
            coverage['entries'][entry_id][state] = covered(coverage['entries'][entry_id][state], row['status'])
        if not case['entries']:
            coverage['empty_list'] = covered(coverage['empty_list'], row['status'])
        result['cases'].append(row)
    result['glyphs'] = [metrics.glyphs_by_id[key] for key in sorted(used)]
    status = _status([row['status'] for row in result['cases']])
    result.update(status=status, preview_status=status, ok=status == 'PASS',
                  exercised_scope=['declared_case_geometry', 'declared_maximum_probes'],
                  placement_count=metrics.placement_count, emitted_cells=count)


@contextmanager
def _preview_inputs(source, script_schema, profile, cases, font_schema, font):
    """Fresh preview held through the consumer; both identities checked before closure."""
    context = {}
    try:
        # Detach every caller-owned declaration before the first source read.
        schema, checked = _declarations(script_schema, profile)
        if not checked['supported']:
            raise MenuError('READ_ONLY', 'unsupported menu or script family has no preview')
        checked_cases = validate_menu_cases(cases, checked['normalized'])
        normalized_font = font_metrics.validate_font_schema(font_schema)['normalized_schema']
        if not checked_cases['normalized']['cases']:
            raise MenuError('NO_CASES', 'preview requires at least one explicit case')
        with _inspection_inputs(source, schema, checked['normalized']) as (held, inspected, _checked):
            context.update({key: inspected[key] for key in IDENTITIES})
            with open_menu_metrics(font, normalized_font, checked['normalized']['glyph_map']) as metrics:
                context.update(metrics.identity, cases_sha256=checked_cases['sha256'])
                context['preview_id'] = _digest({'preview_version': 1, 'tool_version': ROMANCER_VERSION,
                    'menu_document_id': context['menu_document_id'], 'metrics_id': context['metrics_id'],
                    'cases_sha256': context['cases_sha256']})
                result = {**inspected, **_result('preview'), **context,
                          'warnings': metrics.warnings, 'effective_cases': checked_cases['normalized'],
                          'font_source_identity': metrics.source_identity, 'glyph_map': metrics.glyph_map}
                _preview_cases(result, checked_cases['normalized'], metrics)
                _bounded(result)
                yield result
                # The comparator may have decoded ROIs since yield. Neither descriptor
                # is closed until both final pathname/handle checks have completed.
                held.assert_stable()
                metrics.assert_stable()
    except CAUGHT as exc:
        exc.menu_context = {**context, **getattr(exc, 'menu_context', {})}
        raise


def preview_menu(source, script_schema: dict, profile: dict, cases: dict, font_schema: dict, font) -> dict:
    context = {}
    try:
        with _preview_inputs(source, script_schema, profile, cases, font_schema, font) as result:
            context = result
        return result
    except CAUGHT as exc:
        return _bounded(_failure('preview', exc, context))


def decode_menu_number(raw: bytes, field: dict) -> int:
    """Decode a bounded field using its already validated menu definition."""
    if type(raw) is not bytes or len(raw) != field['width']:
        raise MenuError('NUMERIC_ENCODING', 'numeric bytes do not match storage width', status='FAIL')
    codec = field['codec']
    if codec == 'uint':
        value = int.from_bytes(raw, field['endian'], signed=False)
    elif codec == 'packed-bcd':
        value = 0
        for byte in raw:
            high, low = byte >> 4, byte & 15
            if high > 9 or low > 9:
                raise MenuError('NUMERIC_ENCODING', 'packed BCD contains a nondecimal nibble', status='FAIL')
            value = value * 100 + high * 10 + low
    elif codec == 'ascii-decimal':
        if not raw or any(byte < 48 or byte > 57 for byte in raw):
            raise MenuError('NUMERIC_ENCODING', 'ASCII decimal requires only digit bytes', status='FAIL')
        value = int(raw)
    else:
        raise MenuError('NUMERIC_ENCODING', 'unsupported numeric codec')
    if value > field['maximum']:
        raise MenuError('VALUE_RANGE', 'numeric value exceeds the declared maximum', status='FAIL')
    return value


def format_menu_number(value: int, field: dict) -> str:
    """Format exactly, without clamping, truncation or a fee formula."""
    if type(value) is not int or not 0 <= value <= field['maximum']:
        raise MenuError('VALUE_RANGE', 'numeric value is outside the declared range', status='FAIL')
    fmt = field['format']
    text = str(value)
    if len(text) > fmt['digits']:
        raise MenuError('DIGIT_OVERFLOW', 'decimal digits exceed the display budget', status='FAIL')
    if fmt['pad'] != 'none':
        text = text.rjust(fmt['digits'], '0' if fmt['pad'] == 'zero' else ' ')
    return fmt['prefix'] + text + fmt['suffix']
