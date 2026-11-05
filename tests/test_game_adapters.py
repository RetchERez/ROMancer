import copy,hashlib,tempfile,unittest
from pathlib import Path
from tests import test_scene_schema as scenes


class GameAdapterTests(unittest.TestCase):
    def adapter(self,raw=None,definition=None):
        from romancer.adapters.registry import adapter_for
        source,d,sha=scenes.SceneSchemaTests().fixture()
        if raw is not None:source=raw;sha=hashlib.sha256(source).hexdigest();d['source_sha256']=sha
        return adapter_for('levels',source,definition or d,sha)

    def test_noop_reencodes_declared_fields_and_preserves_opaque_bytes(self):
        adapter=self.adapter();proof=adapter.roundtrip()
        self.assertTrue(proof['byte_identical']);self.assertEqual(proof['source_sha256'],proof['encoded_sha256'])
        self.assertEqual(proof['declared_ranges_checked'],7)
        self.assertFalse(proof['game_revision_complete']);self.assertFalse(proof['native_verified'])
        doc=adapter.inspect();doc['rooms'][0]['terrain'][0]=999
        self.assertEqual(adapter.inspect()['rooms'][0]['terrain'][0],0,'returned documents do not mutate adapter state')

    def test_reserved_rgb555_bits_and_object_padding_are_not_destroyed(self):
        from romancer.adapters.registry import adapter_for
        raw,d,_=scenes.SceneSchemaTests().fixture();raw=bytearray(raw)
        d['tiles']['palette_format']='rgb555-le'
        raw[32:40]=b'\xff\xff\x00\x80\x1f\x80\xe0\x83';raw[197:200]=b'\xa1\xb2\xc3'
        sha=hashlib.sha256(raw).hexdigest();d['source_sha256']=sha
        result=adapter_for('levels',bytes(raw),d,sha).roundtrip()
        self.assertTrue(result['byte_identical']);self.assertTrue(result['reserved_bytes_preserved'])

    def test_all_existing_tile_codecs_and_palette_orders_roundtrip(self):
        from romancer.asset_codecs import CODECS,encode_cell
        from romancer.adapters.registry import adapter_for
        for codec,bits in CODECS.items():
            for palette_format in ['rgb888','rgb555-le','rgb555-be']:
                with self.subTest(codec=codec,palette=palette_format):
                    source,d,_=scenes.SceneSchemaTests().fixture();raw=bytearray(source)
                    d['tiles'].update(codec=codec,palette_offset=256,palette_format=palette_format)
                    for index in range(2):
                        encoded=encode_cell([(pixel+index)%(1<<bits) for pixel in range(64)],codec=codec,width=8,height=8)
                        raw[index*len(encoded):(index+1)*len(encoded)]=encoded
                    for color in range(1<<bits):
                        at=256+color*(3 if palette_format=='rgb888' else 2)
                        if palette_format=='rgb888':raw[at:at+3]=bytes((color*13%256,color*29%256,color*47%256))
                        else:raw[at:at+2]=(0x8000|(color*2113&32767)).to_bytes(2,'little' if palette_format.endswith('le') else 'big')
                    sha=hashlib.sha256(raw).hexdigest();d['source_sha256']=sha
                    self.assertTrue(adapter_for('levels',bytes(raw),d,sha).roundtrip()['byte_identical'])

    def test_inventory_is_exact_scoped_and_dependencies_affect_preview_resources(self):
        adapter=self.adapter();inventory=adapter.inventory();ids={r['kind']:r['id'] for r in inventory['resources']}
        self.assertEqual(set(ids),{'tiles','palette','metatiles','terrain','collision','elevation','objects'})
        self.assertEqual(len(inventory['adapter_sha256']),64);self.assertFalse(inventory['game_revision_complete'])
        self.assertTrue(inventory['unresolved']);self.assertTrue(all(r['source_sha256']==inventory['source_sha256'] for r in inventory['resources']))
        doc=adapter.inspect();plan=adapter.plan(doc['document_id'],[{'kind':'metatile','index':0,'part':0,'value':1}])
        self.assertEqual(set(plan['resource_impact']),{ids['metatiles'],ids['terrain']})
        height=adapter.plan(doc['document_id'],[{'kind':'elevation','room_id':'room-0','index':0,'value':1}])
        self.assertEqual(set(height['resource_impact']),{ids['elevation'],ids['terrain']})
        changed=adapter.inventory();changed['resources'][0]['id']='tampered'
        self.assertEqual(adapter.inventory(),inventory)

    def test_closed_registry_and_source_document_guards_are_shared(self):
        from romancer.adapters.registry import adapter_for
        raw,d,sha=scenes.SceneSchemaTests().fixture()
        for kind in ['unknown','external.python','../levels']:
            with self.subTest(kind=kind),self.assertRaises(ValueError):adapter_for(kind,raw,d,sha)
        with self.assertRaises(ValueError):adapter_for('levels',raw,d,'0'*64)
        adapter=self.adapter()
        with self.assertRaisesRegex(ValueError,'stale'):adapter.plan('0'*64,[{'kind':'elevation','room_id':'room-0','index':0,'value':1}])

    def test_actual_api_inspection_and_review_use_the_same_adapter(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.boot_fixtures import make_boot_fixture
        raw,d,_=scenes.SceneSchemaTests().fixture();data=bytearray(make_boot_fixture('nes')['data']);base=0x1000;data[base:base+len(raw)]=raw
        d=copy.deepcopy(d);d['source_sha256']=hashlib.sha256(data).hexdigest()
        for k in ['offset','palette_offset']:d['tiles'][k]+=base
        d['metatiles']['offset']+=base
        for room in d['rooms']:
            for k in ['terrain','collision','elevation','objects']:room[k]['offset']+=base
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'scene.nes';path.write_bytes(data);api=WorkbenchAPI(root/'work')
            try:
                settings=api.dispatch('settings.get',{});api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
                project=api.dispatch('project.create',{'name':'Adapter contract'});p={'project_id':project['project_id']}
                source=api.dispatch('source.import',{**p,'path':str(path),'system':None});p['artifact_id']=source['artifact_id']
                doc=api.dispatch('levels.inspect',{**p,'definition':d});self.assertTrue(doc['ok'],doc)
                self.assertEqual(doc['adapter']['adapter_id'],'declared-level-v1');self.assertTrue(doc['adapter']['roundtrip']['byte_identical'])
                plan=api.dispatch('levels.plan',{**p,'definition':d,'document_id':doc['document_id'],'changes':[{'kind':'elevation','room_id':'room-0','index':0,'value':1}]})
                self.assertTrue(plan['ok'],plan);self.assertTrue(plan['resource_impact']);self.assertEqual(plan['adapter_sha256'],doc['adapter']['adapter_sha256'])
                self.assertEqual(path.read_bytes(),bytes(data))
            finally:api.close()


def setUpModule():
    # Exercise preserved development internals separately from the release boundary.
    from unittest import addModuleCleanup
    from unittest.mock import patch
    feature = patch("romancer.release_scope.LEVEL_EDITOR_ENABLED", True)
    feature.start()
    addModuleCleanup(feature.stop)
