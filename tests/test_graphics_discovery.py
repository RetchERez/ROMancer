import unittest
import base64,hashlib,tempfile
from pathlib import Path
from unittest.mock import patch
from romancer.asset_codecs import encode_cell


class GraphicsDiscoveryTests(unittest.TestCase):
    def test_unknown_game_tiles_match_each_supported_storage_format(self):
        from romancer.graphics_discovery import match_graphics, SYSTEM_CODECS
        pixels=[0 if x<2 or y==0 else 1+(x+y)%3 for y in range(8) for x in range(8)]
        colors=[(3,9,17),(231,63,11),(91,224,177),(210,160,241)]
        for system,codec in SYSTEM_CODECS.items():
            with self.subTest(system=system):
                raw=bytes([255])*7+encode_cell(pixels,codec=codec,width=8,height=8)+bytes([255])*19
                frame=bytearray(bytes(colors[0])*16*16)
                for y in range(8):
                    for x in range(8):
                        at=((y+3)*16+x+5)*3;frame[at:at+3]=bytes(colors[pixels[y*8+x]])
                found=match_graphics(raw,bytes(frame),16,16,system,region={'x':5,'y':3,'width':8,'height':8})
                self.assertTrue(any(m['offset']==7 and m['x']==5 and m['y']==3 and not m['flip_x'] and not m['flip_y'] for m in found['matches']),found)
                self.assertFalse(found['write_authorized']);self.assertFalse(found['provenance_verified'])
                self.assertEqual(found['coverage']['offset_alignment'],1)

    def test_flipped_duplicate_patterns_remain_ambiguous(self):
        from romancer.graphics_discovery import match_graphics
        pixels=[0 if x<2 or y<1 else 1+(x*3+y)%3 for y in range(8) for x in range(8)]
        tile=encode_cell(pixels,codec='tile8-planar2-msb-v1',width=8,height=8);raw=tile+b'\xff'*16+tile
        colors=[(2,2,2),(233,55,11),(33,244,99),(122,55,210)]
        rgb=bytes(v for y in range(8) for x in range(8) for v in colors[pixels[y*8+7-x]])
        result=match_graphics(raw,rgb,8,8,'nes')
        self.assertEqual(len([m for m in result['matches'] if m['offset'] in (0,32) and m['flip_x']]),2,result)
        self.assertFalse(result['unique_source']);self.assertTrue(result['coverage']['whole_requested_range'])
        partial=match_graphics(raw,rgb,8,8,'nes',length=16)
        self.assertFalse(partial['unique_source']);self.assertFalse(partial['coverage']['whole_source'])

    def test_blank_and_collapsed_patterns_are_not_known_sprites(self):
        from romancer.graphics_discovery import match_graphics
        for raw in [b'\0'*64,b'\xff'*64]:
            self.assertEqual(match_graphics(raw,b'\0'*192,8,8,'nes')['matches'],[])
        with self.assertRaises(KeyboardInterrupt):match_graphics(b'\0'*64,b'\0'*192,8,8,'nes',cancelled=lambda:True)
        with self.assertRaises(ValueError):match_graphics(b'\0'*64,b'bad',8,8,'nes')

    def test_nes_eight_by_sixteen_parts_have_independent_plane_pairs(self):
        from romancer.graphics_discovery import match_graphics
        parts=[[1+(x+y+k)%3 if 1<x<7 else 0 for y in range(8) for x in range(8)] for k in (0,1)]
        raw=b'\xff'*5+b''.join(encode_cell(p,codec='tile8-planar2-msb-v1',width=8,height=8) for p in parts)
        colors=[(3,6,9),(200,60,10),(40,220,90),(130,44,222)]
        rgb=bytes(v for p in parts for index in p for v in colors[index])
        found=match_graphics(raw,rgb,8,16,'nes')
        self.assertTrue(any(m['offset']==5 and m['height']==16 for m in found['matches']),found)

    def test_result_limit_reports_examined_bytes_separately_from_loaded_bytes(self):
        from romancer.graphics_discovery import match_graphics
        pixels=[0 if x<2 else 1+(x+y)%3 for y in range(8) for x in range(8)]
        tile=encode_cell(pixels,codec='tile8-planar2-msb-v1',width=8,height=8)
        colors=[(1,2,3),(230,60,10),(40,230,90),(130,40,200)]
        rgb=bytes(v for index in pixels for v in colors[index]);raw=tile*10000
        result=match_graphics(raw,rgb,8,8,'nes')
        self.assertTrue(result['coverage']['matches_truncated'])
        self.assertEqual(result['coverage']['bytes_loaded'],len(raw))
        self.assertLess(result['coverage']['bytes_scanned'],len(raw))

    def test_continued_ranges_include_tiles_crossing_a_window_boundary(self):
        from romancer.graphics_discovery import match_graphics
        pixels=[0 if x<2 else 1+(x+y)%3 for y in range(8) for x in range(8)]
        tile=encode_cell(pixels,codec='tile8-planar2-msb-v1',width=8,height=8)
        colors=[(1,2,3),(230,60,10),(40,230,90),(130,40,200)]
        rgb=bytes(v for index in pixels for v in colors[index]);raw=b'\xff'*24+tile+b'\xff'*40
        with patch('romancer.graphics_discovery.MAX_SOURCE_BYTES',32):
            first=match_graphics(raw,rgb,8,8,'nes')
            second=match_graphics(raw,rgb,8,8,'nes',start=first['coverage']['next_offset'])
        self.assertTrue(any(m['offset']==24 for m in second['matches']),(first,second))


