"""Literal synthetic mixed records and pixels; no production encoder or native claims."""

import copy
import hashlib
import json
from pathlib import Path

RGB_A = bytes.fromhex('000000 ff0000 00ff00 0000ff')
RGB_B = bytes.fromhex('000000 ff0000 00ff00 000000')


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('ascii')).hexdigest()


def menu_fixture():
    raw = bytes.fromhex('08001400deadbeef' '414200ffffffffff' '1234' 'a55a'
                        '424100ffffffffff' 'ff00' 'c33c')
    prov = {'origin': 'synthetic_fixture', 'note': 'Explicit toy menu', 'reference': None}
    rules = [
        {'resource': 'pa', 'offset': 0, 'length': 2, 'expected_hex': '0800'},
        {'resource': 'pb', 'offset': 2, 'length': 2, 'expected_hex': '1400'},
        {'resource': 'opaque-head', 'offset': 4, 'length': 4, 'expected_hex': 'deadbeef'},
        {'resource': 'a-slot', 'offset': 8, 'length': 8, 'expected_hex': '414200ffffffffff'},
        {'resource': 'price', 'offset': 16, 'length': 2, 'expected_hex': '1234'},
        {'resource': 'flags', 'offset': 18, 'length': 2, 'expected_hex': 'a55a'},
        {'resource': 'b-slot', 'offset': 20, 'length': 8, 'expected_hex': '424100ffffffffff'},
        {'resource': 'quantity', 'offset': 28, 'length': 2, 'expected_hex': 'ff00'},
        {'resource': 'suffix', 'offset': 30, 'length': 2, 'expected_hex': 'c33c'},
    ]
    annotations = {'label': None, 'speaker_label': None, 'speaker_provenance': None, 'layout_ref': None}
    script = {'schema_version': 1, 'id': 'mixed-menu-names', 'version': '1',
        'artifact': {'kind': 'flat-resource', 'size': 32, 'integrity': 'none'},
        'profile': {'schema_version': 2, 'id': 'mixed-menu-resource', 'version': '1',
                    'system': 'genesis', 'accepted_sha256': [hashlib.sha256(raw).hexdigest()],
                    'rules': rules},
        'format': {'family': 'fixed-slots', 'version': 1,
            'encoding': {'kind': 'single-byte', 'glyphs': [{'byte': 65, 'text': 'A'}, {'byte': 66, 'text': 'B'}]},
            'controls': [], 'terminator': {'byte': 0}, 'padding': {'byte': 255},
            'records': [{'id': 'a', 'rule': 'a-slot', 'annotations': dict(annotations)},
                        {'id': 'b', 'rule': 'b-slot', 'annotations': dict(annotations)}],
            'pointers': [{'id': 'pa', 'rule': 'pa', 'target_record': 'a', 'width': 2, 'endian': 'little', 'base': 0},
                         {'id': 'pb', 'rule': 'pb', 'target_record': 'b', 'width': 2, 'endian': 'little', 'base': 0}],
            'guards': ['opaque-head', 'price', 'flags', 'quantity', 'suffix']}}
    # Literal cells: A has 14 ink pixels; zero has 12. B's 5px ink exceeds its 4px advance.
    glyph_data = [(' ', 'blank', '0000000000', 3), ('$', 'fee-mark', '8080808080', 3)]
    glyph_data += [(str(i), f'digit-{i}', '7088888870', 6) for i in range(10)]
    glyph_data += [('A', 'letter-a', '7088f88888', 6), ('B', 'letter-b', 'f088f088f0', 4)]
    font = b''.join(bytes.fromhex(row[2]) for row in glyph_data) + bytes(row[3] for row in glyph_data)
    font_schema = {'schema_version': 1, 'id': 'mixed-menu-font', 'version': '1',
        'source': {'sha256': hashlib.sha256(font).hexdigest(), 'size': len(font)},
        'codec': 'mono-row-msb-v1', 'provenance': dict(prov), 'glyphs': [
            {'id': row[1], 'bitmap': {'offset': i * 5, 'width': 5, 'height': 5, 'row_stride': 1},
             'bearing': {'x': 0, 'y': 0}, 'advance': {'kind': 'u8', 'offset': len(glyph_data) * 5 + i},
             'provenance': dict(prov)} for i, row in enumerate(glyph_data)]}

    def cell(identifier, kind, x, width, **source):
        return {'id': identifier, 'kind': kind, 'box': {'x': x, 'y': 0, 'width': width, 'height': 5},
                'align': 'right' if kind == 'number' else 'left', 'style': 'plain', **source}

    def state(record, *, fee):
        cells = [cell('name', 'name', 0, 24, record_id=record),
                 cell('price', 'number', 28, 28, field_id='price'),
                 cell('quantity', 'number', 60, 30, field_id='quantity')]
        if fee:
            cells.append(cell('fee', 'number', 94, 32, field_id='fee'))
        return cells

    profile = {'schema_version': 1, 'id': 'mixed-menu', 'version': '1', 'model': 'fixed-menu-v1',
        'script_schema_sha256': digest_json(script), 'viewport': {'width': 128, 'height': 64},
        'row_step_px': 16, 'line_height_px': 5,
        'entries': [
            {'id': 'item', 'kind': 'item', 'states': {'selected': state('b', fee=True),
                'unselected': state('a', fee=True)}, 'provenance': dict(prov)},
            {'id': 'spell', 'kind': 'spell', 'states': {'selected': state('b', fee=False),
                'unselected': state('b', fee=False)}, 'provenance': dict(prov)}],
        'numeric_fields': [
            {'id': 'price', 'source': {'kind': 'resource_guard', 'rule': 'price'},
             'codec': 'packed-bcd', 'width': 2, 'endian': 'big', 'maximum': 9999,
             'format': {'digits': 4, 'pad': 'zero', 'prefix': '', 'suffix': ''},
             'role': 'value', 'provenance': dict(prov)},
            {'id': 'quantity', 'source': {'kind': 'resource_guard', 'rule': 'quantity'},
             'codec': 'uint', 'width': 2, 'endian': 'little', 'maximum': 65535,
             'format': {'digits': 5, 'pad': 'none', 'prefix': '', 'suffix': ''},
             'role': 'value', 'provenance': dict(prov)},
            {'id': 'fee', 'source': {'kind': 'case_bytes'}, 'codec': 'ascii-decimal',
             'width': 4, 'endian': None, 'maximum': 9999,
             'format': {'digits': 4, 'pad': 'zero', 'prefix': '$', 'suffix': ''},
             'role': 'fee_preview', 'provenance': dict(prov)}],
        'empty': cell('empty-message', 'literal', 0, 24, text=''),
        'glyph_map': [{'scalar': row[0], 'glyph_id': row[1], 'provenance': dict(prov)} for row in glyph_data],
        'provenance': dict(prov)}
    cases = {'schema_version': 1, 'profile_sha256': digest_json(profile), 'cases': [
        {'id': 'selected', 'entries': ['item', 'spell'], 'selected_entry': 'item',
         'dynamic_values': [{'field_id': 'fee', 'raw_hex': '30303132'}], 'provenance': dict(prov)},
        {'id': 'unselected', 'entries': ['item'], 'selected_entry': None,
         'dynamic_values': [{'field_id': 'fee', 'raw_hex': '30303030'}], 'provenance': dict(prov)},
        {'id': 'empty', 'entries': [], 'selected_entry': None,
         'dynamic_values': [], 'provenance': dict(prov)}]}
    return copy.deepcopy({'raw': raw, 'script_schema': script, 'profile': profile,
                          'cases': cases, 'font': font, 'font_schema': font_schema})


