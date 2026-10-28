import tempfile,unittest
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI


class ReleaseScopeTests(unittest.TestCase):
    def test_only_six_systems_are_exposed_and_other_system_operations_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'workspace')
            try:
                systems=api.dispatch('systems.list',{})
                self.assertEqual({s['id'] for s in systems['systems']},{'nes','snes','genesis','gb','gbc','sms'})
                self.assertFalse(any(op in ('runtime.load_disc','route.run_disc','release.disc_set') or op.startswith('containers.') for op in api.routes))
                blocked=api.dispatch('profiles.get',{'system_id':'unsupported-system'})
                self.assertFalse(blocked['ok']);self.assertIn('six',blocked['error'])
            finally:api.close()

    def test_unknown_bytes_are_rejected_on_import_even_with_a_system_hint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'data.bin';path.write_bytes(b'unidentified data');api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Inspection'});p={'project_id':project['project_id']}
                for hint in (None,'nes','sms'):
                    result=api.dispatch('source.import',{**p,'path':str(path),'system':hint})
                    self.assertFalse(result['ok'],result);self.assertIn('recognized',result['error'])
                self.assertEqual(api.dispatch('project.open',p)['sources'],[])
                from romancer.workbench_projects import register_source
                row=register_source(Path(project['path']),path,None);s={**p,'artifact_id':row['artifact_id']}
                self.assertTrue(api.dispatch('resource.inspect',{**s,'offset':0,'length':4})['ok'])
                blocked=api.dispatch('bytes.plan',{**s,'edits':[{'offset':0,'before':'75','after':'76'}]})
                self.assertFalse(blocked['ok']);self.assertIn('Inspect',blocked['error'])
                with self.assertRaisesRegex(ValueError,'Inspect'):
                    api._runtime_config({**s,'system_id':'nes'})
                with self.assertRaisesRegex(ValueError,'Inspect'):
                    api._route_selection(p,{'kind':'artifact','id':row['artifact_id']})
                with self.assertRaisesRegex(ValueError,'Inspect'):
                    api._audio_capture({**p,'config':{'load':{'game':row['path']}},'format':'wav','baseline':{}},lambda:False)
                with self.assertRaisesRegex(ValueError,'owned supported'):
                    api._audio_capture({**p,'config':{'load':{'game':str(path)}},'format':'wav','baseline':{}},lambda:False)
                with self.assertRaisesRegex(ValueError,'cartridge'):
                    api._runtime_config({**p,'container_id':'0'*32})
            finally:api.close()