class GraphicsObservationTests(unittest.TestCase):
    def test_observation_binds_owned_source_and_current_native_frame(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.boot_fixtures import make_boot_fixture
        from romancer.workbench_evidence import load_evidence
        pixels=[0 if x<2 else 1+(x+y)%3 for y in range(8) for x in range(8)]
        colors=[(1,2,3),(230,60,10),(40,230,90),(130,40,200)]
        rgb=bytes(v for index in pixels for v in colors[index])
        temp=self.enterContext(tempfile.TemporaryDirectory())
        root=Path(temp);api=WorkbenchAPI(root/'workspace');self.addCleanup(api.close)
        data=bytearray(make_boot_fixture('nes')['data']);data[0x3007:0x3017]=encode_cell(pixels,codec='tile8-planar2-msb-v1',width=8,height=8)
        rom=root/'unknown.nes';rom.write_bytes(data)
        project=api.dispatch('project.create',{'name':'Unknown game'})
        source=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(rom),'system':None})
        frame={'ok':True,'width':8,'height':8,'index':5,'rgb24_base64':base64.b64encode(rgb).decode(),'sha256':hashlib.sha256(rgb).hexdigest(),
               'game_sha256':source['sha256'],'core_sha256':'c'*64,'runtime_identity_sha256':'d'*64,'provenance':{'origin':'cold_boot'}}
        params={'project_id':project['project_id'],'artifact_id':source['artifact_id'],'frame_sha256':frame['sha256'],'region':None,'offset':0x3000,'length':64}
        with patch.object(api.runtime,'request',return_value=frame):
            result=api.dispatch('graphics.observe',params)
        self.assertTrue(result['ok'],result);self.assertTrue(any(m['offset']==0x3007 for m in result['matches']))
        record=load_evidence(Path(project['path']),result['evidence_id'],'runtime')
        self.assertEqual(record['report']['frame']['sha256'],frame['sha256'])
        self.assertFalse(record['report']['provenance_verified'])
        bad={**frame,'game_sha256':'0'*64}
        with patch.object(api.runtime,'request',return_value=bad):self.assertFalse(api.dispatch('graphics.observe',params)['ok'])
        with patch.object(api.runtime,'request',return_value=frame):self.assertFalse(api.dispatch('graphics.observe',{**params,'frame_sha256':'0'*64})['ok'])
        match=next(i for i,m in enumerate(result['matches']) if m['offset']==0x3007 and not m['flip_x'] and not m['flip_y'])
        declared=api.dispatch('graphics.declare',{'project_id':project['project_id'],'artifact_id':source['artifact_id'],'evidence_id':result['evidence_id'],'matches':[match]})
        self.assertTrue(declared['ok'],declared);self.assertEqual(declared['layout']['indices'],[0])
        self.assertEqual(declared['inspection']['source_sha256'],source['sha256'])
        self.assertEqual(declared['layout']['provenance'],'pixel_candidate')

    def test_scattered_layout_preserves_positions_flips_and_gaps(self):
        from romancer.graphics_discovery import candidate_layout
        matches=[{'offset':32,'length':32,'x':8,'y':0,'height':16,'width':8,'flip_x':True,'flip_y':True,'observed_colors':{},'codec':'tile8-planar2-msb-v1'},
                 {'offset':0,'length':16,'x':0,'y':0,'height':8,'width':8,'flip_x':False,'flip_y':False,'observed_colors':{},'codec':'tile8-planar2-msb-v1'}]
        result=candidate_layout({'matches':matches,'system_id':'nes'},[0,1])
        self.assertEqual(result['layout']['indices'],[0,3,None,2])
        self.assertEqual(result['layout']['flips'],[0,3,0,3])
        with self.assertRaises(ValueError):candidate_layout({'matches':matches,'system_id':'nes'},[0,0])

    def test_sparse_declaration_span_uses_the_same_budget_as_the_asset_engine(self):
        from romancer.graphics_discovery import candidate_layout
        from romancer.resource_forms import graphics_schema
        matches=[{'offset':o,'length':16,'x':x,'y':0,'height':8,'width':8,'flip_x':False,'flip_y':False,'observed_colors':{},'codec':'tile8-planar2-msb-v1'} for o,x in [(0,0),(8192,8)]]
        view=candidate_layout({'matches':matches,'system_id':'nes'},[0,1])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'data.bin';path.write_bytes(bytes(range(256))*64)
            schema=graphics_schema(path,hashlib.sha256(path.read_bytes()).hexdigest(),view['config'])
            self.assertEqual(schema['bitmaps'][0]['count'],513)
