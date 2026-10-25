"""Synthetic recorder tests; response doubles never establish native acceptance."""
import base64
import copy
from contextlib import closing
import hashlib
import importlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from romancer import history
from romancer.runtime_client import RuntimeClient


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RuntimeFixture(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.capture_runtime'),
                             'native recorder service has not been implemented')
        self.runtime = importlib.import_module('romancer.capture_runtime')
        self.temp = tempfile.TemporaryDirectory(prefix='capture runtime fixture ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.source = self.root / 'original.bin'
        self.game = self.root / 'game.bin'
        self.source.write_bytes(b'synthetic original')
        self.game.write_bytes(b'synthetic game')
        if not hasattr(self, 'core'):
            self.core = self.root / 'not a native core.bin'
            self.core.write_bytes(b'not executed by portable controls')
        history.init_history(self.project)
        self.build = history.register_build(self.project, {
            'inputs': [{'role': 'original', 'path': str(self.source)}],
            'output': str(self.game), 'adapter': {'name': 'generic', 'version': '1'},
            'profile': {'name': 'synthetic', 'version': '1'}, 'settings': {},
        }, self.root)
        self.config = {
            'load': {'core': str(self.core), 'game': str(self.game),
                     'expected_core_sha256': digest(self.core.read_bytes()),
                     'expected_game_sha256': digest(self.game.read_bytes()),
                     'session_dir': str(self.root / 'new session')},
            'steps': [{'frames': 1, 'buttons': ['RIGHT'], 'port': 0}],
            'initial_state_file': None, 'timeout': 10,
        }

    def documented_config(self):
        root = Path(__file__).resolve().parents[1]
        path = root / 'README.txt'
        if not path.exists():path = root.parent / 'README.txt'
        config = json.loads(path.read_text(encoding='utf-8').split('BEGIN CAPTURE JSON', 1)[1].split('END CAPTURE JSON', 1)[0])
        self.assertEqual(set(config), {'load', 'steps', 'initial_state_file', 'timeout'})
        config['load']['core'] = str(self.core)
        config['load']['expected_core_sha256'] = digest(self.core.read_bytes())
        config['load']['expected_game_sha256'] = digest(self.game.read_bytes())
        return config

    def inline_save(self, payload):
        return {'save_ram_base64': base64.b64encode(payload).decode(), 'sha256': digest(payload),
                'core_sha256': self.config['load']['expected_core_sha256'],
                'game_sha256': self.config['load']['expected_game_sha256']}

    def run_capture(self, config=None):
        return self.runtime.capture_run(self.project, self.build['build_id'],
                                        self.config if config is None else config, self.root)

    def blocked(self, config):
        existed = Path(self.config['load']['session_dir']).exists()
        with patch.object(self.runtime, 'RuntimeClient') as launch:
            result = self.run_capture(config)
        self.assertIs(result['ok'], False, result)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIs(result['written'], False)
        launch.assert_not_called()
        self.assertEqual(Path(self.config['load']['session_dir']).exists(), existed)


class PortablePreflightTests(RuntimeFixture):
    def checkpoint_config(self, route, snapshot):
        config = copy.deepcopy(self.config)
        if route == 'inline':
            config['load']['game_save'] = snapshot
        else:
            snapshot = dict(snapshot)
            snapshot['state_base64'] = snapshot.pop('save_ram_base64')
            path = self.root / 'structure state.json'
            path.write_text(json.dumps(snapshot), encoding='utf-8')
            config['initial_state_file'] = str(path)
        return config

    def assert_launch_boundary(self, config):
        with patch.object(self.runtime, 'RuntimeClient', side_effect=RuntimeError('launch boundary')) as launch:
            result = self.run_capture(config)
        self.assertIn('launch boundary', result['error'], result)
        launch.assert_called_once()

    def test_drive_relative_spelling_rejected_before_path_construction(self):
        for name in ('C:game.bin', 'C:core.bin', 'C:new session', 'D:', 'z:state.json'):
            with self.subTest(path=name), patch.object(self.runtime, 'Path') as path:
                with self.assertRaisesRegex(ValueError, 'drive-relative'):
                    self.runtime._path(name, self.root)
                path.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows drive-relative resolution regression')
    def test_drive_relative_public_inputs_and_session_never_launch(self):
        for field in ('core', 'game', 'session_dir'):
            config = copy.deepcopy(self.config)
            config['load'][field] = self.root.drive + Path(config['load'][field]).name
            with self.subTest(field=field):
                self.blocked(config)

    def test_normal_relative_and_absolute_paths_reach_launch(self):
        self.assert_launch_boundary(copy.deepcopy(self.config))
        config = copy.deepcopy(self.config)
        for field in ('core', 'game', 'session_dir'):
            config['load'][field] = str(Path(config['load'][field]).relative_to(self.root))
        self.assert_launch_boundary(config)

    def test_complete_json_depth_boundary_inline_and_state(self):
        for route, extra_depth in (('inline', 3), ('state', 1)):
            for depth in (32, 33, 38):
                extra = None
                for _ in range(depth - extra_depth):
                    extra = [extra]
                snapshot = dict(self.inline_save(b'synthetic checkpoint'), extra=extra)
                config = self.checkpoint_config(route, snapshot)
                with self.subTest(route=route, depth=depth):
                    if depth == 32:
                        self.assert_launch_boundary(config)
                    else:
                        self.blocked(config)

    def test_complete_json_node_boundary_inline_and_state(self):
        def nodes(value):
            pending, total = [value], 0
            while pending:
                item = pending.pop()
                total += 1
                if type(item) is dict:
                    pending.extend(item.keys())
                    pending.extend(item.values())
                elif type(item) is list:
                    pending.extend(item)
            return total
        for route in ('inline', 'state'):
            snapshot = dict(self.inline_save(b'synthetic checkpoint'), extra=[])
            config = self.checkpoint_config(route, snapshot)
            overhead = nodes(config if route == 'inline' else snapshot)
            for count in (10000, 10001):
                snapshot['extra'] = [None] * (count - overhead)
                config = self.checkpoint_config(route, snapshot)
                self.assertEqual(nodes(config if route == 'inline' else snapshot), count)
                with self.subTest(route=route, nodes=count):
                    if count == 10000:
                        self.assert_launch_boundary(config)
                    else:
                        self.blocked(config)

    def test_documented_four_field_config_reaches_launch(self):
        config = self.documented_config()
        with patch.object(self.runtime, 'RuntimeClient', side_effect=RuntimeError('launch boundary')) as launch:
            result = self.run_capture(config)
        self.assertIn('launch boundary', result['error'], result)
        launch.assert_called_once()

    def test_undocumented_game_save_file_is_rejected(self):
        config = dict(self.config, game_save_file=None)
        self.blocked(config)

    def test_inline_save_exact_config_limit_and_one_byte_over(self):
        config = copy.deepcopy(self.config)
        config['load']['game_save'] = self.inline_save(b'')
        config['load']['core_options'] = {'fixture_padding': ''}
        limit = 1024 * 1024
        overhead = len(history.canonical_json(config, max_bytes=limit).encode('utf-8'))
        payload = b'S' * ((limit - overhead) // 4 * 3)
        config['load']['game_save'] = self.inline_save(payload)
        remaining = limit - len(history.canonical_json(config, max_bytes=limit).encode('utf-8'))
        config['load']['core_options']['fixture_padding'] = 'x' * remaining
        self.assertEqual(len(history.canonical_json(config, max_bytes=limit).encode('utf-8')), limit)
        before = copy.deepcopy(config)
        with patch.object(self.runtime, 'RuntimeClient', side_effect=RuntimeError('launch boundary')) as launch:
            result = self.run_capture(config)
        self.assertIn('launch boundary', result['error'], result)
        launch.assert_called_once()
        self.assertEqual(config, before)
        config['load']['core_options']['fixture_padding'] += 'x'
        self.assertEqual(len(history.canonical_json(config, max_bytes=limit + 1).encode()), limit + 1)
        self.blocked(config)

    def test_oversized_or_invalid_inline_save_stops_launch(self):
        valid = self.inline_save(b'synthetic SRAM')
        for save in ({}, False, [], dict(valid, save_ram_base64='%%%'),
                     dict(valid, sha256='0' * 64), dict(valid, core_sha256='0' * 64),
                     dict(valid, game_sha256='0' * 64), self.inline_save(b''),
                     self.inline_save(b'S' * (1024 * 1024))):
            config = copy.deepcopy(self.config)
            config['load']['game_save'] = save
            with self.subTest(kind=type(save).__name__, empty=not save):
                self.blocked(config)

    def test_session_cannot_modify_history_or_evidence_store(self):
        for name in ('.romancer-history', '.romancer-evidence'):
            self.config['load']['session_dir'] = str(self.project / name / 'new session')
            with self.subTest(store=name):
                self.blocked(self.config)

    def test_large_checkpoint_is_separate_from_configuration_budget(self):
        for size in (1024 * 1024 + 1, 8 * 1024 * 1024):
            payload = b'X' * size
            value = {'state_base64': base64.b64encode(payload).decode(), 'sha256': digest(payload),
                     'core_sha256': self.config['load']['expected_core_sha256'],
                     'game_sha256': self.config['load']['expected_game_sha256']}
            path = self.root / 'large state.json'
            path.write_text(json.dumps(value), encoding='utf-8')
            self.config['initial_state_file'] = str(path)
            with self.subTest(size=size), patch.object(self.runtime, 'RuntimeClient',
                    side_effect=RuntimeError('preflight reached launch boundary')) as launch:
                result = self.run_capture()
                launch.assert_called_once()
                self.assertFalse(result['ok'])
                self.assertIn('launch boundary', result['error'])
        payload += b'X'
        value.update(state_base64=base64.b64encode(payload).decode(), sha256=digest(payload))
        path.write_text(json.dumps(value), encoding='utf-8')
        self.blocked(self.config)

    def test_inline_game_save_and_full_envelope_preflight(self):
        self.config['load']['game_save'] = self.inline_save(b'S' * 1024)
        with patch.object(self.runtime, 'RuntimeClient', side_effect=RuntimeError('launch boundary')) as launch:
            self.assertFalse(self.run_capture()['ok'])
            launch.assert_called_once()
        with patch.object(self.runtime.runtime_protocol, 'REQUEST_LIMIT', 1024):
            self.blocked(self.config)

    def test_config_limit_fails_before_launch(self):
        config = copy.deepcopy(self.config)
        config['extra'] = 'x' * (1024 * 1024)
        self.blocked(config)

    def test_linked_checkpoint_fails_before_launch(self):
        target = self.root / 'target.json'
        target.write_text('{}')
        linked = self.root / 'linked.json'
        try:
            linked.symlink_to(target)
        except OSError as exc:
            self.skipTest(f'symlink creation unavailable: {exc}')
        self.config['initial_state_file'] = str(linked)
        self.blocked(self.config)

    def test_checkpoint_growth_is_detected_with_bounded_reads(self):
        path = self.root / 'growing.json'
        path.write_bytes(b'x' * 100)
        original_open = Path.open
        sizes = []
        class Reader:
            def __init__(self, stream):
                self.stream = stream
                self.changed = False
            def __enter__(self):
                return self
            def __exit__(self, *_):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def read(self, size):
                sizes.append(size)
                data = self.stream.read(size)
                if not self.changed:
                    self.changed = True
                    with original_open(path, 'ab') as writer:
                        writer.write(b'x' * 100)
                return data
        def opening(candidate, *args, **kwargs):
            stream = original_open(candidate, *args, **kwargs)
            return Reader(stream) if candidate == path and args == ('rb',) else stream
        with patch.object(Path, 'open', opening), self.assertRaisesRegex(ValueError, 'budget|changed'):
            self.runtime._read_stable(path, 150)
        self.assertTrue(sizes)
        self.assertLessEqual(max(sizes), 151)

    def test_exact_config_fields_no_reply_ingestion(self):
        for key in self.config:
            config = copy.deepcopy(self.config)
            del config[key]
            with self.subTest(missing=key):
                self.blocked(config)
        for key in ('origin', 'reply', 'verified', 'worker_argv'):
            config = copy.deepcopy(self.config)
            config[key] = 'native_worker'
            with self.subTest(extra=key):
                self.blocked(config)

    def test_finite_positive_timeout_and_exact_step_bounds(self):
        for value in (True, None, 0, -1, 121, float('inf'), float('nan')):
            config = copy.deepcopy(self.config)
            config['timeout'] = value
            with self.subTest(timeout=value):
                self.blocked(config)
        for value in (True, 0, -1, 601, 1.0):
            config = copy.deepcopy(self.config)
            config['steps'][0]['frames'] = value
            with self.subTest(frames=value):
                self.blocked(config)
        for value in (True, -1, 4, 0.0):
            config = copy.deepcopy(self.config)
            config['steps'][0]['port'] = value
            with self.subTest(port=value):
                self.blocked(config)

    def test_steps_nonempty_count_total_and_buttons(self):
        for steps in ([], [self.config['steps'][0]] * 101,
                      [{'frames': 600, 'buttons': [], 'port': 0}] * 11,
                      [{'frames': 1, 'buttons': ['UNKNOWN'], 'port': 0}],
                      [{'frames': 1, 'buttons': 'A', 'port': 0}],
                      [{'frames': 1, 'buttons': [], 'port': 0, 'label': 'victory'}]):
            config = copy.deepcopy(self.config)
            config['steps'] = steps
            with self.subTest(steps=steps):
                self.blocked(config)

    def test_invalid_save_unknown_load_fields_and_bad_options(self):
        for key, value in (('game_save', {}), ('invented', True),
                           ('core_options', {'key': False}), ('game_dependencies', 'bad')):
            config = copy.deepcopy(self.config)
            config['load'][key] = value
            with self.subTest(key=key):
                self.blocked(config)

    def test_mismatching_build_output_stops_launch(self):
        self.config['load']['expected_game_sha256'] = 'a' * 64
        self.blocked(self.config)

    def test_stale_registered_source_stops_launch(self):
        self.source.write_bytes(b'changed original')
        self.blocked(self.config)

    def test_existing_session_and_unsafe_paths_stop_launch(self):
        session = Path(self.config['load']['session_dir'])
        session.mkdir()
        self.blocked(self.config)
        self.assertTrue(session.is_dir())

    def test_checkpoint_strict_json_base64_binding_and_sizes(self):
        checkpoint = self.root / 'checkpoint.json'
        valid = {'state_base64': base64.b64encode(b'native bytes').decode(),
                 'sha256': digest(b'native bytes'),
                 'core_sha256': self.config['load']['expected_core_sha256'],
                 'game_sha256': self.config['load']['expected_game_sha256']}
        for text in ('{', '{"sha256":0,"sha256":1}', '{"x":NaN}',
                     json.dumps(dict(valid, state_base64='%%%')),
                     json.dumps(dict(valid, sha256='0' * 64)),
                     json.dumps(dict(valid, game_sha256='0' * 64)),
                     json.dumps(dict(valid, state_base64='', sha256=digest(b'')))):
            checkpoint.write_text(text, encoding='utf-8')
            config = copy.deepcopy(self.config)
            config['initial_state_file'] = str(checkpoint)
            with self.subTest(text=text):
                self.blocked(config)
        checkpoint.write_bytes(b' ' * (12 * 1024 * 1024 + 1))
        self.config['initial_state_file'] = str(checkpoint)
        self.blocked(self.config)


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('gcc'),
                     'compiled native acceptance requires Linux Python and gcc')
class CompiledCaptureTests(RuntimeFixture):
    @classmethod
    def setUpClass(cls):
        cls.core_temp = tempfile.TemporaryDirectory(prefix='capture mock core ')
        cls.addClassCleanup(cls.core_temp.cleanup)
        cls.core = Path(cls.core_temp.name) / 'mock.so'
        cls.hang_core = Path(cls.core_temp.name) / 'hang.so'
        source = Path(__file__).with_name('mock_libretro.c')
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-DROMANCER_V35_TEST',
                        str(source), '-o', str(cls.core)], check=True, capture_output=True)
        subprocess.run(['gcc', '-shared', '-fPIC', '-O2',
                        str(source.with_name('mock_worker_hang.c')), '-o', str(cls.hang_core)],
                       check=True, capture_output=True)

    def setUp(self):
        super().setUp()
        self.store = importlib.import_module('romancer.capture_store')
        self.store.init_capture_store(self.project)
        self.clients = []
        self.real_client = self.runtime.RuntimeClient

    def observe_client(self, *args, **kwargs):
        client = self.real_client(*args, **kwargs)
        self.clients.append(client)
        return client

    def actual_capture(self, config=None):
        with patch.object(self.runtime, 'RuntimeClient', side_effect=self.observe_client):
            result = self.run_capture(config)
        self.assertTrue(self.clients)
        for client in self.clients:
            self.assertIsNotNone(client.process.poll())
        return result

    def assert_no_captures(self):
        with closing(sqlite3.connect(self.project / '.romancer-evidence/captures.sqlite3')) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM captures').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM blobs').fetchone()[0], 0)

    def fault_client(self, transform):
        def launch(*args, **kwargs):
            client = self.observe_client(*args, **kwargs)
            original = client.request
            def request(operation, **parameters):
                self.assertGreater(client.timeout, 0)
                result = original(operation, **parameters)
                return transform(client, operation, result)
            client.request = request
            return client
        return launch

    def test_boolean_protocol_version_is_not_a_valid_handshake(self):
        def change(client, operation, result):
            if operation == 'hello': result['protocol_version'] = True
            return result
        with patch.object(self.runtime, 'RuntimeClient', side_effect=self.fault_client(change)):
            result = self.run_capture()
        self.assertFalse(result['ok'], result)
        self.assert_no_captures()

    def test_session_redirect_after_close_cannot_publish(self):
        session = Path(self.config['load']['session_dir'])
        redirected = self.root / 'redirected output'
        redirected.mkdir()
        def change(client, operation, result):
            if operation == 'close':
                session.rename(self.root / 'retained original session')
                session.symlink_to(redirected, target_is_directory=True)
            return result
        with patch.object(self.runtime, 'RuntimeClient', side_effect=self.fault_client(change)):
            result = self.run_capture()
        self.assertFalse(result['ok'], result)
        self.assert_no_captures()
        self.assertEqual(list(redirected.iterdir()), [])

    def test_close_negative_missing_error_and_nonzero_exit_block_publication(self):
        for mode in ('negative', 'missing', 'transport', 'nonzero'):
            self.config['load']['session_dir'] = str(self.root / mode)
            def change(client, operation, result):
                if operation == 'close':
                    if mode == 'negative':
                        return {'ok': False, 'closed': False}
                    if mode == 'missing':
                        return {'ok': True}
                    if mode == 'transport':
                        raise OSError('close acknowledgement lost')
                    client.process.wait = lambda **kwargs: 7
                return result
            with self.subTest(mode=mode), patch.object(self.runtime, 'RuntimeClient',
                                                       side_effect=self.fault_client(change)):
                result = self.run_capture()
            self.assertFalse(result['ok'], result)
            self.assertFalse(result['written'])
            # Restore Popen.wait before explicit verification/fixture cleanup.
            if mode == 'nonzero':
                del self.clients[-1].process.wait
                self.clients[-1].process.wait(timeout=5)
            self.assertIsNotNone(self.clients[-1].process.poll())
            self.assert_no_captures()

    def test_corrupt_frame_and_binding_responses_never_publish(self):
        for mode in ('base64', 'dimensions', 'length', 'hash', 'index', 'core', 'ancestry', 'coverage'):
            self.config['load']['session_dir'] = str(self.root / mode)
            def change(client, operation, result):
                if operation == 'capture':
                    if mode == 'base64': result['rgb24_base64'] = '!'
                    if mode == 'dimensions': result['width'] = True
                    if mode == 'length': result['rgb24_base64'] = base64.b64encode(b'x').decode()
                    if mode == 'hash': result['sha256'] = '0' * 64
                    if mode == 'index': result['index'] += 1
                    if mode == 'core': result['core_sha256'] = '0' * 64
                    if mode == 'ancestry': result['provenance']['state_derived'] = None
                    if mode == 'coverage': del result['dependency_coverage']
                return result
            with self.subTest(mode=mode), patch.object(self.runtime, 'RuntimeClient',
                                                       side_effect=self.fault_client(change)):
                result = self.run_capture()
            self.assertFalse(result['ok'], result)
            self.assertFalse(result['written'])
            self.assertIsNotNone(self.clients[-1].process.poll())
            self.assert_no_captures()

    def test_source_change_after_native_run_blocks_publication(self):
        check = history.check_build
        count = 0
        def changing(*args):
            nonlocal count
            count += 1
            if count == 2:
                self.source.write_bytes(b'changed during native execution')
            return check(*args)
        with patch.object(history, 'check_build', side_effect=changing):
            result = self.actual_capture()
        self.assertFalse(result['ok'], result)
        self.assertEqual(count, 2)
        self.assert_no_captures()

    def test_expiry_after_startup_between_steps_and_before_close(self):
        for phase in ('startup', 'audio', 'capture'):
            self.config['load']['session_dir'] = str(self.root / phase)
            self.config['steps'] = [{'frames': 1, 'buttons': [], 'port': 0}] * 2
            clock = [time.monotonic()]
            requests = []
            def change(client, operation, result):
                requests.append(operation)
                if operation == phase:
                    clock[0] += 20
                return result
            make = self.fault_client(change)
            def launch(*args, **kwargs):
                client = make(*args, **kwargs)
                if phase == 'startup':
                    clock[0] += 20
                return client
            with self.subTest(phase=phase), patch.object(self.runtime, 'time',
                    SimpleNamespace(monotonic=lambda: clock[0])), patch.object(
                    self.runtime, 'RuntimeClient', side_effect=launch):
                result = self.run_capture()
            self.assertFalse(result['ok'], result)
            self.assertIn('deadline', result['error'])
            if phase == 'startup': self.assertNotIn('load', requests)
            if phase == 'audio': self.assertEqual(requests.count('advance'), 1)
            self.assertIsNotNone(self.clients[-1].process.poll())
            self.assert_no_captures()

    def test_expiry_after_postcheck_or_encoding_never_publishes(self):
        for phase in ('postcheck', 'encoding'):
            self.config['load']['session_dir'] = str(self.root / phase)
            clock = [time.monotonic()]
            check, writer = history.check_build, self.runtime.write_rgb_png
            count = 0
            def checking(*args):
                nonlocal count
                count += 1
                result = check(*args)
                if count == 2 and phase == 'postcheck': clock[0] += 20
                return result
            def writing(*args):
                result = writer(*args)
                if phase == 'encoding': clock[0] += 20
                return result
            with self.subTest(phase=phase), patch.object(self.runtime, 'time',
                    SimpleNamespace(monotonic=lambda: clock[0])), patch.object(history,
                    'check_build', side_effect=checking), patch.object(self.runtime,
                    'write_rgb_png', side_effect=writing):
                result = self.actual_capture()
            self.assertFalse(result['ok'], result)
            self.assertIn('deadline', result['error'])
            self.assert_no_captures()

    def test_real_native_capture_storage_and_input_difference(self):
        first = self.actual_capture()
        self.assertTrue(first['ok'], first)
        stored = self.store.get_capture(self.project, first['capture_id'])
        record = stored['record']
        self.assertEqual(record['origin'], 'native_worker')
        self.assertEqual(record['build']['association'], 'measured_run_output')
        self.assertEqual(record['run']['run_mode'], 'cold_boot')
        self.assertEqual(record['run']['game_sha256'], digest(self.game.read_bytes()))
        self.assertFalse(record['natural_progress_verified'])
        self.assertEqual(stored['image_integrity'], 'PASS')
        self.config['load']['session_dir'] = str(self.root / 'neutral session')
        self.config['steps'][0]['buttons'] = []
        second = self.actual_capture()
        self.assertTrue(second['ok'], second)
        neutral = self.store.get_capture(self.project, second['capture_id'])
        self.assertNotEqual(record['image']['rgb_sha256'], neutral['record']['image']['rgb_sha256'])
        from PIL import Image
        with Image.open(io.BytesIO(stored['png_bytes'])) as image:
            rgb = image.convert('RGB').tobytes()
        self.assertTrue(any(rgb))
        self.assertEqual(digest(rgb), record['image']['rgb_sha256'])
        self.assertEqual(digest(rgb), record['run']['frame']['sha256'])
        self.assertEqual(self.game.read_bytes(), b'synthetic game')

    def test_documented_config_executes_real_native_capture(self):
        config = self.documented_config()
        result = self.actual_capture(config)
        self.assertTrue(result['ok'], result)
        record = self.store.get_capture(self.project, result['capture_id'])['record']
        self.assertEqual(record['origin'], 'native_worker')
        self.assertEqual(record['run']['frame']['index'], 60)
        self.assertEqual(record['run']['run_mode'], 'cold_boot')
        self.assertIsNone(record['run']['initial_game_save_sha256'])

    def test_native_png_import_copy_and_search_keep_distinct_origins(self):
        ingest = importlib.import_module('romancer.capture_ingest')
        result = self.actual_capture()
        self.assertTrue(result['ok'], result)
        native = self.store.get_capture(self.project, result['capture_id'])
        image = self.root / 'synthetic native copy.png'
        image.write_bytes(native['png_bytes'])
        context = {'captured_utc': None, 'game_sha256': digest(self.game.read_bytes()),
                   'core_sha256': digest(self.core.read_bytes()), 'run_mode': 'cold_boot',
                   'state_derived': False, 'source_note': 'supplied context, not a worker reply'}
        entry = {'kind': 'text', 'text': 'The gate opens', 'method': 'manual',
                 'author': 'synthetic test', 'locator': None, 'region': None,
                 'resource': None, 'supersedes': None}
        ingest.add_annotations(self.project, result['capture_id'], [entry])
        imported = ingest.import_capture(self.project, image, {
            'build_id': self.build['build_id'], 'declared_context': context,
            'annotations': [entry]}, self.root)
        copy_record = self.store.get_capture(self.project, imported['capture_id'])
        self.assertEqual(copy_record['png_bytes'], native['png_bytes'])
        self.assertEqual(copy_record['record']['image']['rgb_sha256'], native['record']['image']['rgb_sha256'])
        self.assertEqual(copy_record['record']['origin'], 'imported_image')
        self.assertIsNone(copy_record['record']['run'])
        query = {'text': 'gate', 'build_id': self.build['build_id'],
                 'origin': 'native_worker', 'run_mode': 'cold_boot', 'limit': 10}
        matches = self.store.search_captures(self.project, query)['matches']
        self.assertEqual([item['capture_id'] for item in matches], [result['capture_id']])
        self.assertFalse(matches[0]['natural_progress_verified'])
        self.assertEqual(matches[0]['image_integrity'], 'NOT_CHECKED')
        self.assertEqual(matches[0]['build_currentness'], 'NOT_CHECKED')
        query.pop('run_mode')
        query['origin'] = 'imported_image'
        matches = self.store.search_captures(self.project, query)['matches']
        self.assertEqual([item['capture_id'] for item in matches], [imported['capture_id']])
        self.assertEqual(matches[0]['association'], 'imported_claim')

    def test_oversized_native_metadata_preserves_previous_capture(self):
        first = self.actual_capture()
        self.assertTrue(first['ok'], first)
        previous = self.store.get_capture(self.project, first['capture_id'])
        database = self.project / '.romancer-evidence/captures.sqlite3'
        before = database.read_bytes()
        self.config['load']['session_dir'] = str(self.root / 'overflow session')
        def change(client, operation, result):
            if operation == 'load':
                result['loaded']['core_options'] = {'large': 'x' * (64 * 1024)}
            return result
        with patch.object(self.runtime, 'RuntimeClient', side_effect=self.fault_client(change)):
            result = self.run_capture()
        self.assertFalse(result['ok'], result)
        self.assertFalse(result['written'])
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(self.store.get_capture(self.project, first['capture_id'])['png_bytes'], previous['png_bytes'])

    def test_cleanup_failure_does_not_replace_primary_refusal(self):
        def launch(*args, **kwargs):
            client = self.observe_client(*args, **kwargs)
            original_request, original_close = client.request, client.close
            def request(operation, **parameters):
                if operation == 'capture':
                    raise ValueError('primary capture refusal')
                return original_request(operation, **parameters)
            def close():
                original_close()
                raise OSError('secondary cleanup issue')
            client.request, client.close = request, close
            return client
        with patch.object(self.runtime, 'RuntimeClient', side_effect=launch):
            result = self.run_capture()
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'primary capture refusal')
        self.assertEqual(result['cleanup_error'], 'OSError')
        self.assertIsNotNone(self.clients[-1].process.poll())
        self.assert_no_captures()

    def test_cleanup_exception_before_reaping_still_reaps_owned_child(self):
        real_closes = []
        def launch(*args, **kwargs):
            client = self.observe_client(*args, **kwargs)
            real_closes.append(client.close)
            request = client.request
            def refusing(operation, **parameters):
                if operation == 'capture': raise ValueError('primary capture refusal')
                return request(operation, **parameters)
            client.request = refusing
            client.close = lambda: (_ for _ in ()).throw(OSError('cleanup before abort failed'))
            return client
        try:
            with patch.object(self.runtime, 'RuntimeClient', side_effect=launch):
                result = self.run_capture()
            self.assertFalse(result['ok'])
            self.assertEqual(result['error'], 'primary capture refusal')
            self.assertIsNotNone(self.clients[-1].process.poll(), 'owned worker remains alive')
            self.assert_no_captures()
        finally:
            for close in real_closes:
                close()

    def checkpoint(self, derived=False):
        load = dict(self.config['load'], session_dir=str(self.root / 'checkpoint source session'))
        with RuntimeClient([sys.executable, '-m', 'romancer.runtime_worker']) as client:
            self.assertTrue(client.request('load', **load)['ok'])
            state = client.request('save_state')
            self.assertTrue(state['ok'])
            if derived:
                self.assertTrue(client.request('load_state', snapshot=state)['ok'])
            save = client.request('save_game')
            self.assertTrue(save['ok'])
        return state, save

    def test_real_imported_state_capture_retains_ancestry(self):
        state, _ = self.checkpoint()
        path = self.root / 'state.json'
        path.write_text(json.dumps(state), encoding='utf-8')
        self.config['initial_state_file'] = str(path)
        result = self.actual_capture()
        self.assertTrue(result['ok'], result)
        run = self.store.get_capture(self.project, result['capture_id'])['record']['run']
        self.assertEqual(run['run_mode'], 'imported_save_state')
        self.assertIs(run['provenance']['state_derived'], True)
        self.assertEqual(run['provenance']['ancestor_state_sha256'], state['sha256'])
        self.assertNotIn('state_base64', json.dumps(run))

    def test_real_state_derived_sram_continuation_retains_ancestry(self):
        state, save = self.checkpoint(derived=True)
        self.config['load']['game_save'] = save
        result = self.actual_capture()
        self.assertTrue(result['ok'], result)
        run = self.store.get_capture(self.project, result['capture_id'])['record']['run']
        self.assertEqual(run['run_mode'], 'game_save_continuation')
        self.assertIs(run['provenance']['state_derived'], True)
        self.assertEqual(run['provenance']['ancestor_state_sha256'], state['sha256'])
        self.assertNotIn('save_ram_base64', json.dumps(run))

    def test_game_save_then_state_import_records_both_checkpoints(self):
        state, save = self.checkpoint()
        path = self.root / 'state.json'
        path.write_text(json.dumps(state), encoding='utf-8')
        self.config['initial_state_file'] = str(path)
        self.config['load']['game_save'] = save
        operations = []
        def observe(client, operation, result):
            operations.append(operation)
            return result
        with patch.object(self.runtime, 'RuntimeClient', side_effect=self.fault_client(observe)):
            result = self.run_capture()
        self.assertTrue(result['ok'], result)
        self.assertIsNotNone(self.clients[-1].process.poll())
        self.assertLess(operations.index('load'), operations.index('load_state'))
        self.assertLess(operations.index('load_state'), operations.index('advance'))
        run = self.store.get_capture(self.project, result['capture_id'])['record']['run']
        self.assertEqual(run['run_mode'], 'imported_save_state')
        self.assertEqual(run['initial_state_sha256'], state['sha256'])
        self.assertEqual(run['initial_game_save_sha256'], save['sha256'])
        self.assertIs(run['provenance']['state_derived'], True)

    def test_unknown_game_save_ancestry_remains_unknown(self):
        _, save = self.checkpoint()
        save.pop('provenance')
        self.config['load']['game_save'] = save
        result = self.actual_capture()
        self.assertTrue(result['ok'], result)
        run = self.store.get_capture(self.project, result['capture_id'])['record']['run']
        self.assertIsNone(run['provenance']['state_derived'])
        self.assertEqual(run['provenance']['trust'], 'supplied_checkpoint_metadata')

    def test_real_wrong_core_hash_does_not_publish(self):
        self.config['load']['expected_core_sha256'] = '0' * 64
        result = self.actual_capture()
        self.assertFalse(result['ok'])
        self.assertFalse(result['written'])
        self.assertIn('SHA-256', result['error'])
        self.assert_no_captures()

    def test_real_native_hang_reaps_child_without_publication(self):
        self.config['load']['core'] = str(self.hang_core)
        self.config['load']['expected_core_sha256'] = digest(self.hang_core.read_bytes())
        self.config['timeout'] = 1
        started = time.monotonic()
        result = self.actual_capture()
        self.assertLess(time.monotonic() - started, 12)
        self.assertFalse(result['ok'])
        self.assertFalse(result['written'])
        self.assert_no_captures()


if __name__ == '__main__':
    unittest.main()
