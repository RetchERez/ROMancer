from romancer.boot_fixtures import make_boot_fixture
from contextlib import ExitStack
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image


class ResourceExportTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.resource_exports'),'indexed tile sheet export is missing')
        from romancer import resource_exports
        return resource_exports

    def test_indexed_png_import_keeps_distinct_indices_with_duplicate_colors(self):
        from romancer.resource_forms import image_to_cells
        pixels=[0,1]*32;image=Image.new('P',(8,8));image.putpalette([0,0,0]*256);image.putdata(pixels)
        stream=io.BytesIO();image.save(stream,format='PNG')
        palette=[{'r':0,'g':0,'b':0},{'r':0,'g':0,'b':0}]
        result=image_to_cells(stream.getvalue(),8,8,1,1,palette,'exact')
        self.assertEqual(result['cells'][0],pixels);self.assertTrue(result['preserved_palette_indices'])

    def test_export_has_literal_native_indices_and_an_opaque_palette(self):
        service=self.service()
        from romancer.resource_forms import graphics_schema,image_to_cells
        with tempfile.TemporaryDirectory() as folder:
            raw=bytes.fromhex('8040')+b'\0'*14+bytes.fromhex('0080')+b'\0'*14;path=Path(folder)/'tiles';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            schema=graphics_schema(path,sha,{'system_id':'gb','offset':0,'count':2})
            result=service.export_tile_sheet(path,schema,'tiles',2,0)
            expected=[0]*128;expected[0]=1;expected[1]=2;expected[8]=2
            with Image.open(io.BytesIO(result['png'])) as image:
                self.assertEqual(image.mode,'P');self.assertEqual(image.size,(16,8));self.assertEqual(list(image.tobytes()),expected)
            mapped=image_to_cells(result['png'],8,8,2,2,result['palette_rgb'],'exact')
            self.assertEqual(mapped['cells'][0][:8],[1,2,0,0,0,0,0,0]);self.assertEqual(mapped['cells'][1][:8],[2,0,0,0,0,0,0,0])
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(result['palette_scope'],'inspection-aid')
            with self.assertRaises(ValueError):service.export_tile_sheet(path,schema,'tiles',3,0)

    def test_declared_map_and_font_uses_do_not_claim_unknown_references(self):
        service=self.service();document={'ok':True,'document_id':'doc','source_sha256':'1'*64,'bitmaps':[{'id':'tiles','count':2}],
            'tilemaps':[{'id':'Map','bitmap_id':'tiles','entries':[{'index':0,'offset':20,'values':{'tile_index':1}},{'index':1,'offset':22,'values':{'tile_index':0}}]}],
            'fonts':[{'id':'Font','glyphs':[{'id':'A','bitmap_id':'tiles','cell_index':0}]}]}
        result=service.declared_usage(document,'tiles',0)
        self.assertEqual([row['kind'] for row in result['uses']],['tilemap','font'])
        self.assertEqual(result['relationship_coverage'],'declared_only');self.assertFalse(result['native_render_verified'])

    def test_nonfirst_bitmap_and_second_palette_bank_roundtrip(self):
        from romancer.resource_forms import graphics_schema,image_to_cells
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tiles';raw=bytes.fromhex('8040')+b'\0'*14+bytes.fromhex('00001f00e003007c00001f00e003007c')+bytes.fromhex('8040')+b'\0'*14;path.write_bytes(raw)
            schema=graphics_schema(path,hashlib.sha256(raw).hexdigest(),{'system_id':'gb','offset':0,'count':1,'palette_offset':16,'palette_banks':2})
            schema['bitmaps'].append({**schema['bitmaps'][0],'id':'second','offset':32})
            result=self.service().export_tile_sheet(path,schema,'second',1,1)
            self.assertEqual(result['bitmap_id'],'second');self.assertEqual(result['palette_bank'],1)
            mapped=image_to_cells(result['png'],8,8,1,1,result['palette_rgb'],'exact')
            self.assertEqual(mapped['cells'][0][:8],[1,2,0,0,0,0,0,0]);self.assertTrue(mapped['preserved_palette_indices'])

    def test_api_registers_export_without_modifying_the_source(self):
        self.service()
        from romancer.workbench_api import WorkbenchAPI
        from romancer.resource_forms import graphics_schema
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=bytearray(make_boot_fixture('snes')['data']);raw[:16]=bytes.fromhex('8040')+b'\0'*14;raw=bytes(raw);path=root/'tiles.bin';path.write_bytes(raw);api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'PNG export'});source=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(path),'system':None})
                schema=graphics_schema(path,source['sha256'],{'system_id':'gb','offset':0,'count':1})
                result=api.dispatch('resources.export_image',{'project_id':project['project_id'],'artifact_id':source['artifact_id'],'schema':schema,'bitmap_id':'tiles','columns':1,'bank':0})
                self.assertTrue(result['ok'],result);exported,row=api.download(project['project_id'],result['export']['export_id'])
                self.assertEqual(row['role'],'image');self.assertEqual(hashlib.sha256(exported.read_bytes()).hexdigest(),row['sha256']);self.assertEqual(path.read_bytes(),raw)
            finally:api.close()

    def test_address_uses_include_declared_text_and_table_pointers(self):
        from romancer.resource_forms import script_schema
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';raw=b'HELLO\0\xff\xff\0\0';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            descriptors={'script':script_schema(path,sha,{'system_id':'gb','offset':0,'capacity':8,'count':1,'pointer_offset':8}),
                'tables':{'source_sha256':sha,'definition':{'schema_version':1,'name':'Pointers','offset':8,'count':1,'stride':2,'fields':[{'name':'Target','offset':0,'type':'u16','endian':'little','pointer_base':0}]}}}
            result=self.service().declared_address_uses(path,sha,descriptors,0)
            self.assertEqual([row['kind'] for row in result['uses']],['text','text-pointer','table-pointer']);self.assertFalse(result['partial'])

    def test_explicit_definition_reuse_on_a_byte_build_rechecks_current_bytes(self):
        from romancer.workbench_api import WorkbenchAPI
        with ExitStack() as stack:
            folder=stack.enter_context(tempfile.TemporaryDirectory())
            root=Path(folder);raw=bytearray(1024);raw[:8]=b'HELLO\0\xff\xff';raw[0x100:0x110]=b'SEGA MEGA DRIVE ';raw[0x1a4:0x1a8]=(1023).to_bytes(4,'big');path=root/'source';path.write_bytes(raw);api=WorkbenchAPI(root/'workspace');stack.callback(api.close)
            project=api.dispatch('project.create',{'name':'Reuse'});p={'project_id':project['project_id']};source=api.dispatch('source.import',{**p,'path':str(path),'system':None});src={**p,'artifact_id':source['artifact_id']}
            api.dispatch('resources.declare_script',{**src,'config':{'system_id':'gb','offset':0,'capacity':8,'count':1}})
            plan=api.dispatch('bytes.plan',{**src,'edits':[{'offset':0,'before':'48','after':'4a'}]});built=api.dispatch('build.apply',{**p,'plan_id':plan['plan_id']})
            reused=api.dispatch('resources.reuse_definitions',{**p,'artifact_id':built['artifact_id']});self.assertTrue(reused['ok'],reused)
            current=api.dispatch('project.open',p)['builds'][-1];doc=api.dispatch('script.inspect',{**p,'artifact_id':built['artifact_id'],'schema':current['descriptors']['script']});self.assertEqual(doc['records'][0]['segments'][0]['text'],'JELLO')
