import copy
import importlib
from pathlib import Path
import tempfile
import unittest
from asset_fixtures import asset_fixture


class SchemaTests(unittest.TestCase):
    def validator(self):
        try: module=importlib.import_module('romancer.asset_schema')
        except ModuleNotFoundError: module=None
        self.assertIsNotNone(module,'asset descriptor validation is missing')
        return module.validate_asset_schema

    def test_detached_descriptor_and_unknown_codec_are_read_only(self):
        validate=self.validator()
        with tempfile.TemporaryDirectory() as temp:
            _,schema=asset_fixture(Path(temp));result=validate(schema)
            self.assertTrue(result['write_supported'])
            schema['id']='changed'
            self.assertEqual(result['normalized_schema']['id'],'handwritten-art')
            schema['bitmaps'][0]['codec']='not-understood'
            self.assertFalse(validate(schema)['write_supported'])

    def test_masks_overlaps_aliases_bounds_and_types_reject(self):
        validate=self.validator()
        with tempfile.TemporaryDirectory() as temp:
            _,schema=asset_fixture(Path(temp))
            mutations=[lambda x:x.update(extra=1),
                lambda x:x['source'].update(sha256=int('1'*64)),
                lambda x:x['bitmaps'][0].update(count=True),
                lambda x:x['bitmaps'][0].update(offset=60),
                lambda x:x['bitmaps'][1].update(offset=4),
                lambda x:x['palettes'][0]['channels'].update(r=5),
                lambda x:x['palettes'][0]['channels'].update(r=992),
                lambda x:x['palettes'][0].update(colors_per_bank=3),
                lambda x:x['tilemaps'][0]['fields']['flip_x'].update(mask=65536),
                lambda x:x['tilemaps'][0].update(bitmap_id='missing'),
                lambda x:x['fonts'][0]['glyphs'].append(copy.deepcopy(x['fonts'][0]['glyphs'][0])),
                lambda x:x['fonts'][0]['glyphs'][0]['advance'].update(offset=32),
                lambda x:x['provenance'].update(note='bad\x00note')]
            for mutate in mutations:
                item=copy.deepcopy(schema);mutate(item)
                with self.subTest(item=item),self.assertRaises(ValueError):validate(item)
            cyclic=copy.deepcopy(schema);cyclic['provenance']['reference']=cyclic
            with self.assertRaises(ValueError):validate(cyclic)
