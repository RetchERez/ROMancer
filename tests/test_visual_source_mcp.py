import unittest
from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS,_investigation_properties

class VisualSourceMCPTests(unittest.TestCase):
    def test_native_draft_preview_is_opt_in_and_saved_preview_reads_are_typed(self):
        self.assertIn('assets.preview_scene',WRITE_OPERATIONS)
        self.assertNotIn('assets.preview_scene',READ_OPERATIONS)
        for operation in ('assets.preview_scene.get','assets.preview_scene.find'):
            self.assertIn(operation,READ_OPERATIONS)
            properties=_investigation_properties(operation);self.assertEqual(properties['edits']['type'],'object');self.assertEqual(properties['trace_id']['maxLength'],32)
    def test_task_and_scene_services_have_bounded_typed_agent_inputs(self):
        self.assertIn('editing.readiness',READ_OPERATIONS);self.assertIn('objects.scene',READ_OPERATIONS)
        p=_investigation_properties('objects.scene');self.assertEqual(p['edits']['maxItems'],64);self.assertEqual(p['edits']['items']['properties']['pixels']['maxItems'],64)
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
