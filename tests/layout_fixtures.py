"""Independent literal toy resources, not measurements of a game's font."""

import hashlib
import json


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('ascii')).hexdigest()


def layout_fixture(lines, width_px, *, padding=8):
    prov = {'origin': 'synthetic_fixture', 'note': 'Declared toy model', 'reference': None}
    codes = sorted(set(b' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?,()'))
    cells = [b'\x00' * 5 if c == 32 else b'\x80' * 5 if c in b'!?,()'
             else bytes.fromhex('7088f88888') for c in codes]
    advances = [3 if c in b' !?,()' else 6 for c in codes]
    font = b''.join(cells) + bytes(advances)
    font_schema = {'schema_version': 1, 'id': 'toy-font', 'version': '1',
        'source': {'sha256': hashlib.sha256(font).hexdigest(), 'size': len(font)},
        'codec': 'mono-row-msb-v1', 'provenance': dict(prov), 'glyphs': [
            {'id': f'g{c}', 'bitmap': {'offset': i * 5, 'width': 5,
                'height': 5, 'row_stride': 1}, 'bearing': {'x': 0, 'y': 0},
             'advance': {'kind': 'u8', 'offset': len(codes) * 5 + i},
             'provenance': dict(prov)} for i, c in enumerate(codes)]}
    slot = b'\xe1'.join(lines) + b'\x00' + b'\xff' * padding
    raw = b'\x08\x00GUARD!' + slot + bytes.fromhex('11223344')
    schema = {'schema_version': 1, 'id': 'toy-dialogue', 'version': '1',
        'artifact': {'kind': 'flat-resource', 'size': len(raw), 'integrity': 'none'},
        'profile': {'schema_version': 2, 'id': 'toy-resource', 'version': '1',
            'system': 'genesis', 'accepted_sha256': [hashlib.sha256(raw).hexdigest()],
            'rules': [{'resource': 'ptr', 'offset': 0, 'length': 2, 'expected_hex': '0800'},
                      {'resource': 'guard', 'offset': 2, 'length': 6, 'expected_hex': b'GUARD!'.hex()},
                      {'resource': 'slot', 'offset': 8, 'length': len(slot), 'expected_hex': slot.hex()}]},
        'format': {'family': 'fixed-slots', 'version': 1,
            'encoding': {'kind': 'single-byte', 'glyphs': [{'byte': c, 'text': chr(c)} for c in codes]},
            'controls': [{'id': 'line', 'opcode': 225, 'argument_length': 0,
                          'position_independent': True, 'layout_role': 'line'}],
            'terminator': {'byte': 0}, 'padding': {'byte': 255},
            'records': [{'id': 'a', 'rule': 'slot', 'annotations': {'label': None,
                'speaker_label': None, 'speaker_provenance': None, 'layout_ref': None}}],
            'pointers': [{'id': 'p', 'rule': 'ptr', 'target_record': 'a',
                          'width': 2, 'endian': 'little', 'base': 0}], 'guards': ['guard']}}
    schema_hash = digest_json(schema)
    doc_id = digest_json({'parser_version': 1, 'schema_sha256': schema_hash,
        'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_size': len(raw)})
    policy = {'schema_version': 1, 'id': 'toy-layout', 'version': '1',
        'model': 'explicit-lines-v1', 'document_id': doc_id,
        'script_schema_sha256': schema_hash, 'font_schema_sha256': digest_json(font_schema),
        'glyph_map': [{'byte': c, 'glyph_id': f'g{c}'} for c in codes],
        'boxes': [{'id': 'box', 'width_px': width_px, 'height_px': len(lines) * 5, 'line_height_px': 5}],
        'controls': [{'control_id': 'line', 'arguments_hex': '', 'effect': 'line_reset',
                      'provenance': dict(prov)}],
        'records': [{'record_id': 'a', 'box_id': 'box', 'breaks': [
            {'control_index': i, 'intent': 'soft', 'joiner': ' ', 'provenance': dict(prov)}
            for i in range(len(lines) - 1)]}],
        'quality': {'orphan_max_words': 1, 'orphan_max_percent': 25,
                    'forbid_line_start': ['!', '?', ','], 'forbid_line_end': ['(']},
        'provenance': dict(prov)}
    return raw, font, schema, font_schema, policy
