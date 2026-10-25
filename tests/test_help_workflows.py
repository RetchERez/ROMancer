"""Literal task guidance and progress facts for the offline product shell."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


class HelpWorkflowTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.help_content'), 'offline help service is missing')
        from romancer import help_content
        return help_content

    def test_searchable_offline_tasks_and_systems_have_actionable_steps(self):
        service=self.service();result=service.help_topics('', 'graphics')
        self.assertGreaterEqual(len(result['topics']),17)
        self.assertEqual(result['selected']['id'],'graphics')
        self.assertGreaterEqual(len(result['selected']['steps']),3)
        found=service.help_topics('POINTER','')
        self.assertTrue(any(row['id']=='tables' for row in found['topics']))
        self.assertIsNone(service.help_topics('', '../../untrusted')['selected'])
        with self.assertRaises(ValueError):service.help_topics('x'*161,'')

    def test_readiness_never_confuses_prepared_exports_with_verified_patches(self):
        service=self.service();project={'sources':[],'builds':[]}
        empty=service.project_readiness(project,[],False,[])
        self.assertFalse(any(row['complete'] for row in empty['steps']))
        project={'sources':[{'artifact_id':'source','descriptors':{'assets':{}}}],'builds':[{'artifact_id':'build'}]}
        exports=[{'export_id':'patch','role':'patch','sha256':'a'*64}]
        ready=service.project_readiness(project,exports,True,[])
        rows={row['id']:row for row in ready['steps']}
        self.assertTrue(rows['build']['complete']);self.assertTrue(rows['setup']['complete'])
        self.assertFalse(rows['verify']['complete'])
        verified=service.project_readiness(project,exports,True,['patch'])
        self.assertTrue(next(row for row in verified['steps'] if row['id']=='verify')['complete'])
        self.assertFalse(verified['game_compatibility_claimed'])

    def test_api_help_and_project_checklist_run_with_network_unavailable(self):
        self.service()
        from romancer.workbench_api import WorkbenchAPI
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            api=WorkbenchAPI(Path(directory))
            try:
                with patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
                    help_result=api.dispatch('help.list',{'query':'backup','topic':'recovery'})
                    self.assertTrue(help_result['ok'],help_result)
                    project=api.dispatch('project.create',{'name':'Offline'})
                    progress=api.dispatch('project.readiness',{'project_id':project['project_id']})
                    self.assertTrue(progress['ok'],progress);self.assertFalse(progress['steps'][0]['complete'])
            finally:api.close()
