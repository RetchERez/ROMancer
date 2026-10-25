import base64
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from romancer import workbench_projects as p
from romancer.workbench_files import import_input


def snapshot(raw,game):
    return {'ok':True,'core_sha256':'a'*64,'game_sha256':game,'runtime_identity_sha256':'b'*64,'run_mode':'cold_boot',
            'sha256':hashlib.sha256(raw).hexdigest(),'save_ram_base64':base64.b64encode(raw).decode(),'scope':'exposed_save_ram_snapshot',
            'provenance':{'origin':'cold_boot','state_derived':False},'in_game_save_event_verified':False}


class SaveManagerTests(unittest.TestCase):
    def test_mgba_autodetect_import_and_restore_before_first_frame(self):
        from romancer.save_manager import import_save,restore_save,list_saves
        from romancer.workbench_api import WorkbenchAPI
        from unittest.mock import Mock
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);rom=root/'game.gba';rom.write_bytes(b'gba');save=root/'progress.sav';seed=b'W'*32768;save.write_bytes(seed)
            api=WorkbenchAPI(root/'workspace')
            try:
                project=Path(p.create_project(api.projects,'Early save')['path']);row=p.register_source(project,rom,None)
                api.runtime.session_selection=Mock(return_value={'id':row['artifact_id'],'sha256':row['sha256']})
                api.runtime.request=Mock(return_value=snapshot(b'\xff'*131072,row['sha256']))
                runtime=SimpleNamespace(load_result={'loaded':{'core':{'library_name':'mGBA'}}})
                session={'runtime':runtime,'load':{'core':'fake','game':str(rom),'core_options':{},'expected_core_sha256':'a'*64,'system_files':[]}}
                api.runtime.sessions[str(project)]=session
                inp=import_input(project,save,save.name,'save')
                imported=import_save(api,project,row['artifact_id'],inp['input_id'],'Existing progress')
                api.runtime.close_session=Mock();api.runtime.load=Mock(return_value={'ok':True,'run_mode':'game_save_continuation'})
                restored=restore_save(api,project,row['artifact_id'],imported['save_id'])
                self.assertEqual(restored['status'],'RESTORED')
                configuration=api.runtime.load.call_args.kwargs['configuration']
                self.assertEqual(base64.b64decode(configuration['game_save']['save_ram_base64']),seed)
                self.assertTrue(any(s['size']==131072 and s['origin']=='automatic_backup' for s in list_saves(project,row['artifact_id'])['saves']))
                for core,game,raw in [('Other',str(rom),b'\xff'*131072),('mGBA',str(root/'game.gb'),b'\xff'*131072),('mGBA',str(rom),b'\xff'*32768+b'\x01\x02'*49152)]:
                    runtime.load_result={'loaded':{'core':{'library_name':core}}};session['load']['game']=game
                    api.runtime.request.return_value=snapshot(raw,row['sha256']);api.runtime.close_session.reset_mock()
                    with self.subTest(core=core,game=game,uniform=len(set(raw))==1):
                        with self.assertRaisesRegex(ValueError,'size'):restore_save(api,project,row['artifact_id'],imported['save_id'])
                        api.runtime.close_session.assert_not_called()
            finally:api.runtime.sessions.clear();api.close()

    def test_save_preflight_accepts_supported_large_payload_without_raising_generic_request_budget(self):
        from romancer.runtime_session import preflight_load,snapshot_json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);core=root/'core';core.write_bytes(b'core');game=root/'game';game.write_bytes(b'game')
            saved=snapshot(b'X'*1024**2,hashlib.sha256(b'game').hexdigest())
            config={'core':str(core),'game':str(game),'expected_core_sha256':hashlib.sha256(b'core').hexdigest(),
                    'expected_game_sha256':saved['game_sha256'],'session_dir':str(root/'session'),'game_save':saved}
            self.assertEqual(preflight_load(config,root,allow_game_save=True)['game_save']['sha256'],saved['sha256'])
            with self.assertRaises(ValueError):snapshot_json({'data':'X'*(1024**2+1)})

    def test_raw_import_size_binding_and_immutable_backups_before_restore_failure(self):
        from romancer.save_manager import import_save,list_saves,restore_save
        from romancer.workbench_api import WorkbenchAPI
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);rom=root/'rom';rom.write_bytes(b'abc');save=root/'progress.sav';save.write_bytes(b'WXYZ');api=WorkbenchAPI(root/'workspace')
            try:
                project=Path(p.create_project(api.projects,'Saves')['path']);row=p.register_source(project,rom,None)
                api.runtime.session_selection=Mock(return_value={'id':row['artifact_id'],'sha256':row['sha256']})
                api.runtime.request=Mock(return_value=snapshot(b'ABCD',row['sha256']))
                api.runtime.sessions[str(project)]={'load':{'core':'fake','core_options':{},'expected_core_sha256':'a'*64,'system_files':[]}}
                inp=import_input(project,save,save.name,'save');result=import_save(api,project,row['artifact_id'],inp['input_id'],'Imported progress')
                self.assertEqual(list_saves(project,row['artifact_id'])['saves'][0]['size'],4)
                api.runtime.close_session=Mock();api.runtime.load=Mock(side_effect=ValueError('core refused imported save'))
                saved_path=project/'sessions'/(result['save_id']+'.json')
                import json
                stored=json.loads(saved_path.read_text());wrong={**stored,'runtime_identity_sha256':'c'*64};p.write_json(saved_path,wrong,max_bytes=12*1024**2)
                with self.assertRaisesRegex(ValueError,'setup differs'):restore_save(api,project,row['artifact_id'],result['save_id'])
                api.runtime.close_session.assert_not_called();self.assertEqual(len(list_saves(project,row['artifact_id'])['saves']),1)
                wrong={**stored,'sha256':'0'*64};p.write_json(saved_path,wrong,max_bytes=12*1024**2)
                with self.assertRaisesRegex(ValueError,'checksum'):restore_save(api,project,row['artifact_id'],result['save_id'])
                api.runtime.close_session.assert_not_called();p.write_json(saved_path,stored,max_bytes=12*1024**2)
                with self.assertRaisesRegex(ValueError,'refused'):restore_save(api,project,row['artifact_id'],result['save_id'])
                saves=list_saves(project,row['artifact_id'])['saves'];self.assertEqual(len(saves),2)
                self.assertTrue(any(s['origin']=='automatic_backup' for s in saves));self.assertEqual(save.read_bytes(),b'WXYZ')
                self.assertTrue((project/'sessions'/(result['save_id']+'.json')).is_file())
                api.runtime.request.return_value=snapshot(b'ZZ',row['sha256'])
                with self.assertRaisesRegex(ValueError,'size'):import_save(api,project,row['artifact_id'],inp['input_id'],'Wrong size')
                self.assertEqual(len(list_saves(project,row['artifact_id'])['saves']),2)
            finally:api.runtime.sessions.clear();api.close()

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'native save-RAM roundtrip requires Linux mock core')
    def test_native_import_restart_and_raw_export_roundtrip(self):
        from romancer.save_manager import import_save,capture_save,restore_save,export_save
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);core=root/'mock.so';subprocess.run(['gcc','-shared','-fPIC','-O2','tests/mock_libretro.c','-o',str(core)],check=True)
            api=WorkbenchAPI(root/'workspace');rom=root/'rom.bin';rom.write_bytes(b'original')
            try:
                project=Path(p.create_project(api.projects,'Native saves')['path']);row=p.register_source(project,rom,None)
                api.runtime.load(project,row['artifact_id'],str(core),{})
                original=capture_save(api,project,row['artifact_id'],'Before import')
                self.assertGreater(original['size'],0)
                raw=bytes((i+31)%256 for i in range(original['size']));save=root/'progress.srm';save.write_bytes(raw)
                inp=import_input(project,save,save.name,'save');imported=import_save(api,project,row['artifact_id'],inp['input_id'],'External save')
                restored=restore_save(api,project,row['artifact_id'],imported['save_id']);self.assertEqual(restored['status'],'RESTORED');self.assertTrue(restored['backup_save_id'])
                current=api.runtime.request(project,'save_game',{});self.assertEqual(base64.b64decode(current['save_ram_base64']),raw)
                exported=export_save(api,project,row['artifact_id'],imported['save_id']);path,_=api.download(project.name,exported['export']['export_id']);self.assertEqual(path.read_bytes(),raw);self.assertEqual(exported['export']['role'],'save')
            finally:api.close()
