"""Native release checks use actual reviewed engines when supplied or packaged."""
import hashlib,json,os,tempfile,unittest,zipfile
from pathlib import Path
from romancer.core_pins import CORE_PINS
from romancer.bundled_cores import pack_root
from romancer.native_debugger import backend_root,capture_native

PACK=Path(os.environ.get('ROMANCER_TEST_CORE_PACK',str(pack_root())))
OBSERVER=Path(os.environ.get('ROMANCER_TEST_OBSERVER_ROOT',str(backend_root('nes'))))

class ReleaseEngineSourceTests(unittest.TestCase):
    @unittest.skipUnless((PACK/'CORE-SOURCES.zip').is_file(),'reviewed corresponding source pack not supplied')
    def test_inner_source_inventory_origins_and_recipe_match_the_shipped_release(self):
        with zipfile.ZipFile(PACK/'CORE-SOURCES.zip') as z:
            files={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
        origins=json.loads(files['SOURCE-ORIGINS.json']);self.assertEqual(origins,CORE_PINS)
        rows=json.loads(files['SOURCE-FILES.json']);declared={r['path']:r for r in rows}
        self.assertEqual(len(rows),len(declared));self.assertEqual(set(declared),set(files)-{'SOURCE-FILES.json'})
        for name,row in declared.items():
            self.assertEqual(len(files[name]),row['size'],name);self.assertEqual(hashlib.sha256(files[name]).hexdigest(),row['sha256'],name)
        self.assertEqual(files['BUILD-CORES.py'],(Path(__file__).resolve().parents[1]/'tools/build_cores.py').read_bytes())
        self.assertFalse(any(name.startswith('mgba/') for name in files))
        self.assertNotIn('mGBA',files['README.txt'].decode('utf-8'))
    @unittest.skipUnless(os.name=='nt' and (OBSERVER/'Mesen.exe').is_file(),'reviewed Windows native observer not supplied')
    def test_generated_lua_executes_in_each_retained_mesen_machine(self):
        from romancer.boot_fixtures import make_boot_fixture
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);api=WorkbenchAPI(root/'work')
            try:
                settings=api.dispatch('settings.get',{});api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
                for system,start,end in [('nes',0x8000,0xffff),('snes',0x8000,0xffff),('gb',0x100,0x7fff),('gbc',0x100,0x7fff),('sms',0,0xbfff)]:
                    with self.subTest(system=system):
                        fixture=make_boot_fixture(system);path=root/('original'+fixture['suffix']);path.write_bytes(fixture['data'])
                        project=api.dispatch('project.create',{'name':system});p={'project_id':project['project_id']}
                        source=api.dispatch('source.import',{**p,'path':str(path),'system':None});self.assertTrue(source['ok'],source)
                        selected,row,_=api.source({**p,'artifact_id':source['artifact_id']})
                        result=capture_native(selected,row,{'steps':[{'frames':120,'buttons':[],'port':0}],'probes':[{'kind':'exec','start':start,'end':end}],'event_limit':8,'instruction_limit':1000000,'timeout':10,'stop':{'occurrence':1}},root=OBSERVER)
                        self.assertEqual(result['status'],'STOPPED');self.assertTrue(result['events']);self.assertFalse(result['route_complete'])
            finally:api.close()
