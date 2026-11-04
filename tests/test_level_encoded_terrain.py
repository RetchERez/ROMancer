"""Encoded terrain keeps physical operands distinct from visible cells."""
import copy
import hashlib
import unittest
import tempfile
from pathlib import Path
from romancer.level_design import inspect_level,plan_level
from romancer.adapters.registry import adapter_for


def fixture(stream=None):
    stream=stream if stream is not None else bytes([0x00,0xfd,4,0xfe])+b'\xfe'*19
    raw=bytearray(32768)
    raw[:4096]=bytes((i*13)&255 for i in range(4096));raw[4096]=0xe4
    raw[0x4000:0x4000+len(stream)]=stream
    sha=hashlib.sha256(raw).hexdigest()
    definition={'schema_version':1,'source_sha256':sha,'name':'Encoded terrain fixture',
      'tiles':{'offset':0,'count':256,'codec':'tile8-paired2-msb-v1','palette_offset':4096,'palette_format':'dmg-shades'},
      'metatiles':{'kind':'identity'},'rooms':[{'id':'a','name':'A','width':20,'height':16,
       'terrain':{'codec':'sml-column-segments-v1','offset':0x4000,'length':len(stream)},'collision':None,'objects':None}]}
    return bytes(raw),definition,sha


class EncodedTerrainTests(unittest.TestCase):
    def test_inspection_reports_true_storage_and_visible_operand_fanout(self):
        raw,d,sha=fixture();doc=inspect_level(raw,d,sha);room=doc['rooms'][0]
        self.assertEqual(room['terrain'][0],4);self.assertEqual(room['terrain'][20],4)
        self.assertEqual(room['terrain_storage']['origins'][0],0x4002)
        self.assertEqual(room['terrain_storage']['origins'][300],0x4002)
        self.assertIsNone(room['terrain_storage']['origins'][1])
        self.assertEqual(next(r['length']for r in doc['ranges']if r['name']=='a terrain'),23)
        self.assertFalse(doc['game_semantics_verified'])

    def test_adapter_noop_preserves_every_byte_without_normalizing_the_stream(self):
        raw,d,sha=fixture();adapter=adapter_for('levels',raw,d,sha)
        self.assertTrue(adapter.roundtrip()['byte_identical'])
        terrain=next(r for r in adapter.inventory()['resources']if r['kind']=='terrain')
        self.assertEqual((terrain['offset'],terrain['length']),(0x4000,23))

    def test_plan_writes_one_operand_for_all_repeat_cells_and_deduplicates_agreeing_edits(self):
        raw,d,sha=fixture();doc=inspect_level(raw,d,sha)
        changes=[{'kind':'terrain','room_id':'a','index':i,'value':6}for i in(0,300)]
        plan=plan_level(raw,d,doc['document_id'],changes,sha)
        self.assertEqual(plan['edits'],[{'offset':0x4002,'before':'04','after':'06'}])
        self.assertEqual(plan['affected_cells'],[{'room_id':'a','cells':list(range(0,320,20))}])
        changes[1]['value']=7
        with self.assertRaisesRegex(ValueError,'shared|conflict'):plan_level(raw,d,doc['document_id'],changes,sha)

    def test_defaults_markers_and_interactive_operands_are_not_ordinary_flat_grid_cells(self):
        for stream,index,value,reason in[(None,1,6,'implicit'),(bytes([0x01,4,0xfe])+b'\xfe'*19,0,0xfd,'marker'),(bytes([0x01,0x70,0xfe])+b'\xfe'*19,0,6,'[Ii]nteractive')]:
            raw,d,sha=fixture(stream);doc=inspect_level(raw,d,sha)
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                plan_level(raw,d,doc['document_id'],[{'kind':'terrain','room_id':'a','index':index,'value':value}],sha)

    def test_declared_bounds_dimensions_and_unsupported_codec_are_rejected(self):
        for mutation in('geometry','trailing','unknown','cross_bank'):
            raw,d,sha=fixture()
            if mutation=='geometry':d['rooms'][0]['width']=16;d['rooms'][0]['height']=20
            elif mutation=='trailing':d['rooms'][0]['terrain']['length']+=1
            elif mutation=='unknown':d['rooms'][0]['terrain']['codec']='guessed'
            else:d['rooms'][0]['terrain']['offset']=0x7ff0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):inspect_level(raw,d,sha)

    def test_byte_explanations_use_encoded_operands_instead_of_inventing_flat_cells(self):
        from romancer.source_information import explain_bytes
        raw,d,sha=fixture();result=explain_bytes(raw,{'levels':d},sha,0x4002)
        entries=[r for r in result['interpretations']if r['kind']=='terrain-operand']
        self.assertEqual(len(entries),1);self.assertEqual(entries[0]['affected_cells'],list(range(0,320,20)))
        self.assertTrue(all(r['kind']!='terrain-cell'for r in result['interpretations']))

    def test_public_api_keeps_fanout_and_checksum_aware_builds_reopen_with_the_layout(self):
        from romancer.boot_fixtures import make_boot_fixture
        from romancer.workbench_api import WorkbenchAPI
        payload,d,_=fixture();raw=bytearray(make_boot_fixture('gb')['data'])
        raw[0x1000:0x2000]=payload[:4096];raw[0x2000]=0xe4
        raw[0x4000:0x4017]=payload[0x4000:0x4017]
        d['tiles']['offset']=0x1000;d['tiles']['palette_offset']=0x2000
        d['source_sha256']=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'original.gb';path.write_bytes(raw)
            api=WorkbenchAPI(Path(directory)/'work')
            try:
                settings=api.dispatch('settings.get',{})
                api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
                p={'project_id':api.dispatch('project.create',{'name':'Encoded level'})['project_id']}
                source=api.dispatch('source.import',{**p,'path':str(path),'system':None});self.assertTrue(source['ok'],source)
                params={**p,'artifact_id':source['artifact_id']}
                self.assertTrue(api.dispatch('studio.definition',{**params,'kind':'levels','definition':d})['ok'])
                doc=api.dispatch('levels.inspect',{**params,'definition':d});self.assertTrue(doc['ok'],doc)
                plan=api.dispatch('levels.plan',{**params,'definition':d,'document_id':doc['document_id'],'changes':[{'kind':'terrain','room_id':'a','index':300,'value':6}]})
                self.assertTrue(plan['ok'],plan)
                self.assertEqual(plan.get('affected_cells'),[{'room_id':'a','cells':list(range(0,320,20))}])
                built=api.dispatch('build.apply',{**p,'plan_id':plan['plan_id']});self.assertTrue(built['ok'],built)
                self.assertEqual(path.read_bytes(),raw)
                output=Path(built['path']).read_bytes();self.assertEqual(output[0x4002],6)
                self.assertTrue(set(i for i,(a,b)in enumerate(zip(raw,output))if a!=b)<={0x14e,0x14f,0x4002})
                opened=api.dispatch('project.open',p)['builds'][0];definition=opened['descriptors']['levels']
                derived=api.dispatch('levels.inspect',{**p,'artifact_id':built['artifact_id'],'definition':definition})
                self.assertTrue(derived['ok'],derived);self.assertEqual(derived['rooms'][0]['terrain'][300],6)
            finally:api.close()
