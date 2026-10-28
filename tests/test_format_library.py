import copy,json,unittest,tempfile
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI

class FormatLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory());self.api=WorkbenchAPI(Path(self.temp)/'work');self.addCleanup(self.api.close)
        settings=self.api.dispatch('settings.get',{});self.api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
        studio=self.api.dispatch('project.studio',{});self.p={'project_id':studio['project_id'],'artifact_id':studio['sources'][0]['artifact_id']}
    def create(self,mode='exact'):
        r=self.api.dispatch('formats.create',{**self.p,'name':'Original studio formats','mode':mode,'guards':[] if mode=='exact' else [{'offset':0x100,'length':32}]})
        self.assertTrue(r['ok'],r);return r['document']
    def install(self,document):
        r=self.api.dispatch('formats.install',{'document':document});self.assertTrue(r['ok'],r);return r['pack_id']
    def test_preview_never_mutates_project_and_apply_requires_current_review_and_replacement_ack(self):
        pack=self.create();self.assertNotIn('expected_hex',json.dumps(pack));ident=self.install(pack)
        before=self.api.dispatch('project.open',{'project_id':self.p['project_id']})
        review=self.api.dispatch('formats.preview',{**self.p,'pack_id':ident});self.assertTrue(review['ok'],review);self.assertTrue(review['matched']);self.assertFalse(review['rom_modified'])
        self.assertEqual(self.api.dispatch('project.open',{'project_id':self.p['project_id']}),before)
        args={**self.p,'pack_id':ident,'review_id':review['review_id'],'replace':False,'accept_guarded':False}
        self.assertFalse(self.api.dispatch('formats.apply',args)['ok'])
        self.assertTrue(self.api.dispatch('formats.apply',{**args,'replace':True})['ok'])
        revision=self.api.research._public(self.api.source(self.p)[1])['revision']
        note={'id':None,'title':'Investigation note','offset':0x100,'length':1,'category':'code','text':'Observed separately.','reference':''}
        self.assertTrue(self.api.dispatch('research.note_save',{**self.p,'revision':revision,'note':note})['ok'])
        self.assertFalse(self.api.dispatch('formats.apply',{**args,'replace':True})['ok'],'Changed metadata invalidates the previous review')
    def test_guarded_pack_transfers_only_after_matching_regions_actual_inspection_and_explicit_acceptance(self):
        pack=self.create('guarded');ident=self.install(pack);project,row,path=self.api.source(self.p);raw=path.read_bytes()
        plan=self.api.dispatch('bytes.plan',{**self.p,'edits':[{'offset':0x1d16,'before':raw[0x1d16:0x1d17].hex(),'after':bytes([raw[0x1d16]^1]).hex()}]});built=self.api.dispatch('build.apply',{'project_id':self.p['project_id'],'plan_id':plan['plan_id']});self.assertTrue(built['ok'],built)
        p={**self.p,'artifact_id':built['artifact_id']};review=self.api.dispatch('formats.preview',{**p,'pack_id':ident});self.assertTrue(review['ok'],review);self.assertTrue(review['matched']);self.assertFalse(review['exact_source']);self.assertFalse(review['game_semantics_verified'])
        args={**p,'pack_id':ident,'review_id':review['review_id'],'replace':False,'accept_guarded':False}
        self.assertFalse(self.api.dispatch('formats.apply',args)['ok']);applied=self.api.dispatch('formats.apply',{**args,'accept_guarded':True,'replace':True});self.assertTrue(applied['ok'],applied)
        self.assertEqual(self.api.source(p)[1]['descriptors']['script']['profile']['accepted_sha256'],[built['sha256']])
    def test_changed_guard_or_exact_source_mismatch_does_not_match(self):
        exact=self.install(self.create());guarded=self.install(self.create('guarded'));raw=self.api.source(self.p)[2].read_bytes()
        plan=self.api.dispatch('bytes.plan',{**self.p,'edits':[{'offset':0x100,'before':raw[0x100:0x101].hex(),'after':bytes([raw[0x100]^1]).hex()}]});built=self.api.dispatch('build.apply',{'project_id':self.p['project_id'],'plan_id':plan['plan_id']});p={**self.p,'artifact_id':built['artifact_id']}
        for ident in (exact,guarded):
            r=self.api.dispatch('formats.preview',{**p,'pack_id':ident});self.assertTrue(r['ok'],r);self.assertFalse(r['matched'])
    def test_pack_validation_refuses_executable_fields_missing_guards_and_content_id_tampering(self):
        pack=self.create();bad={**pack,'plugin_code':'anything'};self.assertFalse(self.api.dispatch('formats.install',{'document':bad})['ok'])
        self.assertFalse(self.api.dispatch('formats.create',{**self.p,'name':'No guards','mode':'guarded','guards':[]})['ok'])
        ident=self.install(pack);path=self.api.workspace/'format-library'/(ident+'.json');changed=copy.deepcopy(pack);changed['name']='Changed';path.write_text(json.dumps(changed),encoding='utf-8')
        r=self.api.dispatch('formats.preview',{**self.p,'pack_id':ident});self.assertFalse(r['ok'])
    def test_delete_invalidates_review_and_deep_scan_suggests_without_saving(self):
        ident=self.install(self.create());review=self.api.dispatch('formats.preview',{**self.p,'pack_id':ident})
        scan=self.api.dispatch('rom.scan.run',self.p);self.assertTrue(scan['ok'],scan);self.assertIn(ident,[p['pack_id'] for p in scan['format_library']['matches']]);self.assertFalse(scan['format_library']['applied'])
        self.assertTrue(self.api.dispatch('formats.delete',{'pack_id':ident})['ok']);self.assertFalse(self.api.dispatch('formats.apply',{**self.p,'pack_id':ident,'review_id':review['review_id'],'replace':True,'accept_guarded':False})['ok'])
    def test_cached_format_readiness_expires_when_saved_layouts_change(self):
        from romancer.rom_scan import cached
        self.assertTrue(self.api.dispatch('rom.scan.run',self.p)['ok']);project,row,_=self.api.source(self.p);self.assertIsNotNone(cached(project,row))
        config={'schema_version':1,'name':'Changed values','offset':0x1d16,'count':1,'stride':1,'fields':[{'name':'Health','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
        r=self.api.dispatch('definitions.preview',{**self.p,'kind':'tables','config':config});self.assertTrue(r['ok'],r);self.assertTrue(self.api.dispatch('definitions.save',{**self.p,'kind':'tables','config':config,'review_id':r['review_id'],'replace':True})['ok'])
        project,row,_=self.api.source(self.p);self.assertIsNone(cached(project,row))
    def test_oversized_corrupt_pack_can_still_be_listed_and_removed(self):
        ident=self.install(self.create());path=self.api.workspace/'format-library'/(ident+'.json');path.write_bytes(b'x'*(512*1024+1))
        r=self.api.dispatch('formats.list',{});self.assertTrue(r['ok'],r);self.assertFalse(r['packs'][0]['valid'])
        self.assertTrue(self.api.dispatch('formats.delete',{'pack_id':ident})['ok'])
