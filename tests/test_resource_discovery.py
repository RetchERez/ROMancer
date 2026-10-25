"""Independent strings, pointer bytes and fixed text output for discovery."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


class DiscoveryTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.resource_discovery'),'bounded resource discovery is missing')
        from romancer import resource_discovery
        return resource_discovery

    def test_printable_run_crosses_read_boundary_and_grants_no_write_authority(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';raw=b'\0'*65532+b'HELLO BOUNDARY\0'+b'\0'*20;path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            result=service.discover(path,sha,'gb',0,len(raw),['text'])
            row=next(row for row in result['candidates'] if row['offset']==65532)
            self.assertEqual(row['preview'],'HELLO BOUNDARY');self.assertEqual(row['confidence'],'possible')
            self.assertEqual(result['source_sha256'],sha);self.assertFalse(result['write_authorized'])
            self.assertEqual(row['config']['pointer_offset'],None)

    def test_explicit_pointer_endian_base_and_target(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pointers';raw=bytearray(64);raw[5:7]=b'\x20\x80';raw[13:16]=b'\x01\x00\x20';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            rows=service.pointer_references(path,sha,target=32,width=2,endian='little',base=0x8000,start=0,length=64)
            self.assertEqual([row['offset'] for row in rows], [5]);self.assertEqual(rows[0]['target_offset'],32)
            rows=service.pointer_references(path,sha,target=32,width=3,endian='big',base=0x10000,start=0,length=64)
            self.assertEqual([row['offset'] for row in rows],[13])
            with self.assertRaises(ValueError):service.pointer_references(path,sha,target=65,width=2,endian='little',base=0,start=0,length=64)

    def test_nes_chr_region_is_format_derived_not_guessed(self):
        service=self.service()
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder:
            raw=make_boot_fixture('nes')['data'];path=Path(folder)/'wrong.extension';path.write_bytes(raw)
            result=service.discover(path,hashlib.sha256(raw).hexdigest(),'nes',0,len(raw),['graphics'])
            row=next(row for row in result['candidates'] if row['confidence']=='format-derived')
            self.assertEqual(row['offset'],16400);self.assertEqual(row['format'],'tile8-planar2-msb-v1')
            self.assertEqual(row['config']['count'],16);self.assertFalse(result['runtime_verified'])

    def test_scan_range_limits_stale_source_and_cancellation(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';path.write_bytes(b'\0'*64+b'FINAL STRING\0');sha=hashlib.sha256(path.read_bytes()).hexdigest()
            result=service.discover(path,sha,'gb',0,32,['text'])
            self.assertTrue(result['partial']);self.assertEqual(result['next_offset'],32)
            with self.assertRaises(ValueError):service.discover(path,sha,'gb',0,16*1024**2+1,['text'])
            with self.assertRaises(ValueError):service.discover(path,'0'*64,'gb',0,32,['text'])
            with self.assertRaises(KeyboardInterrupt):service.discover(path,sha,'gb',0,32,['text'],cancelled=lambda:True)

    def test_pointerless_text_declaration_build_preserves_entire_output(self):
        self.service()
        from romancer.workbench_api import WorkbenchAPI
        from romancer.boot_fixtures import make_boot_fixture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'text.gb';raw=bytearray(make_boot_fixture('gb')['data']);raw[0x300:0x308]=b'HELLO\0\xff\xff';path.write_bytes(raw)
            api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Pointerless'});source=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(path),'system':None});params={'project_id':project['project_id'],'artifact_id':source['artifact_id']}
                declared=api.dispatch('resources.declare_script',{**params,'config':{'system_id':'gb','offset':0x300,'capacity':8,'count':1,'stride':8,'encoding':'ascii'}})
                self.assertTrue(declared['ok'],declared);self.assertEqual(declared['schema']['format']['pointers'],[])
                document=declared['inspection'];edits={'schema_version':1,'document_id':document['document_id'],'source_sha256':document['source_sha256'],'schema_sha256':document['schema_sha256'],'changes':[{'record_id':'line-0','segment':0,'text':'WORLD'}]}
                plan=api.dispatch('script.plan',{**params,'schema':declared['schema'],'edits':edits});self.assertTrue(plan['ok'],plan)
                build=api.dispatch('structured.apply',{'project_id':project['project_id'],'plan_id':plan['workbench_plan_id']});self.assertTrue(build['ok'],build)
                expected=bytearray(raw);expected[0x300:0x305]=b'WORLD';expected[0x14d]=(-sum(expected[0x134:0x14d])-25)&255;expected[0x14e:0x150]=b'\0\0';expected[0x14e:0x150]=sum(expected).to_bytes(3,'big')[-2:]
                self.assertEqual(Path(build['path']).read_bytes(),expected);self.assertEqual(path.read_bytes(),raw)
            finally:api.close()
