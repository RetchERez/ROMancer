import hashlib,unittest


class StudioDiscoveryTests(unittest.TestCase):
    def test_pointer_values_are_candidates_with_exact_coverage_and_no_write_authority(self):
        from romancer.studio_discovery import scan_structures
        raw=(0x220).to_bytes(4,'big')+bytes(1020)
        result=scan_structures(raw,'genesis',0,1024)
        self.assertEqual(result['candidates'][0]['target_offset'],0x220)
        self.assertEqual(result['candidates'][0]['confidence'],'CANDIDATE')
        self.assertFalse(result['write_authorized']);self.assertFalse(result['dereference_observed'])
        self.assertEqual(result['coverage']['positions_checked'],256)
        self.assertEqual(scan_structures(raw,'nes',0,1024)['candidates'],[])

    def test_declared_level_and_audio_relationships_keep_exact_source_identity(self):
        from romancer.studio_discovery import resource_relationships
        from romancer.studio_examples import make_studio_example
        example=make_studio_example();raw=example['raw'];sha=hashlib.sha256(raw).hexdigest()
        result=resource_relationships(raw,{'levels':example['levels'],'sound':example['sound']},sha)
        self.assertTrue(any(e['relation']=='indexes metatiles' for e in result['edges']))
        self.assertTrue(any(n['offset']==0x3810 for n in result['nodes']))
        self.assertEqual(result['source_sha256'],sha);self.assertFalse(result['game_semantics_verified'])
        with self.assertRaises(ValueError):resource_relationships(raw,{'levels':example['levels']},'0'*64)
