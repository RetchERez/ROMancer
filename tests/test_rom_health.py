import hashlib
from pathlib import Path
import tempfile
import unittest
import zlib
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI


class RomHealthTests(unittest.TestCase):
    def test_api_budget_and_cancel_precede_all_source_hashing(self):
        from romancer import workbench_projects as projects
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder)/'workspace')
            try:
                project=api.dispatch('project.demo_system',{'system_id':'nes'});row=project['sources'][0]
                path=Path(row['path'])
                with path.open('r+b') as stream:stream.truncate(64*1024**2+1)
                params={'project_id':project['project_id'],'artifact_id':row['artifact_id'],'expected_crc32':'','crc_scope':'file'}
                with patch.object(projects,'_measure',side_effect=AssertionError('unbounded preliminary hash')):
                    value=api.dispatch('rom.check',params)
                    self.assertFalse(value['ok']);self.assertIn('64 MiB',value['error'])
                with path.open('r+b') as stream:stream.truncate(24592)
                with patch.object(projects,'_measure',side_effect=AssertionError('uncancellable preliminary hash')):
                    self.assertEqual(api.dispatch('rom.check',params,cancelled=lambda:True)['status'],'CANCELLED')
            finally:api.close()

    def run_health(self,raw,expected='',scope='file'):
        from romancer.rom_health import check_rom
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cart.bin';path.write_bytes(raw)
            return check_rom(path,hashlib.sha256(raw).hexdigest(),expected,scope)

    def test_literal_crc_reference_match_mismatch_and_no_reference(self):
        value=self.run_health(b'123456789');self.assertEqual(value['crc32'],'CBF43926')
        self.assertEqual(value['crc_comparison']['status'],'NOT_CHECKED')
        self.assertEqual(self.run_health(b'123456789','cbf43926')['crc_comparison']['status'],'PASS')
        mismatch=self.run_health(b'123456789','00000000')
        self.assertEqual(mismatch['crc_comparison']['status'],'FAIL');self.assertEqual(mismatch['status'],'ISSUES_FOUND')
        self.assertFalse(value['runtime_verified']);self.assertEqual(value['system_status'],'UNKNOWN')
        for bad in ('123','0xCBF43926','GGGGGGGG',True):
            with self.assertRaises(ValueError):self.run_health(b'123456789',bad)

    def test_nes_truncation_and_explicit_prg_chr_payload_scope(self):
        raw=b'NES\x1a'+bytes([1,0])+bytes(10)+bytes(16384)
        good=self.run_health(raw);self.assertEqual(good['checks'][0]['status'],'PASS')
        self.assertEqual(self.run_health(raw[:-1])['status'],'ISSUES_FOUND')
        payload=self.run_health(raw,f'{zlib.crc32(raw[16:]):08X}','payload')
        self.assertEqual(payload['crc_comparison']['status'],'PASS')
        self.assertEqual(payload['crc_comparison']['ranges'],[{'offset':16,'length':16384}])
        self.assertNotEqual(payload['crc32'],payload['crc_comparison']['measured'])
        with self.assertRaises(ValueError):self.run_health(b'unknown','','payload')

    def test_console_checksums_detect_mutations_without_changing_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder)/'workspace')
            try:
                for system in ('nes','snes','genesis','gb','gba'):
                    with self.subTest(system=system):
                        project=api.dispatch('project.demo_system',{'system_id':system});row=project['sources'][0]
                        raw=Path(row['path']).read_bytes();params={'project_id':project['project_id'],'artifact_id':row['artifact_id'],'expected_crc32':'','crc_scope':'file'}
                        report=api.dispatch('rom.check',params);self.assertTrue(report['ok'],report)
                        self.assertFalse(any(c['status']=='FAIL' for c in report['checks']),report)
                        self.assertEqual(Path(row['path']).read_bytes(),raw)
                        if system!='nes':
                            changed=bytearray(raw);changed[0x134 if system=='gba' else 0x200]^=1
                            if system=='gba':changed[0xa0]^=1
                            bad=self.run_health(changed)
                            self.assertTrue(any(c['status']=='FAIL' for c in bad['checks']),bad)
                self.assertEqual(api.dispatch('rom.check',params,cancelled=lambda:True)['status'],'CANCELLED')
            finally:api.close()

    def test_snes_copier_header_and_unsupported_checksum_are_explicit(self):
        raw=bytearray(32768);h=0x7fc0;raw[h:h+21]=b'ORIGINAL TEST'.ljust(21,b' ')
        raw[h+21]=0x20;raw[h+23]=5;raw[h+28:h+32]=b'\xff\xff\x00\x00'
        checksum=sum(raw)&65535;raw[h+28:h+32]=(checksum^65535).to_bytes(2,'little')+checksum.to_bytes(2,'little')
        report=self.run_health(bytes(512)+raw);self.assertEqual(next(c for c in report['checks'] if c['name']=='SNES ROM checksum')['status'],'PASS')
        self.assertEqual(report['payload_ranges'],[{'offset':512,'length':32768}])
        # Standard 96 KiB payload declares its next power of two (128 KiB).
        odd=raw+bytes(65536);odd[h+23]=7;odd[-1]=3
        odd[h+28:h+32]=b'\xff\xff\x00\x00'
        expected=(sum(odd[:65536])+2*sum(odd[65536:]))&65535
        odd[h+28:h+32]=(expected^65535).to_bytes(2,'little')+expected.to_bytes(2,'little')
        report=self.run_health(odd)
        self.assertEqual(next(c for c in report['checks'] if c['name']=='SNES ROM checksum')['status'],'PASS')
        odd[-1]^=1
        self.assertEqual(next(c for c in self.run_health(odd)['checks'] if c['name']=='SNES ROM checksum')['status'],'FAIL')
        odd[h+22]=0x13
        self.assertEqual(next(c for c in self.run_health(odd)['checks'] if c['name']=='SNES ROM checksum')['status'],'NOT_CHECKED')

    def test_changed_source_identity_cannot_report_success(self):
        from romancer.rom_health import check_rom
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cart';path.write_bytes(b'123456789')
            with self.assertRaises(ValueError):check_rom(path,'0'*64,'','file')
