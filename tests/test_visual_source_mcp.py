import unittest
from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS,_investigation_properties

class VisualSourceMCPTests(unittest.TestCase):
    def test_source_proof_requires_explicit_write_and_strict_bounded_parameters(self):
        self.assertIn('traces.verify',WRITE_OPERATIONS);self.assertIn('traces.open_verified',WRITE_OPERATIONS);self.assertIn('traces.verification',READ_OPERATIONS)
        self.assertIn('traces.origin',READ_OPERATIONS)
        p=_investigation_properties('traces.verify');self.assertEqual(p['limit']['maximum'],8);self.assertEqual(p['start']['maximum'],256);self.assertNotIn('steps',p);self.assertNotIn('pixels',p)
        p=_investigation_properties('traces.open_verified');self.assertEqual(p['matches']['maxItems'],1)
        self.assertEqual(_investigation_properties('traces.origin')['match_id']['maximum'],255)

if __name__=='__main__':unittest.main()
