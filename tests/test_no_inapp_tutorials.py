from pathlib import Path
import tempfile,unittest
from romancer.workbench_api import WorkbenchAPI
from romancer.app_settings import validate_location

class GuideOnlyTeachingTests(unittest.TestCase):
    def test_fresh_workspace_has_no_tutorial_or_guided_journey_operations(self):
        with tempfile.TemporaryDirectory() as temp:
            api=WorkbenchAPI(Path(temp)/'work')
            try:
                catalogue=api.dispatch('system.operations',{})
                self.assertTrue(catalogue['ok'],catalogue)
                self.assertFalse([r['name'] for r in catalogue['operations'] if r['name'].startswith(('tutorial.','journey.'))])
                self.assertFalse(api.dispatch('tutorial.get',{})['ok'])
                self.assertFalse(api.dispatch('journey.start',{})['ok'])
                self.assertTrue(api.dispatch('help.list',{'query':'','topic':'graphics'})['ok'])
            finally:api.close()

    def test_legacy_lesson_location_resumes_in_help(self):
        location={'version':1,'project_id':'a'*32,'artifact_id':'b'*32,'sha256':'c'*64,
                  'page':'tutorials','offset':0,'selected':0,'scroll':0,
                  'assetPage':0,'scriptPage':0,'catalogPage':0,'catalogQuery':''}
        self.assertEqual(validate_location(location)['page'],'help')
        self.assertEqual(location['page'],'tutorials')
