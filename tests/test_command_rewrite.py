import unittest,copy
from tests.test_command_editor import sample

class CommandRewriteTests(unittest.TestCase):
    def run_preview(self,**kw):
        from romancer.command_rewrite import preview_stream
        raw,d=sample();from romancer.command_editor import inspect_commands
        doc=inspect_commands(raw,d,d['source_sha256']);args={'raw':raw,'definition':d,'document_id':doc['document_id'],'script_id':'door','items':[{'opcode':16,'values':{'Health':12}},{'opcode':16,'values':{'Health':5}},{'opcode':255,'values':{}}],'fill_byte':0,'no_interior_references':True,'sha':d['source_sha256']};args.update(kw)
        return preview_stream(**args)
    def test_insert_remove_and_reorder_known_linear_commands_stays_inside_confirmed_allocation(self):
        import importlib.util;self.assertIsNotNone(importlib.util.find_spec('romancer.command_rewrite'))
        r=self.run_preview();self.assertEqual(r['edits'],[{'offset':0,'before':'1008201234ff0000','after':'100c1005ff000000'}]);self.assertEqual(r['used_bytes'],5);self.assertEqual(r['free_bytes'],3);self.assertFalse(r['game_semantics_verified'])
    def test_branch_pointer_unknown_end_rules_and_oversize_cannot_be_reflowed(self):
        from romancer.command_rewrite import preview_stream
        for args in ({'no_interior_references':False},{'fill_byte':255},{'document_id':'0'*64},{'items':[{'opcode':17,'values':{}}]},{'items':[{'opcode':255,'values':{}},{'opcode':16,'values':{'Health':3}}]},{'items':[{'opcode':16,'values':{'Health':3}}]},{'items':[{'opcode':16,'values':{'Health':True}},{'opcode':255,'values':{}}]},{'items':[{'opcode':16,'values':{'Health':3}}]*10+[{'opcode':255,'values':{}}]}):
            with self.subTest(args=args),self.assertRaises(ValueError):self.run_preview(**args)
        for key,value in [('role','branch'),('target_base',0)]:
            raw,d=sample();d=copy.deepcopy(d)
            if key=='role':d['commands'][0]['role']=value
            else:d['commands'][0]['fields'][0]['target_base']=value
            from romancer.command_editor import inspect_commands
            doc=inspect_commands(raw,d,d['source_sha256'])
            with self.assertRaises(ValueError):self.run_preview(definition=d,document_id=doc['document_id'])
    def test_unmodelled_command_bytes_are_never_filled_by_guessing(self):
        raw,d=sample();d=copy.deepcopy(d);d['commands'][1]['fields']=[]
        from romancer.command_editor import inspect_commands
        doc=inspect_commands(raw,d,d['source_sha256'])
        with self.assertRaises(ValueError):self.run_preview(definition=d,document_id=doc['document_id'])
    def test_api_sequence_build_reopens_on_all_seven_systems(self):
        from tests.test_text_growth import TextGrowthTests
        from romancer.command_editor import inspect_commands
        helper=TextGrowthTests();helper.setUp();self.addCleanup(helper.doCleanups)
        for system in ('nes','snes','genesis','sms','gb','gbc'):
            with self.subTest(system=system):
                p,path,raw,_,_,*_=helper.source(system);api=helper.api
                plan=api.dispatch('bytes.plan',{**p,'edits':[{'offset':0x1200,'before':raw[0x1200:0x1208].hex(),'after':'1008201234ff0000'}]});built=api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']});self.assertTrue(built['ok'],built);p['artifact_id']=built['artifact_id']
                _,d=sample();d['source_sha256']=built['sha256'];d['scripts'][0]['offset']=0x1200;doc=api.dispatch('commands.inspect',{**p,'definition':d});self.assertTrue(doc['ok'],doc)
                args={**p,'definition':d,'document_id':doc['document_id'],'script_id':'door','items':[{'opcode':16,'values':{'Health':12}},{'opcode':16,'values':{'Health':5}},{'opcode':255,'values':{}}],'fill_byte':0,'no_interior_references':True}
                r=api.dispatch('commands.rewrite.preview',args);self.assertTrue(r['ok'],r)
                stale=api.dispatch('commands.rewrite.plan',{**args,'fill_byte':255,'review_id':r['review_id']});self.assertFalse(stale['ok'])
                plan=api.dispatch('commands.rewrite.plan',{**args,'review_id':r['review_id']});self.assertTrue(plan['ok'],plan);target=api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']});self.assertTrue(target['ok'],target)
                opened=api.dispatch('commands.rewrite.definition',{**p,'artifact_id':target['artifact_id']});self.assertTrue(opened['ok'],opened);self.assertEqual([c['opcode'] for c in opened['inspection']['scripts'][0]['commands']],[16,16,255]);self.assertEqual(path.read_bytes(),raw)
