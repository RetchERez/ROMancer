import hashlib,tempfile,unittest
from pathlib import Path
from romancer.system_identify import identify_system
from romancer.system_integrity import integrity_edits
from romancer.rom_health import check_rom

class SMSFormatTests(unittest.TestCase):
    def fixture(self,region=4):
        raw=bytearray(32768);raw[0x100:0x105]=b'SCORE';raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=(region<<4)|0xc
        raw[0x7ffa:0x7ffc]=(sum(raw[:0x7ff0])&65535).to_bytes(2,'little');return raw

    def test_recognizes_bounded_sms_header_and_rejects_gamegear_and_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cartridge.sms';path.write_bytes(self.fixture());result=identify_system(path)
            self.assertEqual(result['status'],'IDENTIFIED',result);self.assertEqual(result['system_id'],'sms')
            self.assertEqual(result['candidates'][0]['metadata']['checksum_length'],32768)
            path.write_bytes(self.fixture(6));self.assertNotEqual(identify_system(path)['status'],'IDENTIFIED')
            raw=self.fixture();raw[0x7fff]=0x40;path.write_bytes(raw);self.assertEqual(identify_system(path)['status'],'BLOCKED')

    def test_edit_plan_repairs_sms_checksum_and_protects_header(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cartridge.sms';raw=self.fixture();path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            edits=integrity_edits(path,sha,'sms',[{'offset':0x100,'before':b'SCORE'.hex(),'after':b'POINT'.hex()}])
            self.assertEqual([e['offset'] for e in edits],[0x100,0x7ffa])
            after=bytearray(raw)
            for edit in edits:after[edit['offset']:edit['offset']+len(bytes.fromhex(edit['after']))]=bytes.fromhex(edit['after'])
            self.assertEqual(int.from_bytes(after[0x7ffa:0x7ffc],'little'),sum(after[:0x7ff0])&65535)
            with self.assertRaises(ValueError):integrity_edits(path,sha,'sms',[{'offset':0x7fff,'before':'4c','after':'4f'}])
            self.assertEqual(path.read_bytes(),raw)

    def test_health_reports_checksum_failure_separately_from_unknown_crc_reference(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cartridge.sms';raw=self.fixture();raw[0x100]^=1;path.write_bytes(raw)
            result=check_rom(path,hashlib.sha256(raw).hexdigest());checks=result['checks']
            self.assertTrue(any(c['name']=='Master System ROM checksum' and c['status']=='FAIL' for c in checks),checks)

    def test_512k_checksum_covers_upper_banks_and_recompression_repairs_it(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.resource_compression import encode_stream
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=self.fixture()+bytearray(524288-32768);raw[0x7fff]=0x41
            raw[0x40000:0x4000a]=encode_stream(b'AAAAABCD','rle')
            raw[0x7ffa:0x7ffc]=((sum(raw[:0x7ff0])+sum(raw[0x8000:]))&65535).to_bytes(2,'little')
            source=root/'large.sms';source.write_bytes(raw)
            self.assertEqual(identify_system(source)['candidates'][0]['metadata']['checksum_length'],524288)
            self.assertTrue(any(c['name']=='Master System ROM checksum' and c['status']=='PASS' for c in check_rom(source,hashlib.sha256(raw).hexdigest())['checks']))
            api=WorkbenchAPI(root/'workspace')
            def call(op,**p):
                result=api.dispatch(op,p);self.assertTrue(result.get('ok'),result);return result
            try:
                p={'project_id':call('project.create',name='SMS compression')['project_id']}
                parent=call('source.import',**p,path=str(source),system=None)
                params={**p,'artifact_id':parent['artifact_id'],'offset':0x40000,'allocation':32,'codec':'rle'}
                child=call('compression.extract',**params)['artifact']
                plan=call('bytes.plan',**p,artifact_id=child['artifact_id'],edits=[{'offset':5,'before':'42','after':'5a'}])
                edited=call('build.apply',**p,plan_id=plan['plan_id'])
                reinsert=call('compression.plan_reinsert',**p,parent_id=parent['artifact_id'],decoded_id=child['artifact_id'],edited_id=edited['artifact_id'],offset=0x40000,allocation=32,codec='rle')
                built=call('build.apply',**p,plan_id=reinsert['plan_id']);after=Path(built['path']).read_bytes()
                self.assertEqual(int.from_bytes(after[0x7ffa:0x7ffc],'little'),(sum(after[:0x7ff0])+sum(after[0x8000:]))&65535)
                self.assertEqual(source.read_bytes(),raw)
            finally:api.close()

    def test_basic_deep_scan_returns_graphics_and_unknown_driver_without_inventing_addresses(self):
        from romancer import rom_scan,workbench_projects
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'cartridge.sms';source.write_bytes(self.fixture());project=Path(workbench_projects.create_project(root/'projects','SMS scan')['path']);registered=workbench_projects.register_source(project,source,None);row=workbench_projects.artifact(project,registered['artifact_id'])
            result=rom_scan.run(project,row);self.assertTrue(result['ok']);self.assertEqual(result['system_id'],'sms');self.assertEqual(result['hardware_reference']['cpu'],'Z80');self.assertEqual(result['sound_system']['driver']['status'],'UNKNOWN');self.assertFalse(result['runtime_verified'])
