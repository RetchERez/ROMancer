"""Direct tile grids and mixed stored graphics need no invented metatile table."""
import copy,hashlib,unittest


def fixture():
    raw=bytearray(512);raw[:16]=bytes([0x80]*8+[0x01]*8)
    raw[64:96]=bytes([0xff,0]*8+[0,0xff]*8);raw[128]=0xe4;raw[160:164]=bytes([0,1,2,3])
    sha=hashlib.sha256(raw).hexdigest()
    definition={'schema_version':1,'source_sha256':sha,'name':'Stored screen',
      'tiles':{'count':4,'color_count':4,'segments':[
        {'first':0,'count':2,'offset':0,'codec':'mono-row-msb-v1','pixel_map':[0,3]},
        {'first':2,'count':2,'offset':64,'codec':'tile8-paired2-msb-v1','pixel_map':[0,1,2,3]}],
        'palette_offset':128,'palette_format':'dmg-shades'},'metatiles':{'kind':'identity'},
      'rooms':[{'id':'screen','name':'Screen','width':2,'height':2,'terrain':{'offset':160,'entry_bytes':1,'endian':'little'},'collision':None,'objects':None}]}
    return bytes(raw),definition,sha


class SegmentedLevelTilesTests(unittest.TestCase):
    def test_mixed_graphics_use_explicit_source_index_mapping_and_hardware_shades(self):
        from romancer.level_design import inspect_level
        raw,d,sha=fixture();doc=inspect_level(raw,d,sha)
        self.assertEqual(doc['palette'],[[255]*3,[170]*3,[85]*3,[0]*3])
        self.assertEqual(doc['tiles'][0][:8],[3,0,0,0,0,0,0,0]);self.assertEqual(doc['tiles'][1][:8],[0,0,0,0,0,0,0,3])
        self.assertEqual(doc['tiles'][2],[1]*64);self.assertEqual(doc['tiles'][3],[2]*64)
        self.assertEqual(doc['metatiles'],[[0],[1],[2],[3]]);self.assertFalse(doc['metatiles_stored'])
        self.assertEqual(doc['block_width'],1);self.assertEqual(doc['block_height'],1)
        self.assertEqual({r['name'] for r in doc['ranges']},{'tiles segment0','tiles segment1','palette','screen terrain'})

    def test_adapter_roundtrip_preserves_every_byte_and_dependencies_resolve(self):
        from romancer.adapters.registry import adapter_for
        raw,d,sha=fixture();adapter=adapter_for('levels',raw,d,sha);proof=adapter.roundtrip()
        self.assertTrue(proof['byte_identical']);self.assertTrue(proof['reserved_bytes_preserved'])
        resources=adapter.inventory()['resources'];by_id={r['id']:r for r in resources}
        self.assertEqual(len(resources),4)
        terrain=next(r for r in resources if r['kind']=='terrain')
        self.assertEqual(len(terrain['dependencies']),2)
        self.assertTrue(all(by_id[h]['kind']=='tiles' for h in terrain['dependencies']))

    def test_direct_grid_edits_write_only_actual_grid_storage(self):
        from romancer.level_design import inspect_level,plan_level
        raw,d,sha=fixture();doc=inspect_level(raw,d,sha)
        plan=plan_level(raw,d,doc['document_id'],[{'kind':'terrain','room_id':'screen','index':3,'value':0}],sha)
        self.assertEqual(plan['edits'],[{'offset':163,'before':'03','after':'00'}])
        with self.assertRaisesRegex(ValueError,'derived|stored|identity'):
            plan_level(raw,d,doc['document_id'],[{'kind':'metatile','index':0,'part':0,'value':1}],sha)

    def test_overlaps_gaps_aliases_and_wrong_palettes_fail_closed(self):
        from romancer.level_design import inspect_level
        for mutation in ('source_overlap','virtual_overlap','virtual_gap','too_many_tiles','bad_map','duplicate_color','unsupported_color','wrong_colors','bad_codec','unhashable_codec','too_many_segments','extra_field','invalid_tiles','invalid_blocks'):
            raw,d,sha=fixture();a,b=d['tiles']['segments']
            if mutation=='source_overlap':b['offset']=8
            elif mutation=='virtual_overlap':b['first']=1
            elif mutation=='virtual_gap':b['first']=3
            elif mutation=='too_many_tiles':d['tiles']['count']=1025
            elif mutation=='bad_map':a['pixel_map']=[0]
            elif mutation=='duplicate_color':a['pixel_map']=[0,0]
            elif mutation=='unsupported_color':a['pixel_map']=[0,4]
            elif mutation=='wrong_colors':d['tiles']['color_count']=16
            elif mutation=='bad_codec':a['codec']='unknown'
            elif mutation=='unhashable_codec':a['codec']=[]
            elif mutation=='too_many_segments':d['tiles']['segments']=[copy.deepcopy(a)]*65
            elif mutation=='invalid_tiles':d['tiles']=None
            elif mutation=='invalid_blocks':d['metatiles']=None
            else:a['guessed']=True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):inspect_level(raw,d,sha)

    def test_packed_monochrome_register_roundtrips_all_256_values(self):
        from romancer.level_palette import decode_palette,encode_palette,storage_length
        self.assertEqual(storage_length('dmg-shades',4),1)
        for value in range(256):
            raw=bytes([value]);colors=decode_palette(raw,'dmg-shades',4)
            self.assertEqual(encode_palette(colors,'dmg-shades',raw),raw)
        for count in (True,1,3,16):
            with self.assertRaises(ValueError):decode_palette(b'\xe4','dmg-shades',count)
        for colors in ([[0,1,0]]*4,[[42]*3]*4):
            with self.assertRaises(ValueError):encode_palette(colors,'dmg-shades',b'\xe4')

    def test_byte_explanations_do_not_treat_identity_tiles_as_a_stored_table(self):
        from romancer.source_information import explain_bytes
        raw,d,sha=fixture();result=explain_bytes(raw,{'levels':d},sha,160)
        self.assertTrue(result['interpretations']);self.assertTrue(all(r['kind']!='metatile-part' for r in result['interpretations']))
