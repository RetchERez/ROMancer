"""Adversarial regressions from the final independent release review."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import zipfile
from romancer.boot_fixtures import make_boot_fixture
from romancer import workbench_projects as p


def require_publication(test):
    from tests.test_streaming_release import require_directory_publication
    require_directory_publication(test)


class ReviewTests(unittest.TestCase):
    def test_historical_capture_cannot_supply_fresh_native_menu_authority(self):
        from romancer.menu_compare import _read_native_capture
        stored={'ok':True,'image_integrity':'PASS','runtime_trusted':False,'record':{'origin':'native_worker','build':{'association':'measured_run_output'}}}
        with patch('romancer.menu_compare.capture_store.get_capture',return_value=stored),self.assertRaisesRegex(ValueError,'historical'):
            _read_native_capture(Path('.'),{'capture_id':'1'*32})

    def test_invalid_structural_header_edits_refuse(self):
        from romancer.system_integrity import integrity_edits
        with tempfile.TemporaryDirectory() as folder:
            for system,offset,after in [('nes',4,'ff'),('gb',0x148,'08'),('snes',0x7fd5,'21'),('gba',0xb2,'00'),('genesis',0x1a7,'00')]:
                data=make_boot_fixture(system)['data'];path=Path(folder)/system;path.write_bytes(data)
                with self.subTest(system=system),self.assertRaises(ValueError):
                    integrity_edits(path,hashlib.sha256(data).hexdigest(),system,[{'offset':offset,'before':data[offset:offset+1].hex(),'after':after}])

    def test_byte_and_structured_builds_keep_fresh_system_identity_for_chained_edits(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                demo=api.dispatch('project.demo_system',{'system_id':'gb'});source=demo['sources'][0];params={'project_id':demo['project_id'],'artifact_id':source['artifact_id']}
                plan=api.dispatch('systems.plan_edits',{**params,'edits':[{'offset':0x200,'before':'81','after':'c1'}]});built=api.dispatch('build.apply',{'project_id':demo['project_id'],'plan_id':plan['plan_id']})
                self.assertEqual(built.get('system_id'),'gb');self.assertEqual(built['system_assessment']['source']['sha256'],built['sha256'])
                next_plan=api.dispatch('systems.plan_edits',{**params,'artifact_id':built['artifact_id'],'edits':[{'offset':0x201,'before':'00','after':'01'}]});second=api.dispatch('build.apply',{'project_id':demo['project_id'],'plan_id':next_plan['plan_id']})
                data=Path(second['path']).read_bytes();self.assertEqual(int.from_bytes(data[0x14e:0x150],'big'),(sum(data[:0x14e])+sum(data[0x150:]))&65535)
                model=api.dispatch('assets.inspect',{**params,'schema':source['descriptors']['assets']});pixels=model['bitmaps'][0]['cells'][0]['pixels'];after=pixels.copy();after[1]=1
                request={'schema_version':1,'document_id':model['document_id'],'changes':[{'kind':'cell','bitmap_id':'tiles','cell_index':0,'before_pixels':pixels,'after_pixels':after}],'acknowledged_consumers':[]}
                plan=api.dispatch('assets.plan',{**params,'schema':source['descriptors']['assets'],'edits':request});built=api.dispatch('structured.apply',{'project_id':demo['project_id'],'plan_id':plan['workbench_plan_id']})
                self.assertEqual(built.get('system_id'),'gb');self.assertEqual(built['system_assessment']['source']['sha256'],built['sha256'])
            finally:api.close()

    def test_iso_file_over_metadata_refuses_inventory(self):
        from tests.test_v53_containers import iso_fixture
        from romancer.container_workspace import inventory_container
        with tempfile.TemporaryDirectory() as folder:
            original=iso_fixture();record=20*2048+68
            for extent in (0,16,17,20):
                data=bytearray(original);data[record+2:record+10]=extent.to_bytes(4,'little')+extent.to_bytes(4,'big');data[record+10:record+18]=(2048).to_bytes(4,'little')+(2048).to_bytes(4,'big')
                path=Path(folder)/str(extent);path.write_bytes(data)
                with self.subTest(extent=extent),self.assertRaises(ValueError):inventory_container(path,hashlib.sha256(data).hexdigest())

    def test_archive_replacement_of_non_artifact_bytes_refuses_restore(self):
        require_publication(self)
        from romancer import project_portability as portability
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(p.create_project(root/'projects','Backup')['path']);(project/'drafts').mkdir(exist_ok=True);(project/'drafts/note.json').write_bytes(b'ORIGINAL')
            archive=root/'backup.zip';portability.backup_project(project,archive,['sources','builds','reports','sessions','captures']);verify=portability._verify_archive
            def replace_after_check(path):
                manifest=verify(path)
                with zipfile.ZipFile(path) as z:entries={name:z.read(name) for name in z.namelist()}
                entries['drafts/note.json']=b'CHANGED AFTER VERIFICATION'
                with zipfile.ZipFile(path,'w') as z:
                    for name,raw in entries.items():z.writestr(name,raw)
                return manifest
            with patch.object(portability,'_verify_archive',side_effect=replace_after_check),self.assertRaises(ValueError):portability.restore_project(archive,root/'restored')
            self.assertFalse((root/'restored'/project.name).exists())

    def test_forged_backup_cannot_grant_coverage_or_current_evidence_trust(self):
        require_publication(self)
        from romancer.project_portability import restore_project
        from romancer.workbench_evidence import load_evidence,store_evidence
        from romancer.coverage import build_coverage
        from romancer.script_schema import canonical_bytes
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(p.create_project(root/'projects','Forged')['path']);identifier='1'*32;key=b'K'*32
            report={'origin':'owned_native_worker','status':'PASS','worker_close_acknowledged':True,'worker_exit_code':0,'transitions':[{'objective':'fabricated','evidence':'measured_assertions','interpretation':'profile_declared'}]}
            record={'schema_version':1,'evidence_id':identifier,'kind':'route','report':report};record['signature']=hmac.new(key,canonical_bytes(record,max_bytes=8*1024**2),hashlib.sha256).hexdigest()
            members={'project.json':(project/'project.json').read_bytes(),'.evidence-key':key,'reports/'+identifier+'.json':json.dumps(record).encode()}
            manifest={'format':'romancer-private-backup-v1','project_id':project.name,'origin_root':str(project),'roles':['sources','builds','reports','sessions','captures'],'members':[{'name':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in members.items()]}
            archive=root/'forged.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for name,raw in members.items():z.writestr(name,raw)
                z.writestr('backup-manifest.json',json.dumps(manifest))
            restored=Path(restore_project(archive,root/'restored')['path']);loaded=load_evidence(restored,identifier)
            self.assertFalse(loaded.get('runtime_trusted',True));self.assertEqual(loaded['report'],report)
            coverage=build_coverage(restored,[identifier],{'required':['fabricated'],'optional':[],'endings':[],'unknown_edges':[]})
            self.assertEqual(coverage['status'],'PARTIAL');self.assertEqual(coverage['untrusted_reports'],1)
            fresh=store_evidence(restored,'runtime',{'status':'NOT_RUN'});self.assertTrue(load_evidence(restored,fresh['evidence_id'])['runtime_trusted'])
            self.assertNotEqual((restored/'.evidence-key').read_bytes(),key)

    def test_external_system_directory_is_snapshotted_and_changes_state_binding(self):
        from romancer.runtime_worker import Workspace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);core=root/'core';core.write_bytes(b'core');game=root/'game';game.write_bytes(b'game');system=root/'system';system.mkdir();(system/'bios').write_bytes(b'old')
            parameters={'core':str(core),'game':str(game),'expected_core_sha256':hashlib.sha256(b'core').hexdigest(),'expected_game_sha256':hashlib.sha256(b'game').hexdigest(),'system_dir':str(system)}
            frontend=Mock();frontend.load_game.return_value={};frontend.av_info.return_value={}
            with patch('romancer.runtime_worker.LibretroFrontend',return_value=frontend):
                first=Workspace();first.load({**parameters,'session_dir':str(root/'first')});binding=first._binding();first.close()
                self.assertEqual((root/'first/system/bios').read_bytes(),b'old');(system/'bios').write_bytes(b'new')
                second=Workspace()
                try:
                    second.load({**parameters,'session_dir':str(root/'second')})
                    with self.assertRaises(ValueError):second._check_binding(binding)
                finally:second.close()

    def test_legacy_rollback_retires_newer_connection_without_losing_it(self):
        from tools.install_windows import rollback
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'workspace').mkdir();connection=b'{"port":12345,"url":"http://127.0.0.1:12345/#token=test"}';(root/'workspace/connection.json').write_bytes(connection)
            (root/'old.ps1').write_text('old launcher');(root/'Open ROMancer.ps1').write_text('current launcher');(root/'active.json').write_text(json.dumps({'version':'60.0.0','legacy_launcher':'old.ps1'}))
            rollback(root);self.assertFalse((root/'workspace/connection.json').exists());self.assertEqual((root/'Open ROMancer.ps1').read_text(),'old launcher')
            backups=list((root/'workspace').glob('connection-before-rollback-*.json'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),connection)

    def test_first_draft_undo_means_no_override_instead_of_deleting_source_text(self):
        from romancer.draft_store import draft_update,draft_move
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'text';source.write_bytes(b'ORIGINAL');project=Path(p.create_project(root/'projects','Text')['path']);row=p.register_source(project,source,None)
            saved=draft_update(project,row['artifact_id'],'scripts:text',0,'CHANGED');undo=draft_move(project,row['artifact_id'],'scripts:text',saved['revision'],-1)
            self.assertIsNone(undo['value'])

    def test_private_backup_retains_prepared_exports_and_index(self):
        require_publication(self)
        from romancer.project_portability import backup_project,restore_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(p.create_project(root/'projects','Exports')['path']);(project/'exports').mkdir(exist_ok=True);(project/'exports/audio.wav').write_bytes(b'original captured PCM');(project/'exports.json').write_bytes(b'{"schema_version":1,"exports":[]}')
            archive=root/'backup.zip';backup_project(project,archive,['sources','builds','reports','sessions','captures']);restored=Path(restore_project(archive,root/'restored')['path'])
            self.assertEqual((restored/'exports/audio.wav').read_bytes(),b'original captured PCM');self.assertEqual((restored/'exports.json').read_bytes(),(project/'exports.json').read_bytes())
