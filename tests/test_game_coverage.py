"""Coverage evidence is a review input, never imported editing authority."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from romancer import coverage


class GameCoverageTests(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads(coverage.MANIFEST_PATH.read_text(encoding='utf-8'))

    def test_frozen_target_set_preserves_every_catalog_and_showcase_identity(self):
        rows=coverage.validate_manifest(self.manifest)
        self.assertEqual(len(rows),1039)
        self.assertEqual(sum('catalog' in r['origin'] for r in rows),1035)
        self.assertEqual(sum('showcase' in r['origin'] for r in rows),6)
        report=coverage.status(limit=1)
        self.assertEqual(report['target_count'],1039)
        self.assertEqual(report['accepted_count'],0)
        self.assertFalse(report['release_ready'])
        self.assertFalse(report['write_authorized'])
        self.assertEqual(len(report['revisions']),1)

    def test_removed_replaced_or_changed_targets_fail_even_when_count_is_preserved(self):
        for mutate in [lambda d:d['targets'].pop(),
                       lambda d:d['targets'][0].update(sha256='0'*64),
                       lambda d:d['targets'][0].update(size=d['targets'][0]['size']+1),
                       lambda d:d['targets'][0].update(system_id='gb' if d['targets'][0]['system_id']!='gb' else 'nes'),
                       lambda d:d['targets'][0].update(accepted=True),
                       lambda d:d['targets'][0].update(origin=[{}]),
                       lambda d:d['targets'].append(copy.deepcopy(d['targets'][0]))]:
            d=copy.deepcopy(self.manifest);mutate(d)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):coverage.validate_manifest(d)

    def test_bounded_queries_reject_booleans_and_do_not_mutate_the_inventory(self):
        for kwargs in [{'page':True},{'limit':False},{'limit':101},{'page':-1},
                       {'system_filter':'other'},{'query':'x'*129}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):coverage.status(**kwargs)
        row=coverage.status(query='Immortal',system_filter='genesis',limit=10)['revisions']
        self.assertTrue(row)
        self.assertFalse(any(r['full_editing_verified'] for r in row))
        row[0]['labels'].append('changed client copy')
        self.assertNotIn('changed client copy',str(coverage.status(query='Immortal')))

    def packet(self):
        target=coverage.load_manifest()[0]
        context={'romancer_commit':'a'*40,'adapter_sha256':'b'*64}
        inventory={'source_sha256':target['sha256'],'adapter_sha256':'b'*64,
                   'resources':[{'id':'original-fixture-room','operations':['inspect','noop','edit','undo_redo','reopen','native','patch']}],
                   'unresolved':[]}
        candidate={'source_sha256':target['sha256'],**context,'proofs':[
            {'resource_id':'original-fixture-room','operation':op,'source_sha256':target['sha256'],
             'romancer_commit':'a'*40,'adapter_sha256':'b'*64,'evidence_sha256':'c'*64,'result':'pass','origin':'commercial'}
            for op in inventory['resources'][0]['operations']]}
        return target,inventory,context,candidate

    def test_identity_or_pass_flags_cannot_self_certify_full_editing(self):
        target,inventory,context,packet=self.packet()
        result=coverage.assess_evidence(target,inventory,context,packet)
        self.assertTrue(result['ready_for_review'])
        self.assertFalse(result['accepted'])
        self.assertFalse(result['write_authorized'])
        self.assertTrue(result['requires_independent_review'])
        packet['accepted']=True
        with self.assertRaises(ValueError):coverage.assess_evidence(target,inventory,context,packet)

    def test_missing_resource_operations_stale_or_synthetic_proofs_block_review(self):
        changes=[lambda p:p['proofs'].pop(),
                 lambda p:p.update(source_sha256='d'*64),
                 lambda p:p['proofs'][0].update(romancer_commit='d'*40),
                 lambda p:p['proofs'][0].update(adapter_sha256='d'*64),
                 lambda p:p['proofs'][0].update(source_sha256='d'*64),
                 lambda p:p['proofs'][0].update(origin='synthetic'),
                 lambda p:p['proofs'][0].update(result='inconclusive'),
                 lambda p:p['proofs'].append(copy.deepcopy(p['proofs'][0]))]
        for mutate in changes:
            target,inventory,context,packet=self.packet();mutate(packet)
            result=coverage.assess_evidence(target,inventory,context,packet)
            self.assertFalse(result['ready_for_review'],(mutate,result))
            self.assertFalse(result['accepted'])
        target,inventory,context,packet=self.packet();inventory['unresolved']=['unknown consumer']
        self.assertFalse(coverage.assess_evidence(target,inventory,context,packet)['ready_for_review'])

    def test_an_omitted_expected_resource_or_unreviewed_na_is_not_a_pass(self):
        target,inventory,context,packet=self.packet()
        inventory['resources'].append({'id':'unobserved-room','operations':['native']})
        self.assertFalse(coverage.assess_evidence(target,inventory,context,packet)['ready_for_review'])
        packet['proofs'][0]['result']='not_applicable'
        self.assertFalse(coverage.assess_evidence(target,inventory,context,packet)['ready_for_review'])

    def test_read_only_api_and_ai_schema_do_not_turn_catalog_matches_into_support(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.mcp_server import READ_OPERATIONS,_investigation_properties
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'work')
            try:
                r=api.dispatch('coverage.status',{'query':'','system_filter':'all','page':0,'limit':2})
                self.assertTrue(r['ok'],r);self.assertEqual(r['target_count'],1039)
                self.assertFalse(r['release_ready']);self.assertFalse(r['write_authorized'])
                self.assertIn('coverage.status',READ_OPERATIONS)
                self.assertIn('system_filter',_investigation_properties('coverage.status'))
            finally:api.close()

    def test_cli_reports_unmet_gate_without_overwriting_existing_reports(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'coverage.json'
            args=[sys.executable,'-B',str(root/'tools/audit_game_coverage.py'),'--output',str(output)]
            p=subprocess.run(args,cwd=root,capture_output=True,text=True)
            self.assertEqual(p.returncode,1,p.stderr)
            self.assertFalse(json.loads(output.read_text())['release_ready'])
            output.write_bytes(b'preserve existing report')
            p=subprocess.run(args,cwd=root,capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stderr)
            self.assertEqual(output.read_bytes(),b'preserve existing report')
