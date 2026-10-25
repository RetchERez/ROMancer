import hashlib,unittest


class SourceInformationTests(unittest.TestCase):
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
