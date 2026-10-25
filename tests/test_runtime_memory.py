import ctypes
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class MemoryTests(unittest.TestCase):
    def test_environment_polling_does_not_retain_per_frame_records(self):
        import gc,tracemalloc
        from romancer.libretro_frontend import LibretroFrontend,RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE
        frontend=LibretroFrontend.__new__(LibretroFrontend);frontend.environment_log=[];frontend.messages=[]
        flag=ctypes.c_bool();pointer=ctypes.addressof(flag)
        tracemalloc.start()
        try:
            before=tracemalloc.get_traced_memory()[0]
            for _ in range(20000):self.assertTrue(frontend._environment(RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE,pointer))
            gc.collect();retained=tracemalloc.get_traced_memory()[0]-before
            self.assertLess(retained,512*1024,'Core polling must not retain a dictionary per callback.')
            self.assertFalse(flag.value)
        finally:tracemalloc.stop()

    def test_idle_cleanup_continues_after_a_worker_close_failure(self):
        import threading,time
        from romancer.workbench_runtime import RuntimePool
        class Runtime:
            exit_code=0
            def __init__(self,fail):self.fail=fail;self.exited=False
            def close_verified(self):
                if self.fail:raise RuntimeError('worker has exited')
            def __exit__(self,*args):self.exited=True
        class Stop:
            def __init__(self):self.waits=0
            def wait(self,seconds):self.waits+=1;return self.waits>1
        pool=RuntimePool.__new__(RuntimePool);pool.lock=threading.RLock();pool.stopping=Stop()
        bad,good=Runtime(True),Runtime(False)
        pool.sessions={'bad':{'runtime':bad,'touched':time.monotonic()-400},'good':{'runtime':good,'touched':time.monotonic()-400}}
        pool._expire()
        self.assertEqual(pool.sessions,{})
        self.assertTrue(bad.exited and good.exited)

    def test_capability_and_bounded_read_do_not_advance_or_mutate(self):
        from romancer.runtime_worker import Workspace
        workspace=Workspace()
        hello=workspace.handle('hello',{})
        self.assertIn('memory_read',hello,'the bounded native read port is missing')
        data=(ctypes.c_ubyte*4)(8,8,0,255)
        class Library:
            def retro_get_memory_size(self,region):return 4
            def retro_get_memory_data(self,region):return ctypes.addressof(data)
        class Frontend:
            lib=Library();frame_index=7;core_options={}
        workspace.frontend=Frontend()
        result=workspace.handle('read_memory',{'region':2,'offset':3,'length':1})
        self.assertEqual(result['raw_hex'],'ff')
        self.assertFalse(result['memory_written'])
        self.assertEqual(bytes(data),b'\x08\x08\x00\xff')
        self.assertEqual(workspace.frontend.frame_index,7)
        self.assertEqual(result['sequence'],1)
        with self.assertRaises(ValueError):workspace.handle('read_memory',{'region':2,'offset':4,'length':1})
        self.assertIsNotNone(workspace.frontend)

    def test_invalid_requests_never_call_native_symbols(self):
        from romancer.runtime_worker import Workspace
        workspace=Workspace()
        self.assertIn('memory_read',workspace.handle('hello',{}),'memory read port missing')
        class Frontend:
            @property
            def lib(self):raise AssertionError('malformed input reached the core')
        workspace.frontend=Frontend()
        for parameters in [{'region':True,'offset':0,'length':1},{'region':4,'offset':0,'length':1},
                           {'region':2,'offset':0,'length':4097},{'region':2,'offset':-1,'length':1},
                           {'region':2,'offset':0,'length':1,'pointer':1}]:
            with self.assertRaises(ValueError):workspace.handle('read_memory',parameters)

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('gcc'),'Linux native compiled worker check')
    def test_actual_worker_reads_compiled_core_then_right_input(self):
        from romancer.runtime_client import RuntimeClient
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'mock.so';game=root/'game.bin';game.write_bytes(b'fixture')
            subprocess.run(['gcc','-shared','-fPIC','-O2','-DROMANCER_V35_TEST','tests/mock_libretro.c','-o',str(core)],check=True)
            with RuntimeClient([sys.executable,'-m','romancer.runtime_worker'],timeout=10) as client:
                result=client.request('load',core=str(core),game=str(game),session_dir=str(root/'session'),
                                      expected_core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),expected_game_sha256=hashlib.sha256(game.read_bytes()).hexdigest())
                self.assertTrue(result['ok'],result)
                self.assertEqual(client.request('read_memory',region=2,offset=0,length=2)['raw_hex'],'0808')
                self.assertTrue(client.request('advance',frames=1,buttons=['right'],port=0)['ok'])
                self.assertEqual(client.request('read_memory',region=2,offset=0,length=2)['raw_hex'],'0908')
