import hashlib,unittest


class SourceInformationTests(unittest.TestCase):
    def test_declared_graphics_bytes_explain_tile_row_plane_and_palette_storage(self):
        import tempfile
        from pathlib import Path
        from romancer.source_information import explain_bytes
        from romancer.resource_forms import graphics_schema
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'graphics';raw=bytes(64)+bytes.fromhex('0003')+bytes(30);path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            schema=graphics_schema(path,sha,{'system_id':'sms','offset':0,'count':2,'palette_offset':64})
            tile=explain_bytes(raw,{'assets':schema},sha,34)['interpretations'][0]
            self.assertEqual((tile['kind'],tile['cell_index'],tile['row'],tile['plane']),('bitmap-byte',1,0,2));self.assertEqual(tile['codec'],'tile8-rowplanar4-msb-v1')
            color=explain_bytes(raw,{'assets':schema},sha,65)['interpretations'][0]
            self.assertEqual((color['kind'],color['bank'],color['index'],color['value']),('palette-entry',0,1,3));self.assertEqual(color['channels']['r'],3)
            self.assertFalse(explain_bytes(raw,{'assets':schema},sha,65)['write_authorized'])
            schema['source']['sha256']='0'*64
            self.assertEqual(explain_bytes(raw,{'assets':schema},sha,34)['interpretations'],[])

    def test_declared_number_has_exact_bytes_type_order_and_numeric_limits(self):
        from romancer.source_information import explain_bytes
        raw=b'\x34\x12\x00\x00';sha=hashlib.sha256(raw).hexdigest()
        table={'schema_version':1,'name':'Declared stats','offset':0,'count':2,'stride':2,'fields':[{'name':'Power','offset':0,'type':'u16','endian':'little','pointer_base':None}]}
        result=explain_bytes(raw,{'tables':{'source_sha256':sha,'definition':table}},sha,1)
        field=result['interpretations'][0];self.assertEqual((field['value'],field['raw_hex'],field['endian'],field['maximum']),(4660,'3412','little',65535))
        self.assertEqual(field['confidence'],'DECLARED');self.assertFalse(result['game_semantics_verified'])
        self.assertEqual(explain_bytes(raw,{},sha,0)['interpretations'],[])

    def test_level_and_sound_ranges_are_identified_without_inventing_game_behavior(self):
        from romancer.source_information import explain_bytes
        from romancer.studio_examples import make_studio_example
        f=make_studio_example();raw=f['raw'];sha=hashlib.sha256(raw).hexdigest()
        result=explain_bytes(raw,{'levels':f['levels'],'sound':f['sound']},sha,0x3010)
        self.assertEqual(result['interpretations'][0]['name'],'hillside terrain')
        with self.assertRaises(ValueError):explain_bytes(raw,{},'0'*64,0)
