import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI


DEFAULTS = {'theme':'romancer','scale':100,'autoDeepScan':True,'autoGraphics':True,
            'rememberWorkspace':True,'volume':80,'startMuted':False,'loopPreview':False,
            'reduceMotion':False,'advancedTools':False,'checkUpdates':True}
LOCATION = {'version':1,'project_id':'a'*32,'artifact_id':'b'*32,'sha256':'c'*64,
            'page':'resources','offset':16,'selected':18,'scroll':20.5,
            'assetPage':0,'scriptPage':1,'catalogPage':0,'catalogQuery':'font'}


class AppSettingsTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.api=WorkbenchAPI(self.root);self.addCleanup(lambda:self.api.close())

    def test_defaults_are_whitelisted_and_durable_values_survive_new_server(self):
        result=self.api.dispatch('settings.get',{});self.assertTrue(result['ok'],result)
        self.assertEqual(result['revision'],0);self.assertEqual(result['values'],DEFAULTS)
        self.assertFalse((self.root/'settings.json').exists())
        values={**DEFAULTS,'theme':'light','scale':150,'autoDeepScan':False,'volume':23}
        saved=self.api.dispatch('settings.save',{'revision':0,'values':values});self.assertTrue(saved['ok'],saved)
        self.assertEqual(saved['revision'],1)
        self.api.close();self.api=WorkbenchAPI(self.root)
        self.assertEqual(self.api.dispatch('settings.get',{})['values'],values)
        stored=json.loads((self.root/'settings.json').read_bytes());self.assertEqual(stored['values'],values)
        self.assertEqual(set(stored),{'schema_version','revision','values'})

    def test_invalid_and_stale_saves_preserve_the_exact_previous_file(self):
        self.assertTrue(self.api.dispatch('settings.save',{'revision':0,'values':DEFAULTS})['ok'])
        before=(self.root/'settings.json').read_bytes()
        invalid=[{**DEFAULTS,'theme':'<script>'},{**DEFAULTS,'volume':101},{**DEFAULTS,'volume':True},
                 {**DEFAULTS,'scale':75},{**DEFAULTS,'autoDeepScan':'true'},
                 {**DEFAULTS,'rom_path':'C:/private/game.gb'},{k:v for k,v in DEFAULTS.items() if k!='theme'}]
        for values in invalid:
            with self.subTest(values=values):
                self.assertFalse(self.api.dispatch('settings.save',{'revision':1,'values':values})['ok'])
                self.assertEqual((self.root/'settings.json').read_bytes(),before)
        for revision in [0,-1,True,1.5,2**53]:
            self.assertFalse(self.api.dispatch('settings.save',{'revision':revision,'values':DEFAULTS})['ok'])
            self.assertEqual((self.root/'settings.json').read_bytes(),before)

    def test_concurrent_requests_have_one_revision_winner(self):
        def save(index):return self.api.dispatch('settings.save',{'revision':0,'values':{**DEFAULTS,'volume':index}})
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(save,range(8)))
        self.assertEqual(sum(bool(result['ok']) for result in results),1,results)
        actual=self.api.dispatch('settings.get',{});self.assertEqual(actual['revision'],1)
        self.assertEqual(json.loads((self.root/'settings.json').read_bytes())['values'],actual['values'])

    def test_failed_atomic_replace_and_corrupt_metadata_never_reset_saved_values(self):
        self.assertTrue(self.api.dispatch('settings.save',{'revision':0,'values':DEFAULTS})['ok'])
        before=(self.root/'settings.json').read_bytes()
        with patch('romancer.workbench_projects.os.replace',side_effect=OSError('disk unavailable')):
            self.assertFalse(self.api.dispatch('settings.save',{'revision':1,'values':{**DEFAULTS,'theme':'dark'}})['ok'])
        self.assertEqual((self.root/'settings.json').read_bytes(),before);self.assertEqual(list(self.root.glob('.metadata-*')),[])
        (self.root/'settings.json').write_text('{broken',encoding='utf-8');broken=(self.root/'settings.json').read_bytes()
        self.assertFalse(self.api.dispatch('settings.get',{})['ok'])
        self.assertFalse(self.api.dispatch('settings.save',{'revision':0,'values':DEFAULTS})['ok'])
        self.assertEqual((self.root/'settings.json').read_bytes(),broken)

    def test_workspace_resume_is_only_bounded_metadata_and_survives_new_server(self):
        self.assertEqual(self.api.dispatch('settings.workspace.get',{}),{'ok':True,'location':None})
        self.assertTrue(self.api.dispatch('settings.workspace.save',{'location':LOCATION})['ok'])
        self.api.close();self.api=WorkbenchAPI(self.root)
        self.assertEqual(self.api.dispatch('settings.workspace.get',{})['location'],LOCATION)
        before=(self.root/'workspace-location.json').read_bytes()
        invalid=[{**LOCATION,'path':'C:/secret.gb'},{**LOCATION,'project_id':'../bad'},
                 {**LOCATION,'artifact_id':'a'*64},{**LOCATION,'sha256':'bad'},{**LOCATION,'page':'external'},
                 {**LOCATION,'scroll':float('inf')},{**LOCATION,'offset':64*1024**2+1},
                 {**LOCATION,'selected':True},{**LOCATION,'assetPage':100001},{**LOCATION,'catalogQuery':'x'*257}]
        for location in invalid:
            with self.subTest(location=location):
                self.assertFalse(self.api.dispatch('settings.workspace.save',{'location':location})['ok'])
                self.assertEqual((self.root/'workspace-location.json').read_bytes(),before)
        self.assertTrue(self.api.dispatch('settings.workspace.save',{'location':None})['ok'])
        self.assertIsNone(self.api.dispatch('settings.workspace.get',{})['location'])

    def test_connected_game_view_can_be_saved_and_restored_as_workspace_location(self):
        location={**LOCATION,'page':'gameview'}
        saved=self.api.dispatch('settings.workspace.save',{'location':location});self.assertTrue(saved['ok'],saved)
        self.assertEqual(self.api.dispatch('settings.workspace.get',{})['location'],location)


if __name__=='__main__':unittest.main()
