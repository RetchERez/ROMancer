import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI
from romancer import workbench_projects as projects


class VerifiedGameTests(unittest.TestCase):
    def test_rastan_exact_revision_opens_verified_first_enemy_graphics(self):
        from romancer.verified_games import PROFILES
        profile=copy.deepcopy(next(p for p in PROFILES if p['id']=='rastan-sms'))
        raw=bytearray(262144);raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=0x40
        raw[0x7ffa:0x7ffc]=((sum(raw[:0x7ff0])+sum(raw[0x8000:]))&65535).to_bytes(2,'little')
        source=self.root/'original.sms';source.write_bytes(raw);row=projects.register_source(Path(self.project['path']),source,None);profile['sha256']=row['sha256'];p={**self.params,'artifact_id':row['artifact_id']}
        with patch('romancer.verified_games.PROFILES',(profile,)):
            model=self.api.dispatch('games.inspect',p);self.assertEqual(model['status'],'MATCHED',model);self.assertEqual(model['fields'],[])
            self.assertEqual(model['resources'][0]['kind'],'assets')
            opened=self.api.dispatch('games.configure',{**p,'resource_id':'first-enemy-sprites'});self.assertTrue(opened['ok'],opened)
            self.assertEqual(opened['resource_kind'],'assets');self.assertEqual(opened['inspection']['bitmaps'][0]['count'],60)
            self.assertEqual(opened['inspection']['bitmaps'][0]['codec'],'tile8-rowplanar4-msb-v1')
            self.assertEqual(opened['sprite_layout']['indices'],[30,32,31,33,52,54,53,55])
            explained=self.api.dispatch('resources.explain',{**p,'offset':0x10000});self.assertTrue(explained['ok'],explained)
            self.assertEqual(explained['interpretations'][0]['plane'],0)
            refused=self.api.dispatch('games.plan',{**p,'profile_id':profile['id'],'values':{}});self.assertFalse(refused['ok']);self.assertIn('Graphics',refused['error'])
            self.assertEqual(source.read_bytes(),raw)

    def test_handheld_definitions_guard_layout_and_keep_separate_builds(self):
        from romancer.verified_games import PROFILES
        from romancer.boot_fixtures import make_boot_fixture
        identifiers={'ffl2-usa','dejavu-casebooks-usa'}
        self.assertTrue(identifiers.issubset({p['id'] for p in PROFILES}))
        for identifier,chosen in [('ffl2-usa','stool_down'),('dejavu-casebooks-usa','parchment')]:
            profile=copy.deepcopy(next(p for p in PROFILES if p['id']==identifier))
            raw=bytearray(make_boot_fixture(profile['system'])['data']);raw.extend(bytes(profile['size']-len(raw)))
            raw[0x148]=(len(raw)//32768).bit_length()-1
            if identifier=='ffl2-usa':
                from tests.test_verified_room import make_room_fixture
                raw=make_room_fixture(raw)
            for offset,length,_ in profile['offsets']:
                raw[offset:offset+length]=bytes.fromhex('17ce1d' if identifier=='ffl2-usa' else '0000027e1e007f03')
            raw[0x14d]=(-sum(raw[0x134:0x14d])-25)&255;raw[0x14e:0x150]=bytes(2);raw[0x14e:0x150]=(sum(raw)&65535).to_bytes(2,'big')
            source=self.root/(identifier+('.gb' if profile['system']=='gb' else '.gbc'));source.write_bytes(raw)
            row=projects.register_source(Path(self.project['path']),source,None);profile['sha256']=row['sha256']
            p={**self.params,'artifact_id':row['artifact_id']}
            with self.subTest(identifier=identifier),patch('romancer.verified_games.PROFILES',(profile,)):
                inspected=self.api.dispatch('games.inspect',p);self.assertEqual(inspected['status'],'MATCHED',inspected)
                self.assertIsNotNone(inspected['visual'])
                field=inspected['fields'][0]['id']
                plan=self.api.dispatch('games.plan',{**p,'profile_id':identifier,'values':{field:chosen}});self.assertTrue(plan['ok'],plan)
                built=self.api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']});self.assertTrue(built['ok'],built)
                derived=self.api.dispatch('games.inspect',{**p,'artifact_id':built['artifact_id']})
                self.assertEqual(derived['fields'][0]['value'],chosen,derived)
                self.assertEqual(source.read_bytes(),bytes(raw))
                invalid=self.api.dispatch('games.plan',{**p,'profile_id':identifier,'values':{field:'unverified'}})
                self.assertFalse(invalid['ok'])

    def test_palette_previews_decode_current_and_both_exact_writer_choices(self):
        from romancer.verified_games import palette_visuals
        root=self.root/'palette-root';selected=self.root/'palette-build'
        raw=bytes.fromhex('1f00e003007c0000')
        root.write_bytes(raw);selected.write_bytes(bytes.fromhex('0000285695155d5f'))
        profile={'id':'dejavu-casebooks-usa','offsets':[(0,8,'Colors')]}
        value=palette_visuals(profile,{'path':str(root)},selected)
        palette=value['palettes'][0]
        self.assertEqual(palette['original'][:3],[[255,0,0],[0,255,0],[0,0,255]])
        self.assertEqual(palette['current'],palette['parchment'])
        self.assertEqual(palette['original'][3],[0,0,0])
        self.assertEqual(root.read_bytes(),raw)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=WorkbenchAPI(self.root/'workspace')
        self.addCleanup(self.api.close)
        self.project=projects.create_project(self.api.projects,'Original test program')
        raw=bytearray(16+131072);raw[:8]=bytes.fromhex('4e45531a08002000')
        for offset in (0x1c835,0x1c93a):raw[offset:offset+8]=bytes.fromhex('a904852aa903852c')
        self.original=bytes(raw);source=self.root/'Castlevania (USA).nes';source.write_bytes(raw)
        self.row=projects.register_source(Path(self.project['path']),source,'NES')
        self.params={'project_id':self.project['project_id'],'artifact_id':self.row['artifact_id']}

    def registry(self):
        from romancer.verified_games import PROFILES
        profile=copy.deepcopy(next(p for p in PROFILES if p['id']=='castlevania-usa'))
        profile['sha256']=hashlib.sha256(self.original).hexdigest()
        return patch('romancer.verified_games.PROFILES',(profile,))

    def test_unknown_revision_never_matches_a_filename(self):
        result=self.api.dispatch('games.inspect',self.params)
        self.assertTrue(result['ok'],result);self.assertEqual(result['status'],'UNSUPPORTED')
        blocked=self.api.dispatch('games.plan',{**self.params,'profile_id':'castlevania-usa','values':{'spare_lives':9}})
        self.assertFalse(blocked['ok']);self.assertFalse(list((Path(self.project['path'])/'plans').glob('*.json')))

    def test_named_lives_plan_edits_both_constants_and_labels_derived_build(self):
        with self.registry():
            model=self.api.dispatch('games.inspect',self.params)
            self.assertEqual(model['status'],'MATCHED',model);self.assertEqual(model['fields'][0]['value'],3)
            location=model['locations'][0]
            self.assertEqual(location['storage'],'Unsigned 8-bit counter')
            self.assertIn('current life',location['meaning'])
            self.assertIn('04',location['example']);self.assertIn('HUD',location['evidence'])
            planned=self.api.dispatch('games.plan',{**self.params,'profile_id':'castlevania-usa','values':{'spare_lives':9}})
            self.assertTrue(planned['ok'],planned)
            self.assertEqual([e['offset'] for e in planned['edits']],[0x1c836,0x1c93b])
            built=self.api.dispatch('build.apply',{'project_id':self.params['project_id'],'plan_id':planned['plan_id']})
            self.assertTrue(built['ok'],built);data=Path(built['path']).read_bytes()
            self.assertEqual([data[o] for o in (0x1c836,0x1c93b)],[10,10])
            derived=self.api.dispatch('games.inspect',{**self.params,'artifact_id':built['artifact_id']})
            self.assertEqual(derived['status'],'DERIVED');self.assertFalse(derived['gameplay_verified'])
            self.assertEqual(derived['fields'][0]['value'],9)
            self.assertEqual(Path(self.row['path']).read_bytes(),self.original)
            repeated=self.api.dispatch('games.plan',{**self.params,'profile_id':'castlevania-usa','values':{'spare_lives':9}})
            self.assertEqual(repeated.get('existing_build_id'),built['artifact_id'])

    def test_invalid_values_and_unknown_fields_publish_no_plan(self):
        with self.registry():
            for values in ({'spare_lives':True},{'spare_lives':0},{'spare_lives':100},{'spare_lives':9,'extra':0},{}):
                with self.subTest(values=values):
                    result=self.api.dispatch('games.plan',{**self.params,'profile_id':'castlevania-usa','values':values})
                    self.assertFalse(result['ok'],result)
            self.assertFalse(list((Path(self.project['path'])/'plans').glob('*.json')))

    def test_inconsistent_mirrored_constants_in_derived_build_refuse(self):
        with self.registry():
            plan=projects.plan_byte_edits(Path(self.project['path']),self.row['artifact_id'],[{'offset':0x1c836,'before':'04','after':'07'}])
            built=projects.apply_build(Path(self.project['path']),plan['plan_id'])
            result=self.api.dispatch('games.plan',{**self.params,'artifact_id':built['artifact_id'],'profile_id':'castlevania-usa','values':{'spare_lives':9}})
            self.assertFalse(result['ok']);self.assertIn('mirrored',result['error'])

    def test_modified_owned_source_refuses(self):
        with self.registry():
            Path(self.row['path']).write_bytes(self.original[:-1]+b'X')
            self.assertFalse(self.api.dispatch('games.inspect',self.params)['ok'])

    def other_game(self,identifier):
        from romancer.verified_games import PROFILES
        from romancer.boot_fixtures import make_boot_fixture
        profile=copy.deepcopy(next(p for p in PROFILES if p['id']==identifier))
        fixture=make_boot_fixture(profile['system']);raw=bytearray(fixture['data']);raw.extend(bytes(profile['size']-len(raw)))
        if profile['system']=='snes':raw[0x7fd7]=12;raw[0xc0267]=3
        if profile['system']=='genesis':
            raw[0x1a4:0x1a8]=(len(raw)-1).to_bytes(4,'big');raw[0x4e1b:0x4e25]=b'New game?%';raw[0xfffca:0xfffd4]=bytes.fromhex('0c80fede808566024e75')
        path=self.root/('original-workflow'+fixture['suffix']);path.write_bytes(raw)
        row=projects.register_source(Path(self.project['path']),path,None)
        profile['sha256']=row['sha256']
        return profile,row

    def test_snes_named_power_build_is_exact(self):
        for identifier,values in [('chrono-trigger-usa',{'weapon_attack':30})]:
            profile,row=self.other_game(identifier)
            with self.subTest(identifier=identifier),patch('romancer.verified_games.PROFILES',(profile,)):
                p={**self.params,'artifact_id':row['artifact_id']}
                plan=self.api.dispatch('games.plan',{**p,'profile_id':identifier,'values':values})
                self.assertTrue(plan['ok'],plan)
                built=self.api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']})
                self.assertTrue(built['ok'],built)
                inspected=self.api.dispatch('games.inspect',{**p,'artifact_id':built['artifact_id']})
                self.assertEqual(inspected['fields'][0]['value'],next(iter(values.values())))

    def test_verified_weapon_table_preserves_the_four_unnamed_record_bytes(self):
        profile,row=self.other_game('chrono-trigger-usa');p={**self.params,'artifact_id':row['artifact_id']}
        with patch('romancer.verified_games.PROFILES',(profile,)):
            model=self.api.dispatch('games.inspect',p)
            definition=model['resources'][0]['definition']
            self.assertEqual((definition['offset'],definition['count'],definition['stride']),(0xc0262,90,5))
            self.assertEqual([f['name'] for f in definition['fields']],['Base attack'])
            saved=self.api.dispatch('games.configure',{**p,'resource_id':'weapon-power-table'})
            self.assertTrue(saved['ok'],saved)
            self.assertEqual(saved['inspection']['rows'][1]['cells'][0]['value'],3)
            source=projects.artifact(Path(self.project['path']),row['artifact_id'])
            self.assertEqual(source['descriptors']['tables']['definition'],definition)
            from romancer.data_tables import table_edits
            edits=table_edits(Path(row['path']),row['sha256'],definition,[{'row':1,'field':'Base attack','before':3,'after':7}])
            self.assertEqual(edits,[{'offset':0xc0267,'before':'03','after':'07'}])

    def test_genesis_protects_game_controls_and_includes_visible_integrity_fix(self):
        profile,row=self.other_game('immortal-ue');p={**self.params,'artifact_id':row['artifact_id']}
        with patch('romancer.verified_games.PROFILES',(profile,)):
            for text in ['','         ','too many letters','New%game','New!game','New=game','New@game','café']:
                with self.subTest(text=text):
                    result=self.api.dispatch('games.plan',{**p,'profile_id':profile['id'],'values':{'menu_text':text}})
                    self.assertFalse(result['ok'],result)
            plan=self.api.dispatch('games.plan',{**p,'profile_id':profile['id'],'values':{'menu_text':'New hack?'}})
            self.assertTrue(plan['ok'],plan);self.assertTrue(plan['additional_changes'])
            self.assertIn(0xfffca,[e['offset'] for e in plan['edits']])
            built=self.api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']})
            self.assertTrue(built['ok'],built);self.assertEqual(Path(built['path']).read_bytes()[0x4e1b:0x4e25],b'New hack?%')

    def test_cyclic_build_ancestry_refuses_without_looping(self):
        with self.registry():
            plan=projects.plan_byte_edits(Path(self.project['path']),self.row['artifact_id'],[{'offset':0x100,'before':'00','after':'01'}])
            built=projects.apply_build(Path(self.project['path']),plan['plan_id'])
            with projects.locked(Path(self.project['path'])) as data:
                data['builds'][0]['source_id']=built['artifact_id'];projects.write_json(Path(self.project['path'])/'project.json',data)
            result=self.api.dispatch('games.inspect',{**self.params,'artifact_id':built['artifact_id']})
            self.assertFalse(result['ok']);self.assertIn('cyclic',result['error'])

    def test_public_registry_contains_only_small_sourced_definitions(self):
        from romancer.verified_games import PROFILES
        self.assertEqual(len(PROFILES),6)
        for p in PROFILES:
            self.assertRegex(p['sha256'],r'^[a-f0-9]{64}$')
            self.assertTrue(p['reference'].startswith('https://github.com/') or p['id']=='rastan-sms' and p['reference']=='/user-guide/index.html#rastan-blobs')
            self.assertNotIn('path',p)

    def test_operation_names_and_required_parameters_are_discoverable(self):
        result=self.api.dispatch('system.operations',{})
        self.assertTrue(result['ok'],result)
        operation=next(r for r in result['operations'] if r['name']=='games.plan')
        self.assertEqual(operation['required_parameters'],['project_id','artifact_id','profile_id','values'])
        self.assertEqual(result['scope'],'Operation names, required and optional parameter names; value constraints are documented per operation.')


def setUpModule():
    # Exercise preserved development internals separately from the release boundary.
    from unittest import addModuleCleanup
    from unittest.mock import patch
    feature = patch("romancer.release_scope.LEVEL_EDITOR_ENABLED", True)
    feature.start()
    addModuleCleanup(feature.stop)
