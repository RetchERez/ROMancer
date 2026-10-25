import copy
import importlib
import unittest
from debug_fixtures import debug_fixture


class DebugSchemaTests(unittest.TestCase):
    def services(self):
        try:
            schema=importlib.import_module('romancer.debug_schema');trace=importlib.import_module('romancer.debug_trace')
        except ModuleNotFoundError:schema=trace=None
        self.assertIsNotNone(schema,'exact address troubleshooting is missing')
        return schema,trace

    def test_exact_bank_space_and_offset_never_suffix_match(self):
        schema,trace=self.services();fixture=debug_fixture();case=schema.validate_debug_case(fixture['case'])['normalized']
        schema.validate_debug_trace(fixture['trace'],case)
        second=case['probes'][1];self.assertEqual(trace.resolve_probe(second,case)['file_offset'],8)
        self.assertEqual(trace.resolve_probe(case['probes'][2],case)['status'],'UNRESOLVED')
        one={**case,'probes':[case['probes'][0]]}
        self.assertEqual([row['event_id'] for row in trace.select_trace_candidates(fixture['trace'],one)],['bank1'])
        self.assertEqual(trace.resolve_probe(case['probes'][3],case)['memory'],{'region':2,'offset':0,'length':1})

    def test_unknown_fields_overlapping_windows_and_address_overflow_refuse(self):
        schema,_=self.services();fixture=debug_fixture()
        for mutate in [lambda x:x.update(native_verified=True),lambda x:x['windows'][1].update(bank=1),
                       lambda x:x['probes'][0]['address'].update(offset=65536),lambda x:x['probes'][0].update(length=True),
                       lambda x:x['windows'][0].update(file_offset=30),lambda x:x['spaces'][0].update(bank_bits=0)]:
            case=copy.deepcopy(fixture['case']);mutate(case)
            with self.assertRaises(ValueError):schema.validate_debug_case(case)

    def test_trace_cannot_claim_native_writes_or_different_revision(self):
        schema,_=self.services();fixture=debug_fixture();case=schema.validate_debug_case(fixture['case'])['normalized']
        for mutate in [lambda x:x.update(format='raw-log'),lambda x:x['source'].update(sha256='1'*64),
                       lambda x:x['events'][0]['access'].update(kind='observed_write')]:
            value=copy.deepcopy(fixture['trace']);mutate(value)
            with self.assertRaises(ValueError):schema.validate_debug_trace(value,case)
