import unittest
from romancer.object_workbench import verified_layout,validate_layout


def part(ident,x,y,offset,flip=0,height=8):
    mapping=[]
    for sy in range(height):
        for sx in range(8):
            source=(height-1-sy if flip&2 else sy)*8+(7-sx if flip&1 else sx)
            mapping.append({'source_pixel':source,'screen_pixel':sy*8+sx,'value':1+(source%2),'encoded_bytes':[]})
    return {'match_id':ident,'offset':offset,'length':height*2,'width':8,'height':height,'x':x,'y':y,'codec':'tile8-planar2-msb-v1','pixel_map':mapping,'source_colors':{'1':[255,0,0],'2':[0,255,0]},'complete_placement':True}

class ObjectWorkbenchTests(unittest.TestCase):
    def test_verified_parts_form_whole_object_with_recovered_flips_holes_and_shared_sources(self):
        parts=[part(0,20,30,4096),part(1,36,30,4112,1),part(2,20,38,4096,2)]
        r=verified_layout('nes',parts)
        self.assertEqual(r['config']['offset'],4096);self.assertEqual(r['config']['count'],2)
        self.assertEqual(r['layout']['indices'],[0,None,1,0,None,None]);self.assertEqual(r['layout']['flips'],[0,0,1,2,0,0])
        self.assertEqual(r['scene_region'],{'x':20,'y':30,'width':24,'height':16});self.assertEqual(r['shared_tiles'],[{'cell_index':0,'placements':[0,3]}])
        self.assertEqual(r['layout']['provenance'],'causal_replay');self.assertEqual(validate_layout(r,8192,'nes'),r)
    def test_full_height_flip_reorders_two_nes_tiles_and_keeps_native_colors(self):
        r=verified_layout('nes',[part(0,0,0,1024,3,16)])
        self.assertEqual(r['layout']['indices'],[1,0]);self.assertEqual(r['layout']['flips'],[3,3]);self.assertEqual(r['layout']['colors'][0]['1'],[255,0,0])
    def test_ambiguous_overlap_off_grid_mixed_codec_and_warped_mapping_do_not_authorize_assembly(self):
        for parts in ([part(0,0,0,0),part(1,0,0,16)],[part(0,0,0,0),part(1,9,0,16)],[part(0,0,0,0),{**part(1,8,0,16),'codec':'tile8-packed4-low-v1'}]):
            with self.assertRaises(ValueError):verified_layout('nes',parts)
        p=part(0,0,0,0);p['pixel_map'][4]['source_pixel']=3
        with self.assertRaisesRegex(ValueError,'orientation|mapping'):verified_layout('nes',[p])
    def test_saved_layout_cannot_smuggle_source_bytes_or_invalid_holes_and_ranges(self):
        r=verified_layout('nes',[part(0,0,0,4096)])
        for broken in ({**r,'config':{**r['config'],'offset':9000}},{**r,'layout':{**r['layout'],'indices':[4]}},{**r,'payload':'rom data'}):
            with self.assertRaises(ValueError):validate_layout(broken,8192,'nes')

class ObjectServiceTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from romancer.workbench_api import WorkbenchAPI
        from romancer.workbench_evidence import store_evidence
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()));self.api=WorkbenchAPI(self.root/'work');self.addCleanup(self.api.close)
        demo=self.api.dispatch('project.demo_system',{'system_id':'nes'});self.sp={'project_id':demo['project_id'],'artifact_id':demo['sources'][0]['artifact_id']};self.source=demo['sources'][0]
        self.proofs=[]
        for i,x in enumerate((0,8)):
            m=part(0,x,0,4096+i*16,i)
            m.pop('width');m.pop('codec')  # Actual pre-existing authenticated v2 producer contract.
            report={'scope':'visual_source_v2','source_sha256':self.source['sha256'],'artifact_id':self.source['artifact_id'],'trace_id':'b'*32,'frame':{'sha256':'a'*64,'width':256,'height':240,'index':10},'context':{'core_sha256':'c'*64},'status':'VERIFIED_VISUAL_SOURCE','verified_matches':[m]}
            self.proofs.append(store_evidence(self.api.project(self.sp),'runtime',report)['evidence_id'])
    def test_full_scene_needs_current_authority_and_matching_frame_identity(self):
        from unittest.mock import patch
        import hashlib
        from romancer.visual_checks import _png
        from romancer.workbench_evidence import load_evidence,store_evidence,quarantine_restored_evidence
        rgb=bytes([20,30,40])*256*240;sha=hashlib.sha256(rgb).hexdigest();parts=[]
        for proof in self.proofs:
            report=load_evidence(self.api.project(self.sp),proof,'runtime')['report']
            report={**report,'frame':{**report['frame'],'sha256':sha}}
            parts.append({'verification_id':store_evidence(self.api.project(self.sp),'runtime',report)['evidence_id'],'match_id':0})
        made=self.api.dispatch('objects.create',{**self.sp,'name':'Scene object','parts':parts});self.assertTrue(made['ok'],made)
        params={**self.sp,'object_id':made['object_id'],'edits':[]}
        scene={'width':256,'height':240,'sha256':sha,'png_base64':_png(rgb,256,240)}
        with patch.object(self.api.traces,'get',return_value={'scene':scene,'runtime_trusted':True}):
            result=self.api.dispatch('objects.scene',params);self.assertTrue(result['ok'],result)
            self.assertEqual(result['changed_pixels'],0);self.assertTrue(result['simulated']);self.assertFalse(result['rom_written'])
        with patch.object(self.api.traces,'get',return_value={'scene':{**scene,'sha256':'0'*64}}):
            self.assertFalse(self.api.dispatch('objects.scene',params)['ok'])
        with patch.object(self.api.traces,'get',return_value={}):
            self.assertFalse(self.api.dispatch('objects.scene',params)['ok'])
        with patch.object(self.api.traces,'get',return_value={'scene':scene,'runtime_trusted':False}):
            self.assertFalse(self.api.dispatch('objects.scene',params)['ok'])
        quarantine_restored_evidence(self.api.project(self.sp))
        self.assertFalse(self.api.dispatch('objects.scene',params)['ok'])

    def test_changing_saved_scene_binding_does_not_reuse_an_unrelated_authentic_proof(self):
        from romancer import workbench_projects as projects
        made=self.api.dispatch('objects.create',{**self.sp,'name':'Bound scene','parts':[{'verification_id':self.proofs[0],'match_id':0}]})
        project=self.api.project(self.sp)
        with projects.locked(project) as store:
            obj=store['sources'][0]['object_layouts']['objects'][0];obj['trace_id']='d'*32;obj['frame_sha256']='e'*64
            projects.write_json(project/'project.json',store)
        result=self.api.dispatch('objects.get',{**self.sp,'object_id':made['object_id']})
        self.assertTrue(result['ok']);self.assertFalse(result['source_dependency_verified'])
    def test_create_reopen_delete_and_pack_keep_exact_revision_and_current_authority(self):
        args={**self.sp,'name':'Two-part creature','parts':[{'verification_id':p,'match_id':0} for p in self.proofs]}
        made=self.api.dispatch('objects.create',args);self.assertTrue(made['ok'],made);ident=made['object_id']
        self.assertEqual(made['object']['definition']['layout']['indices'],[0,1])
        opened=self.api.dispatch('objects.open',{**self.sp,'object_id':ident});self.assertTrue(opened['ok'],opened);self.assertTrue(opened['source_dependency_verified']);self.assertEqual(opened['layout']['flips'],[0,1]);self.assertEqual(opened['inspection']['source_sha256'],self.source['sha256'])
        listing=self.api.dispatch('objects.list',self.sp);self.assertEqual([o['name'] for o in listing['objects']],['Two-part creature'])
        from romancer.workbench_evidence import quarantine_restored_evidence
        quarantine_restored_evidence(self.api.project(self.sp))
        historical=self.api.dispatch('objects.open',{**self.sp,'object_id':ident});self.assertTrue(historical['ok'],historical);self.assertFalse(historical['source_dependency_verified']);self.assertEqual(historical['layout']['provenance'],'checked_declaration')
        self.assertTrue(self.api.dispatch('objects.delete',{**self.sp,'object_id':ident})['ok']);self.assertEqual(self.api.dispatch('objects.list',self.sp)['objects'],[])
    def test_research_pack_preserves_objects_but_cannot_export_or_import_runtime_authority(self):
        import json
        made=self.api.dispatch('objects.create',{**self.sp,'name':'Saved creature','parts':[{'verification_id':p,'match_id':0} for p in self.proofs]});self.assertTrue(made['ok'],made)
        result=self.api.dispatch('research.export',self.sp);self.assertTrue(result['ok'],result);file,_=self.api.download(self.sp['project_id'],result['export']['export_id']);document=json.loads(file.read_text())
        self.assertEqual(document['format'],'romancer-research-v2');self.assertEqual(document['objects'][0]['name'],'Saved creature');self.assertEqual(document['objects'][0]['parts'],[]);self.assertIsNone(document['objects'][0]['trace_id'])
        demo=self.api.dispatch('project.demo_system',{'system_id':'nes'});dest={'project_id':demo['project_id'],'artifact_id':demo['sources'][0]['artifact_id']}
        preview=self.api.dispatch('research.preview',{**dest,'document':document});self.assertTrue(preview['ok'],preview);self.assertEqual(preview['object_count'],1)
        applied=self.api.dispatch('research.apply',{**dest,'document':document,'review_id':preview['review_id'],'replace':True});self.assertTrue(applied['ok'],applied)
        opened=self.api.dispatch('objects.open',{**dest,'object_id':document['objects'][0]['id']});self.assertTrue(opened['ok'],opened);self.assertFalse(opened['source_dependency_verified']);self.assertEqual(opened['layout']['provenance'],'checked_declaration')
        document['objects'][0]['parts']=[{'verification_id':self.proofs[0],'match_id':0}]
        bad=self.api.dispatch('research.preview',{**dest,'document':document});self.assertFalse(bad['ok']);self.assertRegex(bad['error'],'proof|historical|reference')

    def test_explicit_conflicting_proof_formats_are_not_normalized_into_authority(self):
        from romancer.workbench_evidence import load_evidence,store_evidence
        for key,value in [('width',4),('codec','tile8-packed4-low-v1')]:
            report=load_evidence(self.api.project(self.sp),self.proofs[0],'runtime')['report']
            report={**report,'verified_matches':[{**report['verified_matches'][0],key:value}]}
            ident=store_evidence(self.api.project(self.sp),'runtime',report)['evidence_id']
            r=self.api.dispatch('objects.create',{**self.sp,'name':'Conflicting format','parts':[{'verification_id':ident,'match_id':0}]})
            self.assertFalse(r['ok']);self.assertRegex(r['error'],'format|codec|width')
    def test_saved_objects_appear_as_connected_editable_resources(self):
        made=self.api.dispatch('objects.create',{**self.sp,'name':'Connected creature','parts':[{'verification_id':p,'match_id':0} for p in self.proofs]})
        result=self.api.dispatch('gameview.graph',{**self.sp,'query':'','kind':'object','page':0})
        self.assertTrue(result['ok'],result);self.assertEqual(result['total'],1)
        node=result['nodes'][0];self.assertEqual(node['locator']['object_id'],made['object_id'])
        detail=self.api.dispatch('gameview.detail',{**self.sp,'node_id':node['id']})
        self.assertTrue(detail['ok'],detail);self.assertEqual(detail['preview']['object_id'],made['object_id'])

    def test_foreign_frame_or_duplicate_placement_is_not_silently_assembled(self):
        bad=self.api.dispatch('objects.create',{**self.sp,'name':'Duplicate','parts':[{'verification_id':self.proofs[0],'match_id':0}]*2});self.assertFalse(bad['ok']);self.assertNotEqual(bad.get('error'),'unknown workbench operation')
        from romancer.workbench_evidence import load_evidence,store_evidence
        report=load_evidence(self.api.project(self.sp),self.proofs[1],'runtime')['report'];report={**report,'frame':{**report['frame'],'sha256':'e'*64}}
        ident=store_evidence(self.api.project(self.sp),'runtime',report)['evidence_id']
        bad=self.api.dispatch('objects.create',{**self.sp,'name':'Foreign frame','parts':[{'verification_id':self.proofs[0],'match_id':0},{'verification_id':ident,'match_id':0}]});self.assertFalse(bad['ok']);self.assertRegex(bad.get('error',''),'frame|capture')

if __name__=='__main__':unittest.main()
