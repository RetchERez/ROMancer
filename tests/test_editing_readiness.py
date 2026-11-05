from pathlib import Path
import tempfile,unittest
from romancer.workbench_api import WorkbenchAPI
from romancer import workbench_projects as projects

class EditingReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.api=WorkbenchAPI(Path(self.temp.name)/'work')
        self.demo=self.api.dispatch('project.demo_system',{'system_id':'nes'});self.row=self.demo['sources'][0]
        self.p={'project_id':self.demo['project_id'],'artifact_id':self.row['artifact_id']}
    def tearDown(self):self.api.close();self.temp.cleanup()
    def call(self,op,p):
        r=self.api.dispatch(op,p);self.assertTrue(r['ok'],r);return r
    def test_readiness_checks_saved_layouts_without_inventing_game_knowledge(self):
        r=self.call('editing.readiness',self.p);by={x['kind']:x for x in r['areas']}
        self.assertEqual(by['assets']['status'],'ready');self.assertNotIn('levels',by)
        self.assertFalse(r['game_semantics_inferred'])
        project=Path(self.demo['path']);value=projects.read_project(project);value['sources'][0]['descriptors']['assets']['source_sha256']='0'*64;projects.write_json(project/'project.json',value)
        by={x['kind']:x for x in self.call('editing.readiness',self.p)['areas']};self.assertEqual(by['assets']['status'],'unsupported')
    def test_malformed_saved_table_is_reported_without_breaking_overview(self):
        project=Path(self.demo['path']);value=projects.read_project(project);value['sources'][0]['descriptors']['tables']=['malformed'];projects.write_json(project/'project.json',value)
        r=self.call('editing.readiness',self.p);self.assertEqual(next(a for a in r['areas'] if a['kind']=='tables')['status'],'unsupported')

    def test_successful_read_only_inspection_never_says_ready_to_edit(self):
        project=Path(self.demo['path']);value=projects.read_project(project)
        value['sources'][0]['descriptors']['assets']['bitmaps'][0]['codec']='not-understood'
        projects.write_json(project/'project.json',value)
        r=self.call('editing.readiness',self.p);area=next(a for a in r['areas'] if a['kind']=='assets')
        self.assertEqual(area['status'],'unsupported');self.assertIn('read-only',area['reason'].lower())

    def test_saved_levels_do_not_advertise_an_editor_in_the_release(self):
        project=Path(self.demo['path']);value=projects.read_project(project);value['sources'][0]['descriptors']['levels']={};projects.write_json(project/'project.json',value)
        r=self.call('editing.readiness',self.p);self.assertNotIn('levels', {a['kind'] for a in r['areas']})
