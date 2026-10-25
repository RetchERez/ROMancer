import importlib
from pathlib import Path
import tempfile
import unittest


class AnalysisTests(unittest.TestCase):
    def test_regression_requires_matching_complete_execution_identity(self):
        import copy
        m=self.module('regression')
        identity={'schema_version':1,'tool_version':'50.0.0.dev1','core_options':{'region':'NTSC'},
                  'game_dependencies':[],'initial_state_sha256':None,'game_save_sha256':None,'system_directory_used':False}
        baseline={'status':'PASS','route_sha256':'1'*64,'context':{'core_sha256':'2'*64,'game_sha256':'3'*64},
                  'execution_identity':identity,'observations':[]}
        self.assertEqual(m.compare_runs(baseline,copy.deepcopy(baseline))['status'],'UNCHANGED')
        for key,value in [('core_options',{'region':'PAL'}),('initial_state_sha256','a'*64),('game_save_sha256','b'*64),
                          ('game_dependencies',[{'relative':'disc.bin','expected_sha256':'c'*64}]),('tool_version','old')]:
            candidate=copy.deepcopy(baseline);candidate['execution_identity'][key]=value
            self.assertEqual(m.compare_runs(baseline,candidate)['status'],'INCONCLUSIVE',key)
        candidate=copy.deepcopy(baseline);candidate.pop('execution_identity')
        self.assertEqual(m.compare_runs(baseline,candidate)['status'],'INCONCLUSIVE')
        candidate=copy.deepcopy(baseline);candidate['context']['game_sha256']='d'*64
        self.assertEqual(m.compare_runs(baseline,candidate)['status'],'UNCHANGED')
        baseline['execution_identity']['system_directory_used']=True
        self.assertEqual(m.compare_runs(baseline,copy.deepcopy(baseline))['status'],'INCONCLUSIVE')

    def module(self,name):
        try:m=importlib.import_module('romancer.'+name)
        except ModuleNotFoundError:m=None
        self.assertIsNotNone(m,name+' service is missing');return m

    def test_battle_range_cost_equipment_and_exhausted_budget(self):
        m=self.module('battle_analysis')
        profile={'schema_version':1,'id':'literal','semantics':'declared-action-cost-v1','actions':[
            {'id':'sword','label':'Sword','min_range':0,'max_range':1,'cost':{},'power':10,'accuracy_per_mille':1000},
            {'id':'bolt','label':'Bolt','min_range':1,'max_range':5,'cost':{'mp':3},'power':20,'accuracy_per_mille':500}]}
        observations=[{'kind':'resources','values':{'mp':3}},{'kind':'range','value':1},{'kind':'equipment','bonuses':{'sword':2}}]
        budget={'retries_used':0,'max_retries':3,'failures_used':0,'max_failures':2}
        result=m.analyze_battle(profile,observations,budget)
        self.assertEqual(result['recommended_action'],'sword')
        observations[1]['value']=4
        self.assertEqual(m.analyze_battle(profile,observations,budget)['recommended_action'],'bolt')
        observations[0]['values']['mp']=2
        self.assertIsNone(m.analyze_battle(profile,observations,budget)['recommended_action'])
        budget['failures_used']=2
        self.assertEqual(m.analyze_battle(profile,observations,budget)['status'],'STOP')
        profile['semantics']='guess-game-rules'
        with self.assertRaises(ValueError):m.analyze_battle(profile,observations,budget)

    def test_coverage_rejects_imported_pass_and_separates_optional_unknown(self):
        m=self.module('coverage')
        from romancer.workbench_projects import create_project
        from romancer.workbench_evidence import store_evidence
        with tempfile.TemporaryDirectory() as temp:
            project=Path(create_project(Path(temp),'coverage')['path'])
            goals={'required':['cross-bridge'],'optional':['find-cache'],'endings':['credits'],'unknown_edges':['north gate']}
            spoof={'status':'PASS','transitions':[{'objective':'credits'}]}
            result=m.build_coverage(project,[spoof],goals)
            self.assertEqual(result['covered'],[]);self.assertEqual(result['untrusted_reports'],1)
            trusted=store_evidence(project,'route',{'status':'PASS','origin':'owned_native_worker',
                'worker_close_acknowledged':True,'worker_exit_code':0,'context':{},'transitions':[
                    {'from':'a','to':'b','objective':'cross-bridge','evidence':'measured_assertions','interpretation':'profile_declared'}]})
            result=m.build_coverage(project,[trusted['evidence_id']],goals)
            self.assertEqual(result['covered'],['cross-bridge']);self.assertEqual(result['endings']['missing'],['credits'])
            self.assertEqual(result['optional']['missing'],['find-cache']);self.assertEqual(result['unknown_edges'],['north gate'])

    def test_regression_localizes_fault_and_cache_invalidates(self):
        m=self.module('regression')
        changes=[{'id':str(i)} for i in range(8)]
        def evaluate(subset):return {'status':'FAIL' if any(x['id']=='5' for x in subset) else 'PASS'}
        result=m.bisect_changes(changes,evaluate,{'max_evaluations':30})
        self.assertEqual(result['failing_subset'],[{'id':'5'}]);self.assertTrue(result['minimal_reproduced'])
        stopped=m.bisect_changes(changes,evaluate,{'max_evaluations':1})
        self.assertEqual(stopped['status'],'INCONCLUSIVE')
        inputs={'source':'0'*64,'profile':'1'*64,'core':'2'*64,'settings':{},'route':'3'*64,'tool':'test-v1'}
        old=m.evidence_cache_key(inputs)
        for key in inputs:
            changed={**inputs,key:({'option':'changed'} if key=='settings' else 'changed')}
            self.assertNotEqual(old,m.evidence_cache_key(changed))
        self.assertEqual(m.compare_runs({'status':'BLOCKED'},{'status':'PASS'})['status'],'INCONCLUSIVE')
