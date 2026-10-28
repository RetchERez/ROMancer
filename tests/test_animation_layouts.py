import unittest,tempfile
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI

class AnimationTests(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory());self.api=WorkbenchAPI(Path(self.temp)/'work');self.addCleanup(self.api.close)
        p=self.api.dispatch('project.studio',{});row=self.api.dispatch('project.open',{'project_id':p['project_id']})['sources'][0];self.p={'project_id':p['project_id'],'artifact_id':row['artifact_id']}
        self.schema=row['descriptors']['assets'];self.sha=row['sha256']
        self.doc=self.api.dispatch('assets.inspect',{**self.p,'schema':self.schema});self.bitmap=self.doc['bitmaps'][0]
    def args(self):
        return {**self.p,'name':'Hero walk','bitmap_id':self.bitmap['id'],'document_id':self.doc['document_id'],
            'frames':[{'columns':2,'rows':2,'indices':[0,1,2,3],'flips':[0,0,0,0],'duration':120},{'columns':2,'rows':2,'indices':[4,5,2,3],'flips':[0,0,0,0],'duration':160}]}
    def test_review_save_open_and_research_exchange_preserve_declared_frames(self):
        review=self.api.dispatch('animations.preview',self.args());self.assertTrue(review['ok'],review);self.assertEqual(review['shared_tiles'],[2,3])
        listed=self.api.dispatch('animations.list',self.p);self.assertEqual(listed['animations'],[])
        saved=self.api.dispatch('animations.save',{**self.args(),'review_id':review['review_id']});self.assertTrue(saved['ok'],saved)
        opened=self.api.dispatch('animations.get',{**self.p,'animation_id':saved['animation_id']});self.assertEqual(opened['animation']['frames'][1]['duration'],160);self.assertFalse(opened['game_semantics_verified'])
        graph=self.api.dispatch('gameview.graph',{**self.p,'query':'','kind':'animation','page':0});self.assertTrue(graph['ok'],graph);self.assertEqual(graph['nodes'][0]['name'],'Hero walk')
        export=self.api.dispatch('research.export',self.p);self.assertTrue(export['ok'],export)
        import json
        pack=json.loads((self.api.project(self.p)/'exports'/export['export']['name']).read_text(encoding='utf-8'));self.assertEqual(pack['animations'][0]['name'],'Hero walk')
        second=self.api.dispatch('project.studio',{});q={'project_id':second['project_id'],'artifact_id':self.api.dispatch('project.open',{'project_id':second['project_id']})['sources'][0]['artifact_id']}
        preview=self.api.dispatch('research.preview',{**q,'document':pack});self.assertTrue(preview['ok'],preview)
        applied=self.api.dispatch('research.apply',{**q,'document':pack,'review_id':preview['review_id'],'replace':True});self.assertTrue(applied['ok'],applied)
        self.assertEqual(len(self.api.dispatch('animations.list',q)['animations']),1)
    def test_stale_reviews_bad_tiles_timing_and_missing_layout_are_refused(self):
        args=self.args();review=self.api.dispatch('animations.preview',args);self.assertTrue(review['ok'],review)
        bad=self.args();bad['frames'][0]['indices'][0]=self.bitmap['count'];self.assertFalse(self.api.dispatch('animations.preview',bad)['ok'])
        bad=self.args();bad['frames'][0]['duration']=True;self.assertFalse(self.api.dispatch('animations.preview',bad)['ok'])
        bad=self.args();bad['frames'][0]['flips']=[0];self.assertFalse(self.api.dispatch('animations.preview',bad)['ok'])
        self.assertFalse(self.api.dispatch('animations.save',{**args,'document_id':'0'*64,'review_id':review['review_id']})['ok'])
        self.assertTrue(self.api.dispatch('animations.save',{**args,'review_id':review['review_id']})['ok'])
        self.assertFalse(self.api.dispatch('animations.save',{**args,'name':'Another','review_id':review['review_id']})['ok'])

    def test_saved_layout_reopens_after_tool_version_changes_without_losing_source_checks(self):
        from unittest.mock import patch
        args=self.args();preview=self.api.dispatch('animations.preview',args)
        saved=self.api.dispatch('animations.save',{**args,'review_id':preview['review_id']});self.assertTrue(saved['ok'],saved)
        with patch('romancer.assets.ROMANCER_VERSION','1.0.999'):
            listed=self.api.dispatch('animations.list',self.p);self.assertTrue(listed['ok'],listed)
            opened=self.api.dispatch('animations.get',{**self.p,'animation_id':saved['animation_id']});self.assertTrue(opened['ok'],opened)
            current=self.api.dispatch('assets.inspect',{**self.p,'schema':self.schema})
            self.assertEqual(opened['animation']['document_id'],current['document_id'])
            self.assertEqual(listed['animations'][0]['animation_id'],saved['animation_id'])
            review=self.api.dispatch('definitions.preview',{**self.p,'kind':'tables','config':{'schema_version':1,'name':'Values','offset':0x1000,'count':2,'stride':1,'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]}})
            self.assertTrue(review['ok'],review)
