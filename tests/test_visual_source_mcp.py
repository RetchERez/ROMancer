import unittest
from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS,_investigation_properties

class VisualSourceMCPTests(unittest.TestCase):
    def test_source_proof_requires_explicit_write_and_strict_bounded_parameters(self):
        self.assertIn('traces.verify',WRITE_OPERATIONS);self.assertIn('traces.open_verified',WRITE_OPERATIONS);self.assertIn('traces.verification',READ_OPERATIONS)
        self.assertIn('traces.origin',READ_OPERATIONS)
        p=_investigation_properties('traces.verify');self.assertEqual(p['limit']['maximum'],8);self.assertEqual(p['start']['maximum'],256);self.assertNotIn('steps',p);self.assertNotIn('pixels',p)
        p=_investigation_properties('traces.open_verified');self.assertEqual(p['matches']['maxItems'],1)
        self.assertEqual(_investigation_properties('traces.origin')['match_id']['maximum'],255)

    def test_object_and_native_graphics_tools_keep_typed_arrays_and_read_only_memory(self):
        self.assertIn('objects.create',WRITE_OPERATIONS);self.assertIn('objects.open',WRITE_OPERATIONS);self.assertIn('objects.delete',WRITE_OPERATIONS);self.assertIn('objects.get',READ_OPERATIONS)
        p=_investigation_properties('objects.create');self.assertEqual(p['parts']['type'],'array');self.assertEqual(p['parts']['maxItems'],64);self.assertEqual(p['parts']['items']['properties']['match_id']['maximum'],255)
        self.assertIn('graphics.accesses.capture',WRITE_OPERATIONS);self.assertIn('graphics.accesses.memory',READ_OPERATIONS)
        self.assertIn('compression.preview_reinsert',READ_OPERATIONS);self.assertIn('compression.plan_relocate',WRITE_OPERATIONS);self.assertIn('checks.from_trace',WRITE_OPERATIONS)
        self.assertIn('trace_id',_investigation_properties('checks.from_trace'))
        self.assertIn('spec',_investigation_properties('compression.plan_relocate'))
        self.assertIn('parent_id',_investigation_properties('compression.preview_reinsert'))
        self.assertEqual(_investigation_properties('debugger.capture')['config']['properties']['graphics_snapshot']['type'],'boolean')
        self.assertEqual(_investigation_properties('graphics.accesses.tiles')['count']['maximum'],64)
        p=_investigation_properties('graphics.accesses.memory');self.assertEqual(p['length']['maximum'],4096);self.assertNotIn('data_hex',p)

if __name__=='__main__':unittest.main()