def write_menu_fixture(root, fixture=None):
    """Write only caller-owned synthetic test files; return paths by service argument."""
    fixture = menu_fixture() if fixture is None else fixture
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, value in (('source', fixture['raw']), ('font', fixture['font'])):
        paths[name] = root / (name + '.bin')
        paths[name].write_bytes(value)
    for name in ('script_schema', 'profile', 'cases', 'font_schema'):
        paths[name] = root / (name + '.json')
        paths[name].write_text(json.dumps(fixture[name], sort_keys=True, ensure_ascii=True), encoding='utf-8')
    return paths


def capture_selector(capture_id, build_id, png_sha256, rgb_sha256, *, source_role=None, font_role=None):
    """Request syntax only, not a capture record or evidence of native origin."""
    result = dict(capture_id=capture_id, build_id=build_id, png_sha256=png_sha256, rgb_sha256=rgb_sha256)
    if source_role is not None or font_role is not None:
        result.update(source_role=source_role, font_role=font_role)
    return result


def comparison_fixture(*, expected_preview_id='e' * 64):
    return {'schema_version': 1, 'expected_preview_id': expected_preview_id, 'pairs': [
        {'id': 'same-region', 'case_id': 'selected',
         'target': capture_selector('1' * 32, 'a' * 64, 'b' * 64, 'c' * 64,
                                    source_role='menu', font_role='font'),
         'reference': capture_selector('2' * 32, 'd' * 64, 'b' * 64, 'c' * 64),
         'region': [0, 0, 2, 2], 'relation': 'equal',
         'provenance': {'origin': 'synthetic_fixture', 'note': 'Request syntax, not native evidence',
                        'reference': None}}]}
