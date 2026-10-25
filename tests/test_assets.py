import copy
import importlib
from pathlib import Path
import tempfile
import unittest
from asset_fixtures import asset_fixture


class AssetTests(unittest.TestCase):
    def services(self):
        try:
            assets=importlib.import_module('romancer.assets')
            patch=importlib.import_module('romancer.asset_patch')
        except ModuleNotFoundError: assets=patch=None
        self.assertIsNotNone(assets,'asset transaction services are missing')
        return assets,patch

    def request(self,document):
        pixels=[1]+[0]*62+[2];after=list(pixels);after[1]=3
        return {'schema_version':1,'document_id':document['document_id'],
                'changes':[{'kind':'cell','bitmap_id':'tiles','cell_index':0,'before_pixels':pixels,'after_pixels':after}],
                'acknowledged_consumers':[{'kind':'map','id':'map','entry_index':0},{'kind':'map','id':'map','entry_index':1}]}

    def test_cell_edit_preserves_every_other_byte_and_requires_consumers(self):
        assets,patch=self.services()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,schema=asset_fixture(root);original=source.read_bytes()
            doc=assets.inspect_assets(source,schema);self.assertTrue(doc['ok'],doc)
            request=self.request(doc);missing=copy.deepcopy(request);missing['acknowledged_consumers']=[]
            refused=assets.plan_assets(source,schema,missing)
            self.assertFalse(refused['ok']);self.assertEqual(len(refused['required_consumers']),2)
            plan=assets.plan_assets(source,schema,request);self.assertTrue(plan['ok'],plan)
            result=patch.apply_assets(source,root/'edited.bin',schema,request,expected_plan_id=plan['plan_id'])
            self.assertTrue(result['written'],result)
            expected=bytearray(original);expected[4]=0xc0;expected[12]=0x40
            self.assertEqual((root/'edited.bin').read_bytes(),bytes(expected))
            self.assertEqual(source.read_bytes(),original)

    def test_palette_map_reserved_bits_and_advance_preservation(self):
        assets,patch=self.services()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,schema=asset_fixture(root);original=source.read_bytes()
            doc=assets.inspect_assets(source,schema)
            request={'schema_version':1,'document_id':doc['document_id'],'changes':[
                {'kind':'palette','palette_id':'colors','bank':0,'index':0,'before':{'r':0,'g':0,'b':0},'after':{'r':7,'g':0,'b':0}},
                {'kind':'map','tilemap_id':'map','entry_index':0,'before':{'tile_index':0,'palette_bank':0,'flip_x':0,'flip_y':0},'after':{'tile_index':0,'palette_bank':0,'flip_x':1,'flip_y':0}},
                {'kind':'advance','font_id':'font','glyph_id':'glyph','before':5,'after':6}],
                'acknowledged_consumers':[{'kind':'glyph','font_id':'font','glyph_id':'glyph'},{'kind':'map','id':'map','entry_index':0},{'kind':'map','id':'map','entry_index':1}]}
            plan=assets.plan_assets(source,schema,request);self.assertTrue(plan['ok'],plan)
            result=patch.apply_assets(source,root/'edited.bin',schema,request,expected_plan_id=plan['plan_id'])
            self.assertTrue(result['ok'],result)
            expected=bytearray(original);expected[21]=7;expected[28]=0x60;expected[40]=6
            self.assertEqual((root/'edited.bin').read_bytes(),bytes(expected))

    def test_stale_source_stale_plan_collision_and_noop_never_publish(self):
        assets,patch=self.services()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,schema=asset_fixture(root)
            doc=assets.inspect_assets(source,schema);request=self.request(doc)
            noop={'schema_version':1,'document_id':doc['document_id'],'changes':[],'acknowledged_consumers':[]}
            plan=assets.plan_assets(source,schema,noop)
            result=patch.apply_assets(source,root/'none.bin',schema,noop,expected_plan_id=plan['plan_id'])
            self.assertFalse(result['written']);self.assertFalse((root/'none.bin').exists())
            result=patch.apply_assets(source,root/'none.bin',schema,request,expected_plan_id='0'*64)
            self.assertFalse(result['written'])
            output=root/'exists.bin';output.write_bytes(b'keep')
            plan=assets.plan_assets(source,schema,request)
            result=patch.apply_assets(source,output,schema,request,expected_plan_id=plan['plan_id'])
            self.assertFalse(result['written']);self.assertEqual(output.read_bytes(),b'keep')
            changed=bytearray(source.read_bytes());changed[0]=0
            source.write_bytes(changed)
            self.assertFalse(assets.plan_assets(source,schema,request)['ok'])
