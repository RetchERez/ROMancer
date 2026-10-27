import hashlib
from pathlib import Path
import tempfile
import unittest


class ResourceFormsTests(unittest.TestCase):
    def test_sms_palette_and_tilemap_use_documented_mode4_bits(self):
        from romancer.resource_forms import graphics_schema
        from romancer.assets import inspect_assets
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'declared-data';raw=bytearray(96);raw[0]=0x80;raw[33]=0x03;raw[64:66]=(0xfe00).to_bytes(2,'little');path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            schema=graphics_schema(path,sha,{'system_id':'sms','offset':0,'count':1,'palette_offset':32,'palette_banks':2,'map_offset':64,'map_width':1,'map_height':1})
            self.assertEqual(schema['palettes'][0]['entry_bytes'],1);self.assertEqual(schema['palettes'][0]['channels'],{'r':3,'g':12,'b':48})
            self.assertEqual(schema['tilemaps'][0]['fields']['tile_index']['mask'],0x1ff)
            self.assertEqual(schema['tilemaps'][0]['fields']['flip_x']['mask'],0x200);self.assertEqual(schema['tilemaps'][0]['fields']['flip_y']['mask'],0x400)
            self.assertEqual(schema['tilemaps'][0]['fields']['palette_bank']['mask'],0x800)
            doc=inspect_assets(path,schema);self.assertTrue(doc['ok'],doc);self.assertEqual(doc['palettes'][0]['entries'][1]['rgb'],{'r':255,'g':0,'b':0})
            from romancer.assets import plan_assets
            from romancer.asset_patch import apply_assets
            request={'schema_version':1,'document_id':doc['document_id'],'changes':[{'kind':'map','tilemap_id':'map','entry_index':0,'before':doc['tilemaps'][0]['entries'][0]['values'],'after':{'tile_index':0,'palette_bank':0,'flip_x':0,'flip_y':0}}],'acknowledged_consumers':[{'kind':'map','id':'map','entry_index':0}]}
            plan=plan_assets(path,schema,request);self.assertTrue(plan['ok'],plan)
            output=Path(temp)/'edited';self.assertTrue(apply_assets(path,output,schema,request,expected_plan_id=plan['plan_id'])['ok'])
            self.assertEqual(output.read_bytes()[64:66],bytes.fromhex('00f0'),'Priority and unused bits must survive map editing.')
            self.assertEqual(path.read_bytes(),raw)

    def test_guided_pointer_base_accepts_real_32_bit_rom_addresses(self):
        from romancer.resource_forms import script_schema
        from romancer.script import inspect_script
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'original';source.write_bytes((0x08000008).to_bytes(4,'little')+b'SAFEAB\0'+b'\xff'*5)
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            config={'system_id':'gba','offset':8,'capacity':8,'count':1,'stride':8,
                'pointer_offset':0,'pointer_width':4,'pointer_endian':'little','pointer_base':-0x08000000}
            schema=script_schema(source,sha,config);doc=inspect_script(source,schema)
            self.assertTrue(doc['write_supported'],doc)
            self.assertEqual(schema['format']['pointers'][0]['base'],-0x08000000)
            with self.assertRaises(ValueError):script_schema(source,sha,{**config,'pointer_base':0x100000000})

    def test_api_structured_cartridge_build_reviews_and_repairs_checksum(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.system_demo import make_system_fixtures
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'own.sfc';source.write_bytes(make_system_fixtures()['snes']);api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'SNES form'});p={'project_id':project['project_id']}
                row=api.dispatch('source.import',{**p,'path':str(source),'system':None});selection={**p,'artifact_id':row['artifact_id']}
                declared=api.dispatch('resources.declare_assets',{**selection,'config':{'system_id':'snes','offset':0x1000,'count':1}});self.assertTrue(declared['ok'],declared)
                doc=declared['inspection'];before=doc['bitmaps'][0]['cells'][0]['pixels'];after=before.copy();after[0]=1
                plan=api.dispatch('assets.plan',{**selection,'schema':declared['schema'],'edits':{'schema_version':1,'document_id':doc['document_id'],'changes':[{'kind':'cell','bitmap_id':'tiles','cell_index':0,'before_pixels':before,'after_pixels':after}],'acknowledged_consumers':[]}})
                self.assertTrue(plan['integrity_edits']);built=api.dispatch('structured.apply',{**p,'plan_id':plan['workbench_plan_id']});self.assertTrue(built['ok'],built)
                raw=Path(built['path']).read_bytes();self.assertEqual(int.from_bytes(raw[0x7fde:0x7fe0],'little'),sum(raw)&65535);self.assertEqual(raw[0x1000],128)
                self.assertEqual(built['output_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(built['sha256'],built['output_sha256'])
            finally:api.close()
    def test_gba_low_nibble_storage_has_literal_pixel_order(self):
        from romancer.asset_codecs import decode_cell,encode_cell
        raw=bytes.fromhex('21'+'00'*30+'fe');pixels=[1,2]+[0]*60+[14,15]
        self.assertEqual(decode_cell(raw,codec='tile8-packed4-low-v1',width=8,height=8),pixels)
        self.assertEqual(encode_cell(pixels,codec='tile8-packed4-low-v1',width=8,height=8),raw)

    def test_guided_text_pointer_and_slot_edits_preserve_neighbors(self):
        from romancer.resource_forms import script_schema
        from romancer.script import inspect_script,plan_script
        from romancer.script_patch import apply_script
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'own.resource';source.write_bytes(b'\x08\x00GUARD!AB\x00\xff\xff\xff\xff\xffTAIL')
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            schema=script_schema(source,sha,{'system_id':'gba','offset':8,'capacity':8,'count':1,'stride':8,'pointer_offset':0,'pointer_width':2,'pointer_endian':'little','pointer_base':0,'terminator':0,'padding':255,'encoding':'ascii','table':'','controls':[]})
            doc=inspect_script(source,schema);self.assertTrue(doc['write_supported'],doc)
            edits={'schema_version':1,'document_id':doc['document_id'],'source_sha256':sha,'schema_sha256':doc['schema_sha256'],'changes':[{'record_id':'line-0','segment':0,'text':'BA'}]}
            out=root/'out';result=apply_script(source,out,schema,edits,expected_plan_id=plan_script(source,schema,edits)['plan_id']);self.assertTrue(result['ok'],result)
            self.assertEqual(out.read_bytes(),b'\x08\x00GUARD!BA\x00\xff\xff\xff\xff\xffTAIL')
            with self.assertRaises(ValueError):script_schema(source,'0'*64,{'system_id':'gba'})

    def test_system_graphics_templates_change_literal_first_pixel(self):
        from romancer.resource_forms import graphics_schema
        from romancer.assets import inspect_assets,plan_assets
        from romancer.asset_patch import apply_assets
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for system,want in [('nes',b'\x80'),('snes',b'\x80'),('genesis',b'\x10'),('segacd',b'\x10'),('gba',b'\x01')]:
                with self.subTest(system=system):
                    source=root/system;source.write_bytes(b'GUARD!!!'+bytes(64)+b'TAIL');sha=hashlib.sha256(source.read_bytes()).hexdigest()
                    schema=graphics_schema(source,sha,{'system_id':system,'offset':8,'count':1})
                    doc=inspect_assets(source,schema);bitmap=doc['bitmaps'][0];before=bitmap['cells'][0]['pixels'];after=before.copy();after[0]=1
                    edits={'schema_version':1,'document_id':doc['document_id'],'changes':[{'kind':'cell','bitmap_id':'tiles','cell_index':0,'before_pixels':before,'after_pixels':after}],'acknowledged_consumers':[]}
                    out=root/(system+'-out');result=apply_assets(source,out,schema,edits,expected_plan_id=plan_assets(source,schema,edits)['plan_id']);self.assertTrue(result['ok'],result)
                    self.assertEqual(out.read_bytes(),b'GUARD!!!'+want+bytes(63)+b'TAIL')

    def test_declared_font_palette_and_map_bind_exact_extents(self):
        from romancer.resource_forms import graphics_schema,font_schema_from_assets
        from romancer.assets import inspect_assets,plan_assets
        from romancer.font_metrics import measure_font
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'font';source.write_bytes(bytes.fromhex('8000000000000000')+b'\x06'+bytes(55))
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            schema=graphics_schema(source,sha,{'system_id':'gba','offset':0,'count':1,'codec':'mono-row-msb-v1','font_chars':'A','advance_offset':8})
            font=font_schema_from_assets(schema);measured=measure_font(source,font)
            self.assertTrue(measured['ok'],measured);self.assertEqual(measured['glyphs'][0]['advance_pixels'],6)
            with self.assertRaises(ValueError):graphics_schema(source,sha,{'system_id':'snes','offset':40,'count':2})

    def test_image_mapping_requires_explicit_conversion_and_reports_changes(self):
        from romancer.resource_forms import image_to_cells
        from PIL import Image
        import io
        image=Image.new('RGB',(8,8),(255,255,255));image.putpixel((0,0),(250,250,250));data=io.BytesIO();image.save(data,format='PNG')
        palette=[{'r':0,'g':0,'b':0},{'r':255,'g':255,'b':255}]
        with self.assertRaises(ValueError):image_to_cells(data.getvalue(),8,8,1,1,palette,'exact')
        mapped=image_to_cells(data.getvalue(),8,8,1,1,palette,'nearest')
        self.assertEqual(mapped['cells'],[[1]*64]);self.assertEqual(mapped['converted_pixels'],1)

    def test_guided_font_layout_and_menu_execute_existing_measurements(self):
        from romancer.resource_forms import script_schema,graphics_schema,font_schema_from_assets,layout_policy,menu_configuration
        from romancer.script import inspect_script
        from romancer.dialogue_layout import check_layout
        from romancer.menu import preview_menu
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'text';source.write_bytes(b'\x08\x00GUARD!AB\x00\xff\xff\xff\xff\xffTAIL')
            schema=script_schema(source,hashlib.sha256(source.read_bytes()).hexdigest(),{'system_id':'nes','offset':8,'capacity':8,'count':1,'pointer_offset':0,'encoding':'table','table':'41=A\n42=B'})
            path=root/'font';path.write_bytes(bytes(16)+b'\x06\x06')
            assets=graphics_schema(path,hashlib.sha256(path.read_bytes()).hexdigest(),{'system_id':'nes','offset':0,'count':2,'codec':'mono-row-msb-v1','font_chars':'AB','advance_offset':16})
            font=font_schema_from_assets(assets);doc=inspect_script(source,schema);policy=layout_policy(doc,schema,font,32,16,8)
            layout=check_layout(source,schema,path,font,policy);self.assertTrue(layout['ok'],layout)
            menu=menu_configuration(schema,font,32,16,8);preview=preview_menu(source,schema,menu['profile'],menu['cases'],font,path)
            self.assertTrue(preview['ok'],preview);self.assertEqual(preview['preview_status'],'PASS')
