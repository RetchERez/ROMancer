import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import tempfile
import time
import unittest
from unittest.mock import patch


class WorkerProtocolTests(unittest.TestCase):
    def client(self, **kwargs):
        from romancer.runtime_client import RuntimeClient
        return RuntimeClient([sys.executable, '-m', 'romancer.runtime_worker'], **kwargs)

    @unittest.skipUnless(os.name=='nt','Windows venv redirector ownership')
    def test_windows_virtualenv_worker_owns_the_actual_child_and_keeps_site_packages(self):
        try:import venv
        except ImportError:self.skipTest('standalone embedded Python has no venv builder')
        with tempfile.TemporaryDirectory(prefix='romancer venv ') as folder:
            root=Path(folder)/'environment'
            venv.EnvBuilder(with_pip=False,system_site_packages=True).create(root)
            (root/'Lib/site-packages/romancer_venv_probe.py').write_text('VALUE=73',encoding='utf-8')
            code=textwrap.dedent("""
                import sys
                from pathlib import Path
                from romancer.runtime_client import RuntimeClient
                assert Path(sys.prefix)==Path(sys.argv[1])
                worker='import sys;sys.path.insert(0,'+repr(str(Path.cwd()))+');import romancer_venv_probe;assert romancer_venv_probe.VALUE==73;from romancer.runtime_worker import main;main()'
                for flags in ([],['-I','-B']):
                    with RuntimeClient([sys.executable,*flags,'-c',worker],timeout=10) as client:
                        assert client.request('hello')['ok']
                        owned=client.process
                    assert owned.poll() is not None
            """)
            result=subprocess.run([str(root/'Scripts/python.exe'),'-B','-c',code,str(root)],
                                  cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_real_child_handshake_and_close(self):
        with self.client() as client:
            process = client.process
            reply = client.request('hello')
            self.assertTrue(reply['ok'])
            self.assertFalse(reply['core_loaded'])
            self.assertEqual(reply['protocol_version'], 1)
        self.assertIsNotNone(process.poll())

    def test_unloaded_and_unknown_operations_fail_without_crashing(self):
        with self.client() as client:
            self.assertFalse(client.request('advance', frames=1)['ok'])
            self.assertFalse(client.request('not_an_operation')['ok'])
            self.assertTrue(client.request('hello')['ok'])

    def test_startup_timeout_reaps_child(self):
        from romancer.runtime_client import RuntimeClient, RuntimeWorkerError
        created = []
        real = subprocess.Popen

        def start(*args, **kwargs):
            child = real(*args, **kwargs)
            created.append(child)
            return child

        with patch('romancer.runtime_client.subprocess.Popen', side_effect=start):
            with self.assertRaises(RuntimeWorkerError):
                RuntimeClient([sys.executable, '-c', 'import time; time.sleep(60)'], timeout=0.15)
        self.assertEqual(len(created), 1)
        self.assertIsNotNone(created[0].poll())

    def test_malformed_startup_and_early_exit_reap_child(self):
        from romancer.runtime_client import RuntimeClient, RuntimeWorkerError
        for script in ["print('not json',flush=True)", 'raise SystemExit(7)',
                       "print('x'*70000,flush=True)"]:
            with self.subTest(script=script[:30]), self.assertRaises(RuntimeWorkerError):
                RuntimeClient([sys.executable, '-c', script], timeout=1)

    def test_invalid_client_parameters(self):
        from romancer.runtime_client import RuntimeClient
        for command, timeout in [([], 1), ('python', 1), ([sys.executable], True),
                                  ([sys.executable], float('inf')), ([sys.executable], 0), (['wsl'], 1)]:
            with self.subTest(command=command, timeout=timeout), self.assertRaises(ValueError):
                RuntimeClient(command, timeout=timeout)

    def test_maximum_state_fits_request_protocol(self):
        from romancer.runtime_protocol import REQUEST_LIMIT, encode, decode
        data = base64.b64encode(b'X' * (8 * 1024 * 1024)).decode('ascii')
        packet = {'protocol_version': 1, 'id': 1, 'operation': 'load_state',
                  'parameters': {'snapshot': {'state_base64': data}}}
        encoded = encode(packet, REQUEST_LIMIT)
        self.assertEqual(decode(encoded, REQUEST_LIMIT), packet)

    def test_worker_rejects_unauthenticated_malformed_and_oversized_requests(self):
        from romancer.runtime_protocol import REQUEST_LIMIT
        for mode in ('token', 'version', 'repeated-id', 'bool-id', 'duplicate-key', 'oversized'):
            with self.subTest(mode=mode), self.client(timeout=3) as client:
                packet = {'protocol_version': 1, 'id': 2, 'token': client._token,
                          'operation': 'hello', 'timeout': 3, 'parameters': {}}
                if mode == 'token':
                    packet['token'] = '0' * 64
                elif mode == 'version':
                    packet['protocol_version'] = 2
                elif mode == 'repeated-id':
                    packet['id'] = 1
                elif mode == 'bool-id':
                    packet['id'] = True
                payload = (json.dumps(packet) + '\n').encode()
                if mode == 'duplicate-key':
                    payload = b'{"id":2,"id":2}\n'
                elif mode == 'oversized':
                    payload = b'x' * (REQUEST_LIMIT + 1) + b'\n'
                try:
                    client.socket.sendall(payload)
                    self.assertEqual(client.socket.recv(1), b'')
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                client.process.wait(timeout=3)
                self.assertIsNotNone(client.process.poll())

    def test_state_payload_one_over_limit_rejected_before_native_call(self):
        from romancer.runtime_worker import STATE_LIMIT, Workspace
        data = b'X' * (STATE_LIMIT + 1)
        workspace = Workspace()
        from unittest.mock import Mock
        frontend = Mock()
        workspace.frontend = frontend
        with self.assertRaises(ValueError):
            workspace.handle('load_state', {'snapshot': {
                'state_base64': base64.b64encode(data).decode('ascii'),
                'sha256': hashlib.sha256(data).hexdigest()}})
        frontend.unserialize.assert_not_called()
        frontend.close.assert_not_called()

    def test_maximum_state_round_trips_real_socket(self):
        from romancer.runtime_client import RuntimeClient
        script = textwrap.dedent('''
            import json, os, socket
            s = socket.socket()
            s.bind(('127.0.0.1',0))
            s.listen(1)
            print(json.dumps({'protocol_version':1,'pid':os.getpid(),'port':s.getsockname()[1]}),flush=True)
            c,_ = s.accept()
            with c, c.makefile('rb') as r:
                while line := r.readline(16*1024*1024+1):
                    q = json.loads(line)
                    result = {'ok':True,'protocol_version':1}
                    if q['operation']=='echo':
                        result['snapshot'] = q['parameters']['snapshot']
                    c.sendall((json.dumps({'protocol_version':1,'id':q['id'],'result':result})+'\\n').encode())
                    if q['operation']=='close':
                        break
        ''')
        data = b'X' * (8 * 1024 * 1024)
        snapshot = {'state_base64': base64.b64encode(data).decode('ascii'),
                    'sha256': hashlib.sha256(data).hexdigest()}
        with RuntimeClient([sys.executable, '-c', script]) as client:
            result = client.request('echo', snapshot=snapshot)
            self.assertEqual(result['snapshot'], snapshot)

    def test_loader_uses_verified_owned_snapshots(self):
        from romancer.runtime_worker import Workspace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core, game = root / 'core.so', root / 'game.bin'
            core.write_bytes(b'core')
            game.write_bytes(b'game')
            track = root / 'track.bin'
            track.write_bytes(b'track')
            seen = []

            class Frontend:
                def __init__(self, path, **_):
                    core.write_bytes(b'changed core')
                    game.write_bytes(b'changed game')
                    track.write_bytes(b'changed track')
                    seen.append(Path(path).read_bytes())

                def load_game(self, path):
                    seen.append(Path(path).read_bytes())
                    seen.append((Path(path).parent / 'tracks' / 'track.bin').read_bytes())
                    return {}

                def memory_region(self, _):
                    return b''

                def av_info(self):
                    return {}

                def close(self):
                    pass

            with patch('romancer.runtime_worker.LibretroFrontend', Frontend):
                workspace = Workspace()
                result = workspace.load({'core': str(core), 'game': str(game),
                                         'expected_core_sha256': hashlib.sha256(b'core').hexdigest(),
                                         'expected_game_sha256': hashlib.sha256(b'game').hexdigest(),
                                         'game_dependencies': [{'source': str(track), 'relative': 'tracks/track.bin',
                                                                'expected_sha256': hashlib.sha256(b'track').hexdigest()}],
                                         'session_dir': str(root / 'session')})
                self.assertTrue(result['ok'])
                workspace.close()
            self.assertEqual(seen, [b'core', b'game', b'track'])

    def test_dependency_paths_are_validated_before_native_loading(self):
        from romancer.runtime_worker import Workspace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core, game = root / 'core.so', root / 'game.bin'
            core.write_bytes(b'core')
            game.write_bytes(b'game')
            relatives = ['../outside', '/absolute', 'game.bin', 'a//b', 'a/./b', 'C:/bad']
            if sys.platform == 'win32':
                relatives.append('CON')
            for relative in relatives:
                with self.subTest(relative=relative), patch('romancer.runtime_worker.LibretroFrontend') as frontend:
                    workspace = Workspace()
                    with self.assertRaises(ValueError):
                        workspace.load({'core': str(core), 'game': str(game),
                                        'expected_core_sha256': hashlib.sha256(b'core').hexdigest(),
                                        'expected_game_sha256': hashlib.sha256(b'game').hexdigest(),
                                        'session_dir': str(root / 'session'),
                                        'game_dependencies': [{'source': str(game), 'relative': relative,
                                                               'expected_sha256': hashlib.sha256(b'game').hexdigest()}]})
                    frontend.assert_not_called()
                    self.assertFalse((root / 'session').exists())

    def test_transport_failure_reaps_owned_process(self):
        from romancer.runtime_client import RuntimeClient, RuntimeWorkerError
        script = textwrap.dedent('''
            import json, os, socket, sys, time
            s = socket.socket()
            s.bind(('127.0.0.1', 0))
            s.listen(1)
            print(json.dumps({'protocol_version':1,'pid':os.getpid(),'port':s.getsockname()[1]}),flush=True)
            c,_ = s.accept()
            r = c.makefile('rb')
            first = json.loads(r.readline())
            c.sendall((json.dumps({'protocol_version':1,'id':first['id'],
                                  'result':{'ok':True,'protocol_version':1,'core_loaded':False}})+'\\n').encode())
            second = json.loads(r.readline())
            mode = sys.argv[1]
            if mode == 'hang':
                time.sleep(60)
            elif mode == 'exit':
                os._exit(9)
            elif mode == 'wrong-id':
                c.sendall((json.dumps({'protocol_version':1,'id':second['id']+1,'result':{'ok':True}})+'\\n').encode())
            elif mode == 'slow':
                response = (json.dumps({'protocol_version':1,'id':second['id'],'result':{'ok':True}})+'\\n').encode()
                for offset in range(0, len(response), 8):
                    c.sendall(response[offset:offset+8])
                    time.sleep(0.15)
            else:
                c.sendall(b'not JSON\\n')
            time.sleep(60)
        ''')
        for mode in ('hang', 'exit', 'wrong-id', 'malformed', 'slow'):
            with self.subTest(mode=mode), RuntimeClient([sys.executable, '-c', script, mode], timeout=1) as client:
                process = client.process
                started = time.monotonic()
                with self.assertRaises(RuntimeWorkerError):
                    client.request('probe')
                self.assertLess(time.monotonic() - started, 1.8)
                self.assertIsNotNone(process.poll())
                client.close()


@unittest.skipUnless(shutil.which('gcc') and sys.platform != 'win32', 'native GCC mock core requires Linux/WSL')
class CompiledWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='romancer_worker_core_')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.core = cls.root / 'mock.so'
        source = Path(__file__).resolve().parent / 'mock_libretro.c'
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-DROMANCER_V35_TEST',
                        str(source), '-o', str(cls.core)], check=True, capture_output=True)
        cls.core_hash = hashlib.sha256(cls.core.read_bytes()).hexdigest()
        cls.hang_core = cls.root / 'hang.so'
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2', str(source.with_name('mock_worker_hang.c')),
                        '-o', str(cls.hang_core)], check=True, capture_output=True)

    def setUp(self):
        from romancer.runtime_client import RuntimeClient
        self.temp = tempfile.TemporaryDirectory(prefix='romancer session ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'fixture.bin'
        self.game.write_bytes(b'synthetic game')
        self.game_hash = hashlib.sha256(self.game.read_bytes()).hexdigest()
        self.argv = [sys.executable, '-m', 'romancer.runtime_worker']
        self.client_type = RuntimeClient

    def load(self, client, name='session', **extra):
        return client.request('load', core=str(self.core), game=str(self.game),
                              expected_core_sha256=self.core_hash, expected_game_sha256=self.game_hash,
                              session_dir=str(self.root / name), **extra)

    def test_input_capture_audio_and_state_restore(self):
        with self.client_type(self.argv) as client:
            self.assertTrue(self.load(client)['ok'])
            first = client.request('advance', frames=1, buttons=[])
            snapshot = client.request('save_state')
            self.assertTrue(snapshot['ok'])
            client.request('advance', frames=1, buttons=['RIGHT'])
            moved = client.request('capture')
            self.assertTrue(moved['ok'])
            self.assertNotEqual(moved['sha256'], first['frame']['sha256'])
            rgb = base64.b64decode(moved['rgb24_base64'], validate=True)
            self.assertEqual(hashlib.sha256(rgb).hexdigest(), moved['sha256'])
            self.assertTrue(any(rgb))
            audio = client.request('audio')
            pcm = base64.b64decode(audio['pcm_s16le_base64'], validate=True)
            self.assertGreater(len(pcm), 0)
            self.assertEqual(len(pcm), audio['captured_frames'] * 4)
            restored = client.request('load_state', snapshot=snapshot)
            self.assertTrue(restored['ok'])
            self.assertFalse(client.request('capture')['ok'], 'stale frame survived state import')
            again = client.request('advance', frames=1, buttons=[])
            self.assertEqual(again['run_mode'], 'imported_save_state')
            self.assertEqual(again['frame']['sha256'], first['frame']['sha256'])

    def test_normal_game_save_continues_in_fresh_worker(self):
        with self.client_type(self.argv) as client:
            self.assertTrue(self.load(client)['ok'])
            client.request('advance', frames=1, buttons=['A'])
            checkpoint = client.request('save_game')
            self.assertTrue(checkpoint['ok'])
        with self.client_type(self.argv) as other:
            result = self.load(other, 'continued', game_save=checkpoint)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['run_mode'], 'game_save_continuation')
            saved_again = other.request('save_game')
            self.assertEqual(saved_again['sha256'], checkpoint['sha256'])
        self.assertEqual(self.game.read_bytes(), b'synthetic game')

    def test_state_derived_save_keeps_provenance_in_new_worker(self):
        with self.client_type(self.argv) as client:
            self.assertTrue(self.load(client)['ok'])
            state = client.request('save_state')
            self.assertTrue(client.request('load_state', snapshot=state)['ok'])
            checkpoint = client.request('save_game')
            self.assertTrue(checkpoint['provenance']['state_derived'])
        with self.client_type(self.argv) as other:
            result = self.load(other, 'continued', game_save=checkpoint)
            self.assertTrue(result['ok'], result)
            self.assertTrue(result['provenance']['state_derived'])
            self.assertEqual(result['provenance']['ancestor_state_sha256'], state['sha256'])
            self.assertFalse(result['natural_progress_verified'])

    def test_missing_save_provenance_remains_unknown(self):
        with self.client_type(self.argv) as client:
            self.assertTrue(self.load(client)['ok'])
            checkpoint = client.request('save_game')
        checkpoint.pop('provenance')
        with self.client_type(self.argv) as other:
            result = self.load(other, 'continued', game_save=checkpoint)
            self.assertTrue(result['ok'], result)
            self.assertIsNone(result['provenance']['state_derived'])
            self.assertFalse(result['natural_progress_verified'])
            self.assertFalse(self.load(other, 'second-load')['ok'])
            self.assertFalse((self.root / 'second-load').exists())

    def test_bad_hash_and_existing_session_fail_before_loading_core(self):
        with self.client_type(self.argv) as client:
            reply = client.request('load', core=str(self.core), game=str(self.game),
                                    expected_core_sha256='0' * 64, expected_game_sha256=self.game_hash,
                                    session_dir=str(self.root / 'bad'))
            self.assertFalse(reply['ok'])
            self.assertFalse((self.root / 'bad').exists())
            self.assertFalse(client.request('hello')['core_loaded'])
            self.root.joinpath('occupied').mkdir()
            self.assertFalse(self.load(client, 'occupied')['ok'])

    def test_frame_budget_and_wrong_state_hash_rejected(self):
        with self.client_type(self.argv) as client:
            self.assertTrue(self.load(client)['ok'])
            for frames in (True, 0, -1, 601):
                self.assertFalse(client.request('advance', frames=frames)['ok'])
            self.assertFalse(client.request('advance', frames=1, buttons=['UNKNOWN'])['ok'])
            saved = client.request('save_state')
            saved['sha256'] = '0' * 64
            self.assertFalse(client.request('load_state', snapshot=saved)['ok'])
            self.assertTrue(client.request('advance', frames=1)['ok'])

    def test_native_stall_terminates_worker_and_preserves_checkpoint(self):
        from romancer.runtime_client import RuntimeWorkerError
        self.core = self.hang_core
        self.core_hash = hashlib.sha256(self.core.read_bytes()).hexdigest()
        with self.client_type(self.argv, timeout=1) as client:
            self.assertTrue(self.load(client)['ok'])
            saved = client.request('save_game')
            process = client.process
            with self.assertRaises(RuntimeWorkerError):
                client.request('advance', frames=1)
            self.assertIsNotNone(process.poll())
            self.assertEqual(hashlib.sha256(Path(saved['path']).read_bytes()).hexdigest(), saved['sha256'])


if __name__ == '__main__':
    unittest.main()
