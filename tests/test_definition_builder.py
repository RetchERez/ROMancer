import copy,unittest
from tests.test_debugger_tools import DebuggerAPITests


class BuilderTests(unittest.TestCase):
    setUp=DebuggerAPITests.setUp
    def config(self):
        return {'schema_version':1,'name':'Enemy values','offset':0x1000,'count':4,'stride':4,'fields':[
            {'name':'Health','offset':0,'type':'u16','endian':'little','pointer_base':None},
            {'name':'Damage','offset':2,'type':'u8','endian':'little','pointer_base':None}]}
    def preview(self,kind='tables',config=None):
        return self.api.dispatch('definitions.preview',{**self.params,'kind':kind,'config':config or self.config()})
    def test_preview_decodes_fields_without_saving_then_saves_reviewed_definition(self):
        before=self.api.dispatch('project.open',{'project_id':self.params['project_id']})
        result=self.preview();self.assertTrue(result['ok'],result)
        self.assertEqual(result['inspection']['rows'][0]['cells'][0]['field'],'Health')
        self.assertEqual(result['inspection']['rows'][0]['cells'][1]['offset'],0x1002)
        self.assertEqual(self.api.dispatch('project.open',{'project_id':self.params['project_id']}),before)
        saved=self.api.dispatch('definitions.save',{**self.params,'kind':'tables','config':self.config(),'review_id':result['review_id'],'replace':False})
        self.assertTrue(saved['ok'],saved)
        source=self.api.dispatch('project.open',{'project_id':self.params['project_id']})['sources'][0]
        self.assertEqual(source['descriptors']['tables']['definition']['name'],'Enemy values')
        self.assertEqual(source['sha256'],self.sha)
    def test_old_review_changed_input_and_unacknowledged_replacement_are_refused(self):
        first=self.preview();self.assertTrue(first['ok'],first)
        args={**self.params,'kind':'tables','config':self.config(),'review_id':first['review_id'],'replace':False}
        self.assertTrue(self.api.dispatch('definitions.save',args)['ok'])
        self.assertFalse(self.api.dispatch('definitions.save',{**args,'replace':True})['ok'])
        second=self.preview();self.assertTrue(second['replacements'])
        self.assertFalse(self.api.dispatch('definitions.save',{**args,'review_id':second['review_id']})['ok'])
        changed=self.config();changed['name']='Renamed'
        self.assertFalse(self.api.dispatch('definitions.save',{**args,'config':changed,'review_id':second['review_id'],'replace':True})['ok'])
    def test_field_overlap_bool_and_wrong_system_are_refused(self):
        bad=self.config();bad['fields'][1]['offset']=1
        self.assertFalse(self.preview(config=bad)['ok'])
        bad=self.config();bad['count']=True;self.assertFalse(self.preview(config=bad)['ok'])
        self.assertFalse(self.preview('assets',{'system_id':'gba','offset':0x1000,'count':4})['ok'])
    def test_graphics_preview_uses_real_decoder_and_mcp_shares_services(self):
        result=self.preview('assets',{'system_id':'nes','offset':0x1000,'count':4})
        self.assertTrue(result['ok'],result);self.assertEqual(len(result['inspection']['bitmaps'][0]['cells']),4)
        from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS,_investigation_properties
        self.assertIn('definitions.preview',READ_OPERATIONS);self.assertIn('definitions.save',WRITE_OPERATIONS)
        self.assertEqual(_investigation_properties('definitions.save')['replace']['type'],'boolean')
