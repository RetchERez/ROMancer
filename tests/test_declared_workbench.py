import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


class DeclaredWorkbenchTests(unittest.TestCase):
    def test_level_and_sound_definition_roundtrip_checks_real_source(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder)/'workspace');self.addCleanup(api.close)
            project=api.dispatch('studio.example',{});self.assertTrue(project['ok'],project)
            opened=api.dispatch('project.open',{'project_id':project['project_id']});source=opened['sources'][0]
            p={'project_id':project['project_id'],'artifact_id':source['artifact_id']}
            for kind in ('levels','sound'):
                with self.subTest(kind=kind):
                    result=api.dispatch('definitions.export',{**p,'kind':kind});self.assertTrue(result['ok'],result)
                    path,_=api.download(p['project_id'],result['export']['export_id']);document=json.loads(path.read_bytes())
                    self.assertEqual(document['kind'],kind);self.assertNotIn('path',document['source'])
                    self.assertTrue(api.dispatch('definitions.import',{**p,'document':document})['ok'])
                    bad=copy.deepcopy(document);bad['source']['sha256']='0'*64
                    self.assertFalse(api.dispatch('definitions.import',{**p,'document':bad})['ok'])

    def test_catalog_indexes_checked_level_sound_and_table_storage(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder)/'workspace');self.addCleanup(api.close)
            project=api.dispatch('studio.example',{});opened=api.dispatch('project.open',{'project_id':project['project_id']})
            source=opened['sources'][0];p={'project_id':project['project_id'],'artifact_id':source['artifact_id']}
            definition={'schema_version':1,'name':'Known values','offset':0x3f10,'count':2,'stride':1,
                        'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]}
            self.assertTrue(api.dispatch('tables.save_definition',{**p,'definition':definition})['ok'])
            indexed=api.dispatch('catalog.index',p);self.assertTrue(indexed['ok'],indexed)
            rows=api.dispatch('catalog.list',{**p,'query':'','page':0,'limit':100})
            kinds={r['kind'] for r in rows['resources']}
            self.assertTrue({'room','objects','table','sample','song'}<=kinds,kinds)
            self.assertFalse(rows['write_authorized'])
            again=api.dispatch('catalog.index',p);self.assertEqual(again['total'],indexed['total'])

    def test_explanation_names_exact_room_cell_and_object_field(self):
        from romancer.studio_examples import make_studio_example
        from romancer.source_information import explain_bytes
        f=make_studio_example();raw=f['raw'];sha=hashlib.sha256(raw).hexdigest();d={'levels':f['levels'],'sound':f['sound']}
        room=f['levels']['rooms'][0];g=room['terrain'];offset=g['offset']+g['entry_bytes']*2
        rows=explain_bytes(raw,d,sha,offset)['interpretations'];cell=next(r for r in rows if r.get('kind')=='terrain-cell')
        self.assertEqual((cell['room_id'],cell['x'],cell['y']),(room['id'],2,0));self.assertEqual(cell['offset'],offset)
        self.assertEqual(cell['value'],int.from_bytes(raw[offset:offset+g['entry_bytes']],g['endian']))
        obj=room['objects'];field=obj['fields'][0];offset=obj['offset']+field['offset']
        rows=explain_bytes(raw,d,sha,offset)['interpretations'];info=next(r for r in rows if r.get('kind')=='object-field')
        self.assertEqual((info['room_id'],info['object_index'],info['field']),(room['id'],0,field['name']))
        self.assertEqual(info['confidence'],'DECLARED');self.assertFalse(explain_bytes(raw,d,sha,offset)['game_semantics_verified'])

    def test_explicit_exit_explanation_and_relationships_agree(self):
        from romancer.studio_examples import make_studio_example
        from romancer.source_information import explain_bytes
        from romancer.studio_discovery import resource_relationships
        f=make_studio_example();raw=f['raw'];sha=hashlib.sha256(raw).hexdigest();d={'levels':f['levels']}
        room=f['levels']['rooms'][0];entry=next(m for m in room['object_metadata'] if m['role']=='exit')
        o=room['objects'];field=next(r for r in o['fields'] if r['name']==entry['reference']['field'])
        at=o['offset']+entry['index']*o['stride']+field['offset']
        row=next(r for r in explain_bytes(raw,d,sha,at)['interpretations'] if r.get('kind')=='object-field')
        self.assertEqual(row['target_room_id'],'courtyard')
        links=resource_relationships(raw,d,sha)
        self.assertEqual(links['relationship_coverage'],'declared_only');self.assertFalse(links['partial'])
        self.assertTrue(any(e['to']=='level:courtyard terrain' and 'declared exit' in e['relation'] for e in links['edges']))
