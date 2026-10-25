"""Hand-authored synthetic script data, independent of production codecs."""
import hashlib


def fixed_fixture():
    raw = (bytes.fromhex('08000014deadbeef')
           + b'A\xf0\x03B\x00' + b'\xff' * 7
           + b'BA\x00' + b'\xff' * 5
           + bytes.fromhex('11223344'))
    rules = [
        {'resource': 'pa', 'offset': 0, 'length': 2, 'expected_hex': '0800'},
        {'resource': 'pb', 'offset': 2, 'length': 2, 'expected_hex': '0014'},
        {'resource': 'guard', 'offset': 4, 'length': 4, 'expected_hex': 'deadbeef'},
        {'resource': 'a-slot', 'offset': 8, 'length': 12,
         'expected_hex': (b'A\xf0\x03B\x00' + b'\xff' * 7).hex()},
        {'resource': 'b-slot', 'offset': 20, 'length': 8,
         'expected_hex': (b'BA\x00' + b'\xff' * 5).hex()},
    ]
    annotations = {'label': None, 'speaker_label': None,
                   'speaker_provenance': None, 'layout_ref': None}
    schema = {
        'schema_version': 1, 'id': 'synthetic-script', 'version': '1',
        'artifact': {'kind': 'flat-resource', 'size': 32, 'integrity': 'none'},
        'profile': {'schema_version': 2, 'id': 'synthetic-resource', 'version': '1',
                    'system': 'genesis',
                    'accepted_sha256': [hashlib.sha256(raw).hexdigest()], 'rules': rules},
        'format': {
            'family': 'fixed-slots', 'version': 1,
            'encoding': {'kind': 'single-byte', 'glyphs': [
                {'byte': 65, 'text': 'A'}, {'byte': 66, 'text': 'B'}]},
            'controls': [{'id': 'pause', 'opcode': 240, 'argument_length': 1,
                          'position_independent': True, 'layout_role': 'pause'}],
            'terminator': {'byte': 0}, 'padding': {'byte': 255},
            'records': [{'id': 'a', 'rule': 'a-slot', 'annotations': dict(annotations)},
                        {'id': 'b', 'rule': 'b-slot', 'annotations': dict(annotations)}],
            'pointers': [
                {'id': 'pa', 'rule': 'pa', 'target_record': 'a',
                 'width': 2, 'endian': 'little', 'base': 0},
                {'id': 'pb', 'rule': 'pb', 'target_record': 'b',
                 'width': 2, 'endian': 'big', 'base': 0}],
            'guards': ['guard'],
        },
    }
    return raw, schema
