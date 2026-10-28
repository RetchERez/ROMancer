import json
from pathlib import Path
import tempfile
import unittest
from romancer import workbench_projects as p


class ProjectSupportTests(unittest.TestCase):
    def test_validation_reports_declared_pointer_location_and_remedy(self):
        from romancer.project_checks import validate_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'rom';source.write_bytes(b'\xff\xffabcdefgh')
            project=Path(p.create_project(root/'projects','Validation')['path']);row=p.register_source(project,source,None)
            value=p.read_project(project);value['sources'][0]['descriptors']={'tables':{'source_sha256':row['sha256'],'definition':{'schema_version':1,'name':'Pointers','offset':0,'count':1,'stride':2,'fields':[{'name':'Target','offset':0,'type':'u16','endian':'little','pointer_base':0}]}}};p.write_json(project/'project.json',value)
            result=validate_project(project)
            issue=next(r for r in result['issues'] if r['code']=='INVALID_POINTER');self.assertEqual(issue['offset'],0);self.assertIn('Target',issue['location']);self.assertTrue(issue['remedy']);self.assertFalse(result['valid'])
            Path(row['path']).write_bytes(b'changed')
            self.assertIn('ARTIFACT_CHANGED',[r['code'] for r in validate_project(project)['issues']])
            Path(row['path']).unlink()
            self.assertIn('ARTIFACT_MISSING',[r['code'] for r in validate_project(project)['issues']])

    def test_stale_missing_dependency_and_unknown_scope_are_distinct(self):
        from romancer.project_checks import validate_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'rom';source.write_bytes(b'abc')
            project=Path(p.create_project(root/'projects','Check')['path']);row=p.register_source(project,source,None)
            self.assertEqual(validate_project(project)['status'],'WARNINGS')
            value=p.read_project(project);value['sources'][0].update(source_id='0'*32,descriptors={'assets':{'source':{'sha256':'0'*64}}});p.write_json(project/'project.json',value)
            result=validate_project(project);codes=[r['code'] for r in result['issues']]
            self.assertIn('MISSING_DEPENDENCY',codes);self.assertIn('STALE_DEFINITION',codes)

    def test_support_report_allowlist_excludes_payloads_paths_tokens_and_freeform(self):
        from romancer.support_report import collect_report
        with tempfile.TemporaryDirectory(prefix='PRIVATE_PERSON_') as folder:
            workspace=Path(folder);project=Path(p.create_project(workspace/'projects','SECRET_PROJECT_TEXT')['path'])
            rom=workspace/'rom';rom.write_bytes(b'SECRET_ROM_BYTES');p.register_source(project,rom,None)
            p.write_json(project/'sessions'/'secret.json',{'token':'SECRET_TOKEN','error':'SECRET_ERROR','save_ram_base64':'SECRET_SAVE_BYTES'})
            p.write_json(workspace/'connection.json',{'token':'SECRET_AUTH'})
            from romancer.workbench_evidence import store_evidence
            store_evidence(project,'route',{'status':'PASS','private_note':'SECRET_MEASUREMENT'})
            report=collect_report(workspace,project);text=json.dumps(report)
            for secret in ('PRIVATE_PERSON_',str(workspace),'SECRET_','source_sha256','artifact_id','project_id','save_ram_base64'):
                self.assertNotIn(secret,text)
            self.assertEqual(report['project']['sources'],1);self.assertTrue(report['checks']);self.assertEqual(report['format'],'romancer-support-v1')
            self.assertEqual(report['project']['test_report_counts']['PASS'],1)

    def test_compressed_descendant_overflow_and_overlapping_plan_are_located(self):
        from romancer.project_checks import validate_project
        from romancer.resource_compression import inspect_compressed
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);packed=root/'packed';packed.write_bytes(b'\x30\x08\x00\x00\x85A');decoded=root/'decoded';decoded.write_bytes(b'A'*8)
            project=Path(p.create_project(root/'projects','Compressed')['path']);parent=p.register_source(project,packed,None);child=p.register_source(project,decoded,None)
            result=inspect_compressed(parent['path'],parent['sha256'],0,6,'rle')
            value=p.read_project(project);value['sources'][1]['compressed_parent']={'parent_id':parent['artifact_id'],'parent_sha256':parent['sha256'],'offset':0,'allocation':6,'codec':'rle','decoded_sha256':child['sha256'],'stream_sha256':result['stream_sha256'],'consumed':result['consumed']};p.write_json(project/'project.json',value)
            plan=p.plan_byte_edits(project,child['artifact_id'],[{'offset':0,'before':'41'*8,'after':b'abcdefgh'.hex()}]);built=p.apply_build(project,plan['plan_id'])
            issues=validate_project(project)['issues'];problem=next(r for r in issues if r['code']=='COMPRESSED_ALLOCATION');self.assertEqual(problem['artifact_id'],built['artifact_id']);self.assertEqual(problem['offset'],0)
            saved=project/'plans'/(plan['plan_id']+'.json');data=json.loads(saved.read_text());data['edits'].append({'offset':1,'before':'41','after':'42'});p.write_json(saved,data)
            self.assertIn('PLAN_OVERLAP',[r['code'] for r in validate_project(project)['issues']])
