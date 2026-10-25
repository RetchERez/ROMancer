"""Color cartridges keep their own identity while sharing GB storage formats."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_gameboy import cartridge
from tests.test_runtime_profiles import fake_core


class GameBoyColorTests(unittest.TestCase):
    def test_legacy_color_project_is_reclassified_from_its_bound_assessment(self):
        from romancer import workbench_projects as projects
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'old.gb';source.write_bytes(cartridge(color=0x80))
            project=projects.create_project(root/'projects','Old Color import');path=Path(project['path'])
            row=projects.register_source(path,source,None)
            value=projects.read_project(path);stored=value['sources'][0]
            stored['system_id']='gb';stored['system_assessment']['system_id']='gb'
            for candidate in stored['system_assessment']['candidates']:
                candidate['system_id']='gb';candidate['format']='gb-cartridge'
            projects.write_json(path/'project.json',value)
            self.assertEqual(projects.read_project(path)['sources'][0]['system_id'],'gbc')
            self.assertEqual(source.read_bytes(),cartridge(color=0x80))

    def test_header_selects_color_independent_of_filename(self):
        from romancer.system_identify import identify_system
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'renamed.nes'
            for flag,system in [(0,'gb'),(0x80,'gbc'),(0xc0,'gbc')]:
                with self.subTest(flag=flag):
                    path.write_bytes(cartridge(color=flag))
                    result=identify_system(path)
                    self.assertEqual(result['status'],'IDENTIFIED')
                    self.assertEqual(result['system_id'],system)

    def test_color_source_can_edit_and_repair_without_changing_family(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'input.gb';raw=cartridge(color=0xc0);path.write_bytes(raw)
            api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Color'})
                p={'project_id':project['project_id']}
                source=api.dispatch('source.import',{**p,'path':str(path),'system':'Game Boy Color'})
                self.assertTrue(source['ok'],source)
                self.assertEqual(source['system_id'],'gbc')
                planned=api.dispatch('systems.plan_edits',{**p,'artifact_id':source['artifact_id'],'edits':[{'offset':0x200,'before':'00','after':'01'}]})
                self.assertTrue(planned['ok'],planned)
                built=api.dispatch('build.apply',{**p,'plan_id':planned['plan_id']})
                self.assertTrue(built['ok'],built)
                self.assertEqual(built['system_id'],'gbc')
                changed=Path(built['path']).read_bytes()
                self.assertEqual(int.from_bytes(changed[0x14e:0x150],'big'),(sum(changed[:0x14e])+sum(changed[0x150:]))&65535)
                self.assertEqual(path.read_bytes(),raw)
            finally:api.close()

    def test_color_profile_uses_same_pinned_core_with_separate_hardware(self):
        from romancer.runtime_profiles import load_profile,save_profile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pack=root/'cores';pack.mkdir();core=pack/'gb.dll';fake_core(core)
            pin={'name':'Gambatte fixture','file':core.name,'sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'options':{'gambatte_gb_hwmode':'GB'}}
            files={core.name:{'size':core.stat().st_size,'sha256':pin['sha256']}}
            with patch('romancer.bundled_cores.CORE_PINS',{'gb':pin}),patch('romancer.bundled_cores.CORE_FILES',files),patch('romancer.bundled_cores.pack_root',return_value=pack),patch('romancer.bundled_cores.host_supported',return_value=True):
                save_profile(root/'workspace','gb',str(core),{'gambatte_gb_hwmode':'GB'},None,{})
                color=load_profile(root/'workspace','gbc')
                self.assertEqual(color['status'],'BUNDLED')
                self.assertEqual(color['profile']['system_id'],'gbc')
                self.assertEqual(color['profile']['options']['gambatte_gb_hwmode'],'GBC')
                self.assertEqual(load_profile(root/'workspace','gb')['profile']['options']['gambatte_gb_hwmode'],'GB')

    def test_color_workshop_has_color_header_and_graphics_declaration(self):
        from romancer.workbench_api import WorkbenchAPI
        from romancer.system_addresses import translate
        from romancer.audio_systems import audio_system_info
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                demo=api.dispatch('project.demo_system',{'system_id':'gbc'})
                self.assertTrue(demo['ok'],demo);row=demo['sources'][0]
                self.assertEqual(row['system_id'],'gbc')
                self.assertEqual(Path(row['path']).read_bytes()[0x143],0xc0)
                self.assertTrue(row['descriptors']['assets']['palettes'])
                self.assertEqual(translate('gbc',0x4567,{'id':'gb-rom'},3,65536)['offset'],0xc567)
                self.assertEqual(audio_system_info('gbc',row['sha256'])['hardware']['nominal_channels'],4)
            finally:api.close()
