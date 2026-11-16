from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI


SOURCE='55bcab0d9efc33a9d9efc90f2c3c4ab12f3221a44b1f357e6c6202a456399aa8'


class CorpusEvidenceTests(unittest.TestCase):
    def query(self,api,source=SOURCE,size=131088):
        return api.dispatch('rom.evidence',{'sha256':source,'size':size})

    def test_ai_can_read_exact_source_relations_without_loading_or_modifying_a_rom(self):
        with tempfile.TemporaryDirectory()as directory:
            api=WorkbenchAPI(Path(directory)/'work')
            try:
                result=self.query(api)
                self.assertTrue(result['ok'],result)
                self.assertEqual(result['status'],'RECORDED_SOURCE_EVIDENCE')
                self.assertEqual(result['source_sha256'],SOURCE)
                self.assertEqual(result['record']['size'],131088)
                self.assertGreater(result['related_total'],0)
                self.assertTrue(any(r['shared_file_bytes']>=128 for r in result['record']['related']))
                self.assertFalse(result['write_authorized'])
                self.assertFalse(result['full_editing_verified'])
                self.assertEqual(result['source_count'],1052)
                self.assertEqual(list(api.projects.iterdir()),[])
            finally:api.close()

    def test_source_size_binding_unknown_hash_and_boolean_rejection(self):
        with tempfile.TemporaryDirectory()as directory:
            api=WorkbenchAPI(Path(directory)/'work')
            try:
                self.assertTrue(self.query(api)['ok'])
                self.assertFalse(self.query(api,size=131089)['ok'])
                self.assertFalse(self.query(api,size=True)['ok'])
                self.assertFalse(self.query(api,source=True)['ok'])
                unknown=self.query(api,source='f'*64,size=64)
                self.assertTrue(unknown['ok'],unknown)
                self.assertEqual(unknown['status'],'NO_RECORDED_SOURCE_EVIDENCE')
                self.assertIsNone(unknown['record'])
                self.assertFalse(unknown['write_authorized'])
            finally:api.close()

    def test_client_mutation_cannot_change_later_evidence_or_mcp_read_only_policy(self):
        from romancer.mcp_server import READ_OPERATIONS,_investigation_properties
        with tempfile.TemporaryDirectory()as directory:
            api=WorkbenchAPI(Path(directory)/'work')
            try:
                packet=self.query(api);self.assertTrue(packet['ok'],packet)
                packet['record']['label']='changed client copy'
                packet['record']['related'].clear()
                again=self.query(api)
                self.assertNotEqual(again['record']['label'],'changed client copy')
                self.assertGreater(len(again['record']['related']),0)
                self.assertIn('rom.evidence',READ_OPERATIONS)
                properties=_investigation_properties('rom.evidence')
                self.assertEqual(properties['size']['type'],'integer')
                self.assertIn('pattern',properties['sha256'])
            finally:api.close()

    def test_altered_database_fails_closed_and_preserves_real_source_scope(self):
        from romancer import corpus_evidence as evidence
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'altered.json'
            path.write_bytes(evidence.DATABASE_PATH.read_bytes()+b' ')
            with patch.object(evidence,'DATABASE_PATH',path):
                with self.assertRaisesRegex(ValueError,'changed'):evidence.lookup(SOURCE,131088)
        packet=evidence.lookup(SOURCE,131088)
        self.assertTrue(all(r['scope']=='prg_chr' for r in packet['record']['references']))
        self.assertFalse(packet['full_editing_verified'])
        self.assertEqual(packet['source_count'],1052)

    def test_deep_scan_cache_changes_when_corpus_database_changes(self):
        from romancer import corpus_evidence as evidence,rom_scan
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'corpus.json';path.write_bytes(evidence.DATABASE_PATH.read_bytes())
            with patch.object(evidence,'DATABASE_PATH',path):
                before=rom_scan.fingerprint(directory)
                path.write_bytes(path.read_bytes()+b' ')
                self.assertNotEqual(before,rom_scan.fingerprint(directory))
