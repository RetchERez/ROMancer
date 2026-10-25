import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

LZ=bytes.fromhex('10 09 00 00 10 41 42 43 30 02')
RLE=bytes.fromhex('30 08 00 00 82 41 02 42 43 44')


class CompressionTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.resource_compression'),'bounded known-format compression is missing')
        from romancer import resource_compression
        return resource_compression

    def test_literal_lz_overlap_and_rle_streams(self):
        service=self.service()
        for encoded,codec,expected in [(LZ,'gba-lz10',b'ABCABCABC'),(RLE,'gba-rle',b'AAAAABCD')]:
            with self.subTest(codec=codec):
                result=service.decode_stream(encoded+b'UNRELATED',codec)
                self.assertEqual(result['data'],expected);self.assertEqual(result['consumed'],len(encoded))
                self.assertEqual(service.decode_stream(service.encode_stream(expected,codec),codec)['data'],expected)

    def test_bad_headers_truncation_backrefs_bombs_and_overruns_refuse(self):
        service=self.service()
        bad=[('gba-lz10',LZ[:-1]),('gba-lz10',bytes.fromhex('10 08 00 00 80 00 00')),('gba-lz10',bytes.fromhex('10 ff ff ff')),
             ('gba-rle',RLE[:-1]),('gba-rle',bytes.fromhex('30 01 00 00 ff 41')),('gba-rle',b'wrong')]
        for codec,raw in bad:
            with self.subTest(raw=raw),self.assertRaises(ValueError):service.decode_stream(raw,codec)
        with self.assertRaises(ValueError):service.encode_stream(b'','gba-lz10')
        with self.assertRaises(ValueError):service.decode_stream(LZ,'guessed-format')

    def test_encoders_cover_literal_groups_runs_and_window_boundaries(self):
        service=self.service()
        values=[bytes(range(256))*3,b'A'*9000,b'ABCD'*2000,bytes((index*37+index//17)&255 for index in range(6000))]
        for codec in ('gba-lz10','gba-rle'):
            for raw in values:
                encoded=service.encode_stream(raw,codec);self.assertEqual(service.decode_stream(encoded,codec)['data'],raw)
                self.assertEqual(encoded,service.encode_stream(raw,codec))
        self.assertLess(len(service.encode_stream(b'ABCD'*2000,'gba-lz10')),1100)

    def test_discovery_validates_streams_without_granting_resource_authority(self):
        service=self.service();rows=service.compression_candidates(b'\0'*8+LZ+b'\xff'*10,0)
        self.assertEqual(rows[0]['offset'],8);self.assertEqual(rows[0]['decoded_size'],9)
        self.assertEqual(rows[0]['confidence'],'validated-format');self.assertNotIn('config',rows[0])

    def test_discovery_probe_limit_reports_where_to_continue(self):
        service=self.service();budget={}
        rows=service.compression_candidates(bytes.fromhex('30 08 00 00 ff 41 00 00')*129,0,budget=budget)
        self.assertEqual(rows,[]);self.assertTrue(budget['partial']);self.assertEqual(budget['next_offset'],1024)

    def test_owned_extract_edit_reinsert_whole_parent_oracle_and_growth_refusal(self):
        service=self.service()
        from romancer.workbench_api import WorkbenchAPI
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=bytearray(make_boot_fixture('gba')['data']);raw[0x500:0x500+len(RLE)]=RLE;source=root/'compressed.gba';source.write_bytes(raw)
            api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Compressed resource'});parent=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(source),'system':None});params={'project_id':project['project_id'],'artifact_id':parent['artifact_id'],'offset':0x500,'allocation':32,'codec':'gba-rle'}
                inspected=api.dispatch('compression.inspect',params);self.assertTrue(inspected['ok'],inspected);self.assertEqual(inspected['decoded_size'],8)
                extracted=api.dispatch('compression.extract',params);self.assertTrue(extracted['ok'],extracted);child=extracted['artifact'];self.assertEqual(Path(child['path']).read_bytes(),b'AAAAABCD')
                edits=api.dispatch('bytes.plan',{'project_id':project['project_id'],'artifact_id':child['artifact_id'],'edits':[{'offset':5,'before':'42','after':'5a'}]});edited=api.dispatch('build.apply',{'project_id':project['project_id'],'plan_id':edits['plan_id']});self.assertTrue(edited['ok'],edited)
                arguments={'project_id':project['project_id'],'parent_id':parent['artifact_id'],'decoded_id':child['artifact_id'],'edited_id':edited['artifact_id'],'offset':0x500,'allocation':32,'codec':'gba-rle'}
                real_read=Path.read_bytes
                def changed_read(selected):
                    return b'AAAAAYCD' if selected==Path(edited['path']) else real_read(selected)
                with patch.object(Path,'read_bytes',changed_read),self.assertRaisesRegex(ValueError,'identity'):
                    service.plan_reinsert(Path(project['path']),parent['artifact_id'],child['artifact_id'],edited['artifact_id'],0x500,32,'gba-rle')
                planned=api.dispatch('compression.plan_reinsert',arguments);self.assertTrue(planned['ok'],planned);self.assertTrue(planned['independent_decode_verified'])
                built=api.dispatch('build.apply',{'project_id':project['project_id'],'plan_id':planned['plan_id']});self.assertTrue(built['ok'],built)
                expected=bytearray(raw);expected[0x507]=ord('Z');self.assertEqual(Path(built['path']).read_bytes(),expected)
                self.assertEqual(source.read_bytes(),raw)
                rejected=api.dispatch('compression.plan_reinsert',{**arguments,'allocation':8});self.assertFalse(rejected['ok'])
                tight=api.dispatch('compression.extract',{**params,'allocation':10})['artifact']
                replacement=api.dispatch('bytes.plan',{'project_id':project['project_id'],'artifact_id':tight['artifact_id'],'edits':[{'offset':0,'before':b'AAAAABCD'.hex(),'after':b'ABCDEFGH'.hex()}]})
                tight_build=api.dispatch('build.apply',{'project_id':project['project_id'],'plan_id':replacement['plan_id']})
                too_large=api.dispatch('compression.plan_reinsert',{**arguments,'decoded_id':tight['artifact_id'],'edited_id':tight_build['artifact_id'],'allocation':10})
                self.assertFalse(too_large['ok']);self.assertIn('fit',too_large['error'])
                project_path=Path(project['path']);value=bytearray(Path(parent['path']).read_bytes());value[-1]^=1;Path(parent['path']).write_bytes(value)
                with self.assertRaises(ValueError):service.plan_reinsert(project_path,parent['artifact_id'],child['artifact_id'],edited['artifact_id'],0x500,32,'gba-rle')
            finally:api.close()
