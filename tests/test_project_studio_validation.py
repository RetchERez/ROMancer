import unittest,tempfile
from pathlib import Path
from romancer.workbench_api import WorkbenchAPI

class StudioValidationTests(unittest.TestCase):
    def test_current_studio_level_and_sound_definitions_are_not_falsely_stale(self):
        folder=self.enterContext(tempfile.TemporaryDirectory());api=WorkbenchAPI(Path(folder));self.addCleanup(api.close)
        p=api.dispatch('project.studio',{});r=api.dispatch('project.validate',{'project_id':p['project_id']});self.assertTrue(r['ok'],r)
        self.assertFalse([i for i in r['issues'] if i['code']=='STALE_DEFINITION'],r['issues'])
    def test_invalid_current_level_data_is_reported_at_its_definition(self):
        from romancer import workbench_projects as projects
        folder=self.enterContext(tempfile.TemporaryDirectory());api=WorkbenchAPI(Path(folder));self.addCleanup(api.close)
        p=api.dispatch('project.studio',{});project=api.project(p)
        with projects.locked(project) as value:
            value['sources'][0]['descriptors']['levels']['rooms'][0]['terrain']['offset']=99999999;projects.write_json(project/'project.json',value)
        r=api.dispatch('project.validate',{'project_id':p['project_id']});self.assertTrue(any(i['code']=='INVALID_DEFINITION' and 'levels' in i['location'] for i in r['issues']),r['issues'])
