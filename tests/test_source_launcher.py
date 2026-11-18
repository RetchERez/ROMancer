import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unittest

@unittest.skipUnless(os.name=='nt' and shutil.which('py.exe'),'Windows source Python discovery')
class SourceLauncherTests(unittest.TestCase):
    def launch(self,workspace):
        script=Path(__file__).resolve().parents[1]/'launch.ps1'
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-NoBrowser','-Workspace',str(workspace)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
        value=json.loads((workspace/'connection.json').read_bytes());self.pids.add(value['pid']);return value

    def setUp(self):self.pids=set()
    def stop_owned(self):
        import ctypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True);kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p;kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        for pid in self.pids:
            if pid>0:
                handle=kernel.OpenProcess(0x100000,False,pid)
                try:
                    try:os.kill(pid,signal.SIGTERM)
                    except OSError:pass
                    if handle:kernel.WaitForSingleObject(handle,5000)
                finally:
                    if handle:kernel.CloseHandle(handle)
        self.pids.clear()

    def tearDown(self):self.stop_owned()

    def test_normal_discovery_reuses_matching_product_server(self):
        with tempfile.TemporaryDirectory() as folder:
            try:
                workspace=Path(folder)/'ROMancer unicode & workspace';workspace.mkdir();first=self.launch(workspace);second=self.launch(workspace)
                self.assertEqual(first['pid'],second['pid'],'normal py.exe discovery started a duplicate same-version server')
            finally:self.stop_owned()

    def test_same_version_with_a_different_application_root_is_not_reused(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length','0')));raw=b'{"ok":true,"product":"ROMancer","version":"1.3.0"}';self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                try:
                    workspace=Path(folder);(workspace/'connection.json').write_text(json.dumps({'pid':0,'application_root':str(workspace/'other-app'),'url':f'http://127.0.0.1:{server.server_port}/#token=fixture'}),encoding='utf-8');value=self.launch(workspace);self.assertNotEqual(value['pid'],0)
                finally:self.stop_owned()
        finally:server.shutdown();server.server_close()
