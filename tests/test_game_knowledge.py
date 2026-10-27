"""Factual references are revision-bound; research never grants write authority."""
import unittest


class GameKnowledgeTests(unittest.TestCase):
    def test_references_cover_six_exact_profiles_without_bulk_game_data(self):
        from romancer.game_knowledge import reference_knowledge
        from romancer.verified_games import PROFILES
        for profile in PROFILES:
            result=reference_knowledge(profile['id'],profile['sha256'],False)
            self.assertEqual(result['verified_original_sha256'],profile['sha256'])
            self.assertFalse(result['write_authorized'])
            self.assertTrue(result['facts']);self.assertTrue(result['sources'])
            for source in result['sources']:
                if source.get('kind')=='native_observation':
                    self.assertTrue(source['url'].startswith('/user-guide/'));self.assertEqual(len(source['original_frame_sha256']),64);self.assertEqual(len(source['edited_frame_sha256']),64)
                else:
                    self.assertTrue(source['url'].startswith('https://github.com/'));self.assertEqual(len(source['commit']),40)
            for fact in result['facts']:
                self.assertIn(fact['status'],('implemented','layout_checked','research_candidate'))
                self.assertTrue(fact['scope']);self.assertTrue(fact['source_ids'])

    def test_derived_reference_is_not_a_new_runtime_or_layout_certification(self):
        from romancer.game_knowledge import reference_knowledge
        result=reference_knowledge('wario-land4-ue','a'*64,True)
        self.assertTrue(result['selected_is_derived'])
        self.assertFalse(result['selected_layout_revalidated'])
        self.assertFalse(result['gameplay_verified'])
        self.assertIn('original',result['note'])
        self.assertEqual(reference_knowledge('unrecognized','a'*64,False),None)


if __name__=='__main__':unittest.main()
