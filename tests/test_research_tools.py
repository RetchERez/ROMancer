import copy
import json
from pathlib import Path
import tempfile
import unittest
from romancer.boot_fixtures import make_boot_fixture
from romancer.workbench_api import WorkbenchAPI


class ResearchToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.raw=make_boot_fixture('nes')['data']
        self.input=self.root/'original.nes';self.input.write_bytes(self.raw)
        self.api=WorkbenchAPI(self.root/'work');self.addCleanup(self.api.close)
        self.p={'project_id':self.call('project.create',name='Research')['project_id']}
        self.source=self.call('source.import',**self.p,path=str(self.input),system=None)
        self.sp={**self.p,'artifact_id':self.source['artifact_id']}

    def call(self,op,**params):
        result=self.api.dispatch(op,params);self.assertTrue(result.get('ok'),result);return result

    def note(self,**changes):
        return {'id':None,'title':'Enemy graphics','offset':4096,'length':32,'category':'graphics',
                'text':'Observed during the opening. Not a collision definition.','reference':'Private frame comparison',**changes}

    def save(self,**changes):
        old=self.call('research.inspect',**self.sp,query='',kind='all',page=0)
        return self.call('research.note_save',**self.sp,revision=old['revision'],note=self.note(**changes))

    def declare(self):
        return self.call('resources.declare_assets',**self.sp,config={'system_id':'nes','offset':4096,'count':4})

    def document(self):
        self.declare();self.save()
        result=self.call('research.export',**self.sp)
        path,_=self.api.download(self.p['project_id'],result['export']['export_id'])
        doc=json.loads(path.read_text());self.assertNotIn('path',doc['source'])
        return doc

    def test_persistent_range_notes_are_user_research_and_do_not_modify_rom(self):
        saved=self.save();self.assertEqual(len(saved['notes']),1);ident=saved['notes'][0]['id']
        self.assertFalse(saved['game_semantics_verified'])
        self.api.close();self.api=WorkbenchAPI(self.root/'work');self.addCleanup(self.api.close)
        found=self.call('research.inspect',**self.sp,query='opening',kind='notes',page=0)
        self.assertEqual(found['notes'][0]['id'],ident);self.assertEqual(self.input.read_bytes(),self.raw)
        self.assertEqual(Path(self.source['path']).read_bytes(),self.raw)
        explained=self.call('resources.explain',**self.sp,offset=4097)
        self.assertEqual(explained['research_notes'][0]['id'],ident)
        self.assertFalse(explained['write_authorized'])

    def test_bad_note_ranges_controls_and_duplicate_titles_do_not_silently_overwrite(self):
        self.save()
        for changes in ({'length':0},{'offset':len(self.raw)},{'length':len(self.raw)},{'text':'bad\x00text'},{'category':'verified'}):
            current=self.call('research.inspect',**self.sp,query='',kind='all',page=0)
            result=self.api.dispatch('research.note_save',{**self.sp,'revision':current['revision'],'note':self.note(**changes)})
            self.assertFalse(result['ok'],changes)
        self.save(title='Enemy graphics',offset=8192)
        found=self.call('research.inspect',**self.sp,query='',kind='notes',page=0)
        self.assertEqual(len(found['notes']),2)

    def test_revision_conflict_and_note_deletion_preserve_other_notes(self):
        empty=self.call('research.inspect',**self.sp,query='',kind='all',page=0);a=self.save()
        stale=self.api.dispatch('research.note_save',{**self.sp,'revision':empty['revision'],'note':self.note(title='stale')})
        self.assertFalse(stale['ok'])
        b=self.save(title='Second',offset=8192)
        deleted=self.call('research.note_delete',**self.sp,revision=b['revision'],note_id=a['notes'][0]['id'])
        self.assertEqual([n['title'] for n in deleted['notes']],['Second'])

    def test_compact_active_resource_browser_rechecks_definitions(self):
        self.declare()
        result=self.call('research.inspect',**self.sp,query='tiles',kind='assets',page=0)
        self.assertEqual(len(result['resources']),1)
        self.assertEqual(result['resources'][0]['length'],64)
        self.assertEqual(result['resources'][0]['offset'],4096)
        self.assertEqual(result['resources'][0]['editor'],'assets')
        from romancer import workbench_projects as p
        project=self.api.project(self.p)
        with p.locked(project) as value:
            value['sources'][0]['descriptors']['assets']['source']['sha256']='0'*64
            p.write_json(project/'project.json',value)
        bad=self.call('research.inspect',**self.sp,query='',kind='all',page=0)
        self.assertEqual(bad['resources'],[]);self.assertTrue(bad['issues'])

    def test_pack_preview_is_read_only_and_import_is_exact_revision_bound(self):
        doc=self.document();p2=self.call('project.create',name='Other')
        s2=self.call('source.import',project_id=p2['project_id'],path=str(self.input),system=None)
        dest={'project_id':p2['project_id'],'artifact_id':s2['artifact_id']}
        review=self.call('research.preview',**dest,document=doc)
        self.assertEqual(review['definitions'],['assets'])
        before=self.call('research.inspect',**dest,query='',kind='all',page=0)
        self.assertEqual(before['resources'],[]);self.assertEqual(before['notes'],[])
        applied=self.call('research.apply',**dest,document=doc,review_id=review['review_id'],replace=False)
        self.assertEqual(len(applied['notes']),1)
        self.assertEqual(len(self.call('research.inspect',**dest,query='',kind='all',page=0)['resources']),1)
        wrong=copy.deepcopy(doc);wrong['source']['sha256']='0'*64
        self.assertFalse(self.api.dispatch('research.preview',{**dest,'document':wrong})['ok'])

    def test_pack_conflict_requires_acknowledgement_and_stale_review_is_refused(self):
        doc=self.document();doc['notes'][0]['title']='Imported title'
        review=self.call('research.preview',**self.sp,document=doc)
        self.assertTrue(review['replacements'])
        self.assertFalse(self.api.dispatch('research.apply',{**self.sp,'document':doc,'review_id':review['review_id'],'replace':False})['ok'])
        self.save(title='New work',offset=8192)
        self.assertFalse(self.api.dispatch('research.apply',{**self.sp,'document':doc,'review_id':review['review_id'],'replace':True})['ok'])
        current=self.call('research.preview',**self.sp,document=doc)
        applied=self.call('research.apply',**self.sp,document=doc,review_id=current['review_id'],replace=True)
        self.assertEqual(len(applied['notes']),2)
        self.assertIn('Imported title',[n['title'] for n in applied['notes']])

    def test_invalid_last_pack_definition_or_note_cannot_partially_import(self):
        doc=self.document();project=self.api.project(self.p);metadata=project/'project.json';before=metadata.read_bytes()
        for mutate in ('definition','note','field'):
            bad=copy.deepcopy(doc)
            if mutate=='definition':bad['definitions']['tables']={'not':'a table'}
            elif mutate=='note':bad['notes'].append(self.note(id='f'*32,offset=len(self.raw)))
            else:bad['execute']='arbitrary code'
            self.assertFalse(self.api.dispatch('research.preview',{**self.sp,'document':bad})['ok'])
            self.assertEqual(metadata.read_bytes(),before)

    def test_changed_review_document_cannot_be_applied(self):
        doc=self.document();review=self.call('research.preview',**self.sp,document=doc)
        doc['notes'][0]['text']='Changed since review'
        self.assertFalse(self.api.dispatch('research.apply',{**self.sp,'document':doc,'review_id':review['review_id'],'replace':True})['ok'])

    def test_mcp_exposes_read_only_browser_and_explicit_research_writes(self):
        from romancer.mcp_server import READ_OPERATIONS,WRITE_OPERATIONS
        self.assertTrue({'research.inspect','research.preview'}<=READ_OPERATIONS)
        self.assertTrue({'research.note_save','research.note_delete','research.export','research.apply'}<=WRITE_OPERATIONS)

    def test_mcp_dedicated_schemas_accept_actual_research_parameter_types(self):
        from romancer.mcp_server import _schema
        for op,key,expected in [('research.note_save','note','object'),('research.preview','document','object'),('research.apply','replace','boolean'),('references.template','stride','integer')]:
            schema=_schema(self.api.routes[op][0].split(),op)
            self.assertEqual(schema['properties'][key]['type'],expected,(op,key))

    def test_large_unicode_note_lists_keep_mcp_review_and_revision_below_budget(self):
        from romancer.mcp_server import MAX_RESULT
        from romancer.research_tools import ResearchTools
        import hashlib
        row={**self.source,'research_notes':{'format':'romancer-notes-v1','source_sha256':self.source['sha256'],'notes':[
            self.note(id=hashlib.md5(str(i).encode(),usedforsecurity=False).hexdigest(),text='漢'*2000,reference='字'*512) for i in range(50)]}}
        result=ResearchTools(self.api)._public(row)
        self.assertLess(len(json.dumps(result).encode()),MAX_RESULT)
        self.assertIn('revision',result)
