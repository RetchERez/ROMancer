from romancer.boot_fixtures import make_boot_fixture
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from romancer import workbench_projects as p


class PortableProjectsTests(unittest.TestCase):
    def test_api_drafts_survive_service_restart(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'own.bin';source.write_bytes(make_boot_fixture('nes')['data'])
            api=WorkbenchAPI(root/'workspace')
            project=api.dispatch('project.create',{'name':'Persistent'})
            row=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(source),'system':None})
            args={'project_id':project['project_id'],'artifact_id':row['artifact_id'],'key':'scripts:line'}
            self.assertTrue(api.dispatch('drafts.save',{**args,'revision':0,'value':'Saved'})['ok'])
            api.close();api=WorkbenchAPI(root/'workspace')
            try:
                self.assertEqual(api.dispatch('drafts.get',args)['value'],'Saved')
                self.assertFalse(api.dispatch('drafts.save',{**args,'revision':0,'value':'Conflict'})['ok'])
            finally:api.close()

    def test_move_backup_restore_preserves_build_and_signed_evidence(self):
        from tests.test_streaming_release import require_directory_publication
        require_directory_publication(self)
        from romancer.project_portability import migrate_project,backup_project,restore_project
        from romancer.workbench_evidence import store_evidence,load_evidence
        from romancer.history import get_build
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'own.bin';source.write_bytes(b'01234567')
            project=Path(p.create_project(root/'original','Portable')['path'])
            row=p.register_source(project,source,None)
            plan=p.plan_byte_edits(project,row['artifact_id'],[{'offset':3,'before':'33','after':'41'}])
            build=p.apply_build(project,plan['plan_id'])
            evidence=store_evidence(project,'runtime',{'status':'NOT_RUN','note':'historical'})
            signed=(project/'reports'/(evidence['evidence_id']+'.json')).read_bytes()
            migrate_project(project)
            stored=json.loads((project/'project.json').read_text(encoding='utf-8'))
            self.assertFalse(Path(stored['sources'][0]['path']).is_absolute())
            archive=root/'backup.zip';backup_project(project,archive,['sources','builds','reports','sessions','captures'])
            restored=restore_project(archive,root/'moved é')
            new=Path(restored['path']);actual=p.artifact(new,build['artifact_id'])
            self.assertEqual(Path(actual['path']).read_bytes(),b'012A4567')
            history=get_build(new,build['build_id']);self.assertEqual(history['build_id'],build['build_id'])
            self.assertTrue(str(history['locations']['output']).startswith(str(new)))
            self.assertEqual((new/'reports'/(evidence['evidence_id']+'.json')).read_bytes(),signed)
            self.assertEqual(load_evidence(new,evidence['evidence_id'])['report']['status'],'NOT_RUN')
            self.assertEqual(source.read_bytes(),b'01234567')

    def test_draft_reopen_undo_revision_conflict_and_changed_source(self):
        from romancer.draft_store import draft_get,draft_update,draft_move
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'own.bin';source.write_bytes(make_boot_fixture('nes')['data'])
            project=Path(p.create_project(root/'workspace','Drafts')['path']);row=p.register_source(project,source,None)
            args=(project,row['artifact_id'],'scripts:text')
            first=draft_update(*args,0,'First');second=draft_update(*args,first['revision'],'Second')
            self.assertEqual(draft_get(*args)['value'],'Second')
            undo=draft_move(*args,second['revision'],-1);self.assertEqual(undo['value'],'First')
            redo=draft_move(*args,undo['revision'],1);self.assertEqual(redo['value'],'Second')
            with self.assertRaises(ValueError):draft_update(*args,first['revision'],'Lost update')
            Path(row['path']).write_bytes(b'changed!')
            with self.assertRaises(ValueError):draft_get(*args)

    def test_legacy_migration_keeps_backup_and_rejects_escaping_relative_path(self):
        from romancer.project_portability import migrate_project
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'own.bin';source.write_bytes(make_boot_fixture('nes')['data'])
            project=Path(p.create_project(root/'workspace','Legacy')['path']);p.register_source(project,source,None)
            legacy=p.read_project(project);legacy.update(format='romancer-workbench-v1',schema_version=1)
            p.write_json(project/'project.json',legacy);before=(project/'project.json').read_bytes()
            self.assertEqual(migrate_project(project)['status'],'MIGRATED')
            self.assertEqual((project/'project.v1.backup.json').read_bytes(),before)
            value=json.loads((project/'project.json').read_bytes());value['sources'][0]['path']='sources/../../outside'
            (project/'project.json').write_text(json.dumps(value))
            with self.assertRaises(ValueError):p.read_project(project)

    def test_archive_traversal_and_active_lock_refuse(self):
        from romancer.project_portability import restore_project,recover_lock
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside','bad')
            with self.assertRaises(ValueError):restore_project(archive,root/'restore')
            project=Path(p.create_project(root/'workspace','Locks')['path'])
            with p.locked(project):
                with self.assertRaises(ValueError):recover_lock(project)
            lock=project/'.workbench-lock';lock.mkdir();(lock/'owner.json').write_text(json.dumps({'pid':99999999,'session':'1'*32,'host':__import__('socket').gethostname()}))
            self.assertEqual(recover_lock(project)['status'],'RECOVERED')
            self.assertFalse(lock.exists())
