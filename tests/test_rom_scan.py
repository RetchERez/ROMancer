import json
from pathlib import Path
import tempfile
import time
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI
from romancer.boot_fixtures import make_boot_fixture


class RomScanTests(unittest.TestCase):


    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.api=WorkbenchAPI(self.root/'workspace');self.addCleanup(self.api.close)
        self.p=self.api.dispatch('project.create',{'name':'Scan test'})
        raw=bytearray(make_boot_fixture('nes')['data']);raw[0x3000:0x3010]=b'HELLO SCANNER\0\0\0'
        self.file=self.root/'original.nes';self.file.write_bytes(raw)
        self.source=self.api.dispatch('source.import',{'project_id':self.p['project_id'],'path':str(self.file),'system':None})
        self.params={'project_id':self.p['project_id'],'artifact_id':self.source['artifact_id']}

    def result(self,start):
        if start['status']=='READY':return start['result']
        for _ in range(300):
            job=self.api.dispatch('jobs.get',{'job_id':start['job_id']})
            if job['status'] in ('COMPLETED','FAILED','CANCELLED'):
                self.assertEqual(job['status'],'COMPLETED',job);return job['result']
            time.sleep(.01)
        self.fail('scan did not finish')

    def test_import_starts_scan_and_cached_reopen_preserves_original(self):
        self.assertIn('scan',self.source,'import must launch analysis automatically')
        result=self.result(self.source['scan']);self.assertTrue(result['ok'],result)
        self.assertEqual(result['source_sha256'],self.source['sha256']);self.assertFalse(result['write_authorized'])
        self.assertEqual(result['coverage']['file_bytes_read'],self.source['size'])
        self.assertTrue(any('HELLO SCANNER' in c['preview'] for c in result['candidates']))
        self.assertEqual(result['graphics_index']['runtime_status'],'WAITING_FOR_GAMEPLAY')
        self.assertGreater(result['graphics_index']['sampled_cells'],0)
        self.assertFalse(result['graphics_index']['write_authorized'])
        self.assertEqual(result['identification']['status'],'UNSUPPORTED','a filename or system header does not establish game identity')
        with patch('romancer.rom_scan.discover',side_effect=AssertionError('cached reopen rescanned')):
            cached=self.api.dispatch('rom.scan.start',{**self.params,'rescan':False})
            self.assertEqual(cached['status'],'READY',cached)
        self.assertEqual(self.file.read_bytes(),Path(self.source['path']).read_bytes())

    def test_catalog_change_invalidates_cache_and_identifies_exact_revision(self):
        self.result(self.source['scan'])
        reference=self.root/'catalog.json';reference.write_text(json.dumps([{'name':'Original scanner fixture','size':self.source['size'],'sha256':self.source['sha256']}]))
        imported=self.api.dispatch('inputs.import',{'project_id':self.p['project_id'],'path':str(reference),'name':reference.name,'kind':'catalog'})
        catalog=self.api.dispatch('revision.import',{'project_id':self.p['project_id'],'input_id':imported['input_id'],'scope':'file'})
        self.assertTrue(catalog['ok'],catalog);self.assertNotIn((self.p['project_id'],self.source['artifact_id']),self.api.rom_scans)
        changed=self.api.dispatch('rom.scan.start',{**self.params,'rescan':False});result=self.result(changed)
        self.assertEqual(result['catalog']['file']['status'],'MATCHED');self.assertEqual(result['catalog']['file']['matches'][0]['name'],'Original scanner fixture')

    def test_tampered_source_and_invalid_rescan_refuse(self):
        self.result(self.source['scan'])
        self.assertFalse(self.api.dispatch('rom.scan.start',{**self.params,'rescan':'yes'})['ok'])
        Path(self.source['path']).write_bytes(b'changed')
        self.assertFalse(self.api.dispatch('rom.scan.start',{**self.params,'rescan':False})['ok'])

    def test_cancelled_run_publishes_no_cache(self):
        self.result(self.source['scan'])
        result=self.api.dispatch('rom.scan.run',self.params,cancelled=lambda:True)
        self.assertEqual(result['status'],'CANCELLED')

    def test_invalid_cache_is_rebuilt(self):
        self.result(self.source['scan'])
        from romancer.rom_scan import cache_path
        from romancer import workbench_projects
        row=workbench_projects.artifact(Path(self.p['path']),self.source['artifact_id'])
        cache_path(Path(self.p['path']),row).write_text('[]')
        started=self.api.dispatch('rom.scan.start',{**self.params,'rescan':False})
        self.assertEqual(started['status'],'RUNNING',started);self.assertTrue(self.result(started)['ok'])

    def test_changed_cache_fields_are_not_used_as_current_scan(self):
        self.result(self.source['scan'])
        from romancer.rom_scan import cache_path
        from romancer import workbench_projects
        row=workbench_projects.artifact(Path(self.p['path']),self.source['artifact_id']);cache=cache_path(Path(self.p['path']),row)
        envelope=json.loads(cache.read_bytes());envelope['report']['coverage']={};envelope['report'].pop('limits');cache.write_text(json.dumps(envelope))
        started=self.api.dispatch('rom.scan.start',{**self.params,'rescan':False});self.assertEqual(started['status'],'RUNNING',started)
        self.assertIn('segments',self.result(started)['coverage'])

    def test_background_scan_does_not_block_project_reads_or_cancel(self):
        self.result(self.source['scan']);entered=threading.Event();release=threading.Event()
        def slow(*args,**kwargs):entered.set();release.wait(3);return {'ok':True}
        with patch('romancer.rom_scan.run',side_effect=slow):
            start=self.api.dispatch('rom.scan.start',{**self.params,'rescan':True});self.assertTrue(entered.wait(2))
            try:
                with ThreadPoolExecutor() as pool:
                    opened=pool.submit(self.api.dispatch,'project.open',{'project_id':self.p['project_id']}).result(timeout=.5)
                self.assertTrue(opened['ok']);self.assertTrue(self.api.dispatch('jobs.cancel',{'job_id':start['job_id']})['ok'])
            finally:release.set()
