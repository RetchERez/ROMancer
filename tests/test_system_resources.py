import hashlib
from pathlib import Path
import tempfile
import unittest
from tests.test_system_identify import nes_bytes


class NESResourceTests(unittest.TestCase):
    def test_nes_chr_tile_page_and_complete_output_oracle(self):
        from romancer.system_resources import describe_nes_chr
        from romancer.assets import inspect_assets,plan_assets
        from romancer.asset_patch import apply_assets
        from romancer.release import prepare_patch,apply_bps
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=bytearray(nes_bytes(trainer=True));chr_start=16+512+16384
            page=chr_start+16*16;raw[page]=0x80;source=root/'original Ω.nes';source.write_bytes(raw)
            sha=hashlib.sha256(raw).hexdigest();described=describe_nes_chr(source,expected_sha256=sha,first_tile=16,count=16)
            self.assertTrue(described['ok'],described);schema=described['schema']
            self.assertEqual(schema['bitmaps'][0]['offset'],page);self.assertEqual(schema['palettes'],[])
            doc=inspect_assets(source,schema);self.assertTrue(doc['ok'],doc);pixels=doc['bitmaps'][0]['cells'][0]['pixels']
            self.assertEqual(pixels[0],1);after=list(pixels);after[0]=3
            request={'schema_version':1,'document_id':doc['document_id'],'changes':[{'kind':'cell','bitmap_id':'nes-chr-page',
                'cell_index':0,'before_pixels':pixels,'after_pixels':after}],'acknowledged_consumers':[]}
            plan=plan_assets(source,schema,request);self.assertTrue(plan['ok'],plan)
            target=root/'target.nes';result=apply_assets(source,target,schema,request,expected_plan_id=plan['plan_id'])
            self.assertTrue(result['ok'],result);expected=bytearray(raw);expected[page+8]=0x80
            self.assertEqual(target.read_bytes(),bytes(expected));self.assertEqual(source.read_bytes(),bytes(raw))
            rebound=describe_nes_chr(target,expected_sha256=hashlib.sha256(expected).hexdigest(),first_tile=16,count=16)
            self.assertEqual(inspect_assets(target,rebound['schema'])['bitmaps'][0]['cells'][0]['pixels'][0],3)
            patch=root/'target.bps';prepared=prepare_patch(source,target,patch,{'title':'Original NES tool fixture','description':''})
            self.assertTrue(prepared['ok'],prepared);self.assertEqual(apply_bps(bytes(raw),patch.read_bytes()),bytes(expected))

    def test_chr_ram_invalid_page_stale_hash_and_bool_inputs_refuse(self):
        from romancer.system_resources import describe_nes_chr
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'fixture.nes';source.write_bytes(nes_bytes());sha=hashlib.sha256(source.read_bytes()).hexdigest()
            for first,count in ((True,1),(0,True),(-1,1),(512,1),(511,2),(0,65),(0,0)):
                with self.subTest(first=first,count=count):self.assertFalse(describe_nes_chr(source,expected_sha256=sha,first_tile=first,count=count)['ok'])
            self.assertFalse(describe_nes_chr(source,expected_sha256='0'*64)['ok'])
            source.write_bytes(nes_bytes(chr_units=0));sha=hashlib.sha256(source.read_bytes()).hexdigest()
            result=describe_nes_chr(source,expected_sha256=sha);self.assertFalse(result['ok']);self.assertIn('CHR-ROM',result['error'])
            with source.open('wb') as stream:stream.write(nes_bytes());stream.seek(64*1024**2);stream.write(b'X')
            digest=hashlib.sha256()
            with source.open('rb') as stream:
                while data:=stream.read(65536):digest.update(data)
            result=describe_nes_chr(source,expected_sha256=digest.hexdigest());self.assertFalse(result['ok']);self.assertIn('64 MiB',result['error'])

    def test_api_demo_uses_regular_structured_build_and_reopen(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp))
            try:
                demo=api.dispatch('project.demo_nes',{});self.assertTrue(demo['ok'],demo)
                row=demo['sources'][0];p={'project_id':demo['project_id'],'artifact_id':row['artifact_id']}
                described=api.dispatch('systems.nes_chr',{**p,'first_tile':16,'count':16});self.assertTrue(described['ok'],described)
                reopened=api.dispatch('project.open',{'project_id':demo['project_id']});schema=reopened['sources'][0]['descriptors']['assets']
                self.assertEqual(schema['bitmaps'][0]['offset'],16+16384+16*16)
                document=api.dispatch('assets.inspect',{**p,'schema':schema});self.assertTrue(document['ok'],document)
                cell=document['bitmaps'][0]['cells'][0];after=list(cell['pixels']);after[0]=(after[0]+1)%4
                edits={'schema_version':1,'document_id':document['document_id'],'changes':[{'kind':'cell','bitmap_id':'nes-chr-page',
                    'cell_index':0,'before_pixels':cell['pixels'],'after_pixels':after}],'acknowledged_consumers':[]}
                plan=api.dispatch('assets.plan',{**p,'schema':schema,'edits':edits});self.assertTrue(plan['ok'],plan)
                build=api.dispatch('structured.apply',{'project_id':demo['project_id'],'plan_id':plan['workbench_plan_id']})
                self.assertTrue(build['ok'],build)
                fresh=api.dispatch('systems.identify',{'project_id':demo['project_id'],'artifact_id':build['artifact_id']})
                self.assertEqual(fresh['system_id'],'nes',fresh);self.assertFalse(fresh['runtime_verified'])
            finally:api.close()


if __name__=='__main__':unittest.main()
