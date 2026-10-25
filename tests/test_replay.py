import copy
import hashlib
import importlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest


def route_fixture():
    return {'schema_version':1,'id':'cursor-right','max_frames':2,'max_actions':2,
            'steps':[{'frames':1,'buttons':['right'],'port':0,'assertions':[
                {'kind':'memory_eq','region':2,'offset':0,'expected_hex':'0908'}],
                'transition':{'from':'start','to':'right','objective':'move-right'},'checkpoint':True}]}


class ReplayTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'compiled stalled route')
    def test_running_cancellation_reaps_stalled_owned_worker(self):
        self.module()
        from romancer.runtime_session import OwnedRuntime,preflight_load
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game=root/'game';game.write_bytes(b'stall fixture');core=root/'stall.so'
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_worker_hang.c','-o',str(core)],check=True)
            load={'core':str(core),'game':str(game),'session_dir':str(root/'s'),
                'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(game.read_bytes()).hexdigest()}
            event=threading.Event();started=time.monotonic()
            with self.assertRaises(KeyboardInterrupt):
                with OwnedRuntime(preflight_load(load,root),20,cancelled=event.is_set) as runtime:
                    process=runtime.client.process;timer=threading.Timer(.2,event.set);timer.start()
                    try:runtime.request('advance',frames=1,buttons=[],port=0)
                    finally:timer.join()
            self.assertLess(time.monotonic()-started,3);self.assertIsNotNone(process.poll())

    def module(self):
        try:module=importlib.import_module('romancer.replay')
        except ModuleNotFoundError:module=None
        self.assertIsNotNone(module,'executed route service is missing');return module

    def test_unknown_assertion_and_supplied_pass_refuse(self):
        module=self.module();route=route_fixture();route['status']='PASS'
        with self.assertRaises(ValueError):module.validate_route(route)
        route=route_fixture();route['steps'][0]['assertions'][0]['kind']='assume_pass'
        with self.assertRaises(ValueError):module.validate_route(route)

    def test_zero_assertion_route_cannot_claim_assertion_pass(self):
        route=route_fixture();route['steps'][0].update(assertions=[],transition=None)
        with self.assertRaises(ValueError):self.module().validate_route(route)

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'compiled libretro route')
    def test_real_input_assertion_failure_continuation_and_cancel(self):
        module=self.module()
        from romancer.runtime_session import OwnedRuntime,preflight_load
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game=root/'game';game.write_bytes(b'original route fixture');core=root/'mock.so'
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_libretro.c','-o',str(core)],check=True)
            load={'core':str(core),'game':str(game),'session_dir':str(root/'s'),
                  'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(game.read_bytes()).hexdigest()}
            with OwnedRuntime(preflight_load(load,root),10) as runtime:
                context={'core_sha256':load['expected_core_sha256'],'game_sha256':load['expected_game_sha256']}
                report=module.execute_route(runtime,route_fixture(),context,lambda:False)
                self.assertEqual(report['status'],'PASS',report)
                self.assertEqual(report['observations'][0]['actual_hex'],'0908')
                state=report['checkpoints'][0]['snapshot']
                runtime.request('load_state',snapshot=state)
                failing=route_fixture();failing['steps'][0]['assertions'][0]['expected_hex']='0000'
                failed=module.execute_route(runtime,failing,context,lambda:False)
                self.assertEqual(failed['status'],'FAIL');self.assertEqual(failed['observations'][0]['actual_hex'],'0a08')
                cancelled=module.execute_route(runtime,route_fixture(),context,lambda:True)
                self.assertEqual(cancelled['status'],'CANCELLED')
                saved=runtime.request('save_game');runtime.close_verified()
            continued={**load,'session_dir':str(root/'continued'),'game_save':{k:saved[k] for k in ('core_sha256','game_sha256','sha256','save_ram_base64')}}
            with OwnedRuntime(preflight_load(continued,root,allow_game_save=True),10) as runtime:
                report=module.execute_route(runtime,route_fixture(),context,lambda:False)
                self.assertEqual(report['status'],'PASS',report)
                observed=runtime.request('save_game')
                self.assertEqual(observed['run_mode'],'game_save_continuation')
                self.assertFalse(observed['in_game_save_event_verified'])
                runtime.close_verified()
            self.assertEqual(game.read_bytes(),b'original route fixture')
