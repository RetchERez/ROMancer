"""One trusted libretro core in a bounded, locally controlled worker process."""
import argparse
import base64
import ctypes
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import tempfile
import threading

from . import ROMANCER_VERSION
from .cd_patch import check_output_paths
from .libretro_frontend import LibretroFrontend, LibretroError
from .runtime_protocol import VERSION, REQUEST_LIMIT, RESPONSE_LIMIT, decode, encode

STATE_LIMIT = 8 * 1024 * 1024
SNAPSHOT_LIMIT = 8 * 1024 * 1024 * 1024


def _text(value, label):
    if type(value) is not str or not value or '\x00' in value:
        raise ValueError(f'{label} must be a nonempty string')
    return value


def _hash(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-fA-F]{64}', value):
        raise ValueError('expected a complete SHA-256')
    return value.lower()


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _fingerprint(path):
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('input is not a regular file')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if _identity(before) != _identity(os.fstat(stream.fileno())) or _identity(before) != _identity(path.stat()):
            raise ValueError('input changed while hashing')
    return digest, before


def _publish(path, data):
    if path.exists() or path.is_symlink():
        raise ValueError('session artifact already exists')
    descriptor, name = tempfile.mkstemp(prefix='.capture-', dir=path.parent)
    temporary = Path(name)
    owned = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        try:
            if os.path.samestat(owned, temporary.lstat()):
                temporary.unlink()
        except FileNotFoundError:
            pass


def _snapshot(source, destination, expected_hash, maximum):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.input-', dir=destination.parent)
    temporary = Path(name)
    owned = os.fstat(descriptor)
    digest = hashlib.sha256()
    count = 0
    try:
        with os.fdopen(descriptor, 'wb') as output, source.open('rb') as original:
            before = os.fstat(original.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('snapshot source is not a regular file')
            while data := original.read(min(1048576, maximum - count + 1)):
                count += len(data)
                if count > maximum:
                    raise ValueError('runtime snapshot byte budget exceeded')
                digest.update(data)
                output.write(data)
            output.flush()
            os.fsync(output.fileno())
            if (_identity(before) != _identity(os.fstat(original.fileno()))
                    or _identity(before) != _identity(source.stat()) or digest.hexdigest() != expected_hash):
                raise ValueError('snapshot input changed or differs from the expected hash')
        if _fingerprint(temporary)[0] != expected_hash:
            raise ValueError('snapshot verification failed')
        os.link(temporary, destination)
        return count
    finally:
        try:
            if os.path.samestat(owned, temporary.lstat()):
                temporary.unlink()
        except FileNotFoundError:
            pass


def _payload(snapshot, field):
    if type(snapshot) is not dict:
        raise ValueError('checkpoint must be an object')
    text = snapshot.get(field)
    if type(text) is not str or len(text) > ((STATE_LIMIT + 2) // 3) * 4:
        raise ValueError('checkpoint exceeds 8 MiB or lacks payload')
    data = base64.b64decode(text, validate=True)
    if not data or len(data) > STATE_LIMIT or hashlib.sha256(data).hexdigest() != _hash(snapshot.get('sha256')):
        raise ValueError('checkpoint payload/hash mismatch')
    return data


class Workspace:
    def __init__(self):
        self.frontend = None
        self.session = None
        self.core_hash = None
        self.game_hash = None
        self.run_mode = 'cold_boot'
        self.provenance = {'origin': 'cold_boot', 'state_derived': False,
                           'ancestor_state_sha256': None, 'parent_checkpoint_sha256': None,
                           'trust': 'current_worker'}
        self._checkpoint = 0
        self._memory_sequence = 0
        self._memory_epoch = 0
        self._memory_session_id = None
        self._effective_core_options = {}
        self._system_files = None
        self._content_dependencies = []

    def _check_binding(self, snapshot, *, require_runtime=True):
        if (_hash(snapshot.get('core_sha256')) != self.core_hash
                or _hash(snapshot.get('game_sha256')) != self.game_hash):
            raise ValueError('checkpoint belongs to a different core or game')
        if require_runtime and snapshot.get('runtime_identity_sha256')!=self._runtime_identity():
            raise ValueError('checkpoint uses different or unmeasured runtime settings/dependencies')

    def _runtime_identity(self):
        options=getattr(self.frontend,'_core_option_values',None)
        if type(options) is not dict:options=self._effective_core_options
        value={'core_sha256':self.core_hash,'game_sha256':self.game_hash,'core_options':options,
               'system_files':self._system_files,'game_dependencies':self._content_dependencies}
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()

    def _binding(self):
        return {'core_sha256': self.core_hash, 'game_sha256': self.game_hash,
                'run_mode': self.run_mode, 'dependency_coverage': 'measured_system_files_and_declared_content' if self._system_files is not None else 'supplied_paths_only',
                'runtime_identity_sha256':self._runtime_identity(),
                'provenance': dict(self.provenance), 'natural_progress_verified': False}

    def load(self, parameters):
        if self.frontend is not None or self.session is not None:
            raise ValueError('use a fresh worker for another load attempt')
        allowed = {'core', 'game', 'expected_core_sha256', 'expected_game_sha256',
                   'session_dir', 'system_dir', 'core_options', 'game_save', 'game_dependencies', 'system_files'}
        if set(parameters) - allowed:
            raise ValueError('unknown load parameter')
        core = Path(_text(parameters.get('core'), 'core')).resolve()
        game = Path(_text(parameters.get('game'), 'game')).resolve()
        session = Path(_text(parameters.get('session_dir'), 'session_dir'))
        for source in (core, game):
            check_output_paths(source, [session])
        for parent in [session.parent, *session.parent.parents]:
            if parent.is_symlink() or parent.is_junction():
                raise ValueError('linked session parent is not permitted')
        session = session.resolve()
        options = parameters.get('core_options', {})
        if (type(options) is not dict or len(options) > 128 or any(
                type(k) is not str or type(v) is not str or not k or len(k) > 256 or len(v) > 1024
                or '\x00' in k or '\x00' in v for k, v in options.items())):
            raise ValueError('core_options must contain bounded string keys and values')
        system = None
        if parameters.get('system_dir') is not None:
            system = Path(_text(parameters['system_dir'], 'system_dir')).resolve()
            if not system.is_dir() or system == session or system in session.parents or session in system.parents:
                raise ValueError('system directory must exist separately from the new session')
        if system is not None and 'system_files' not in parameters:
            from .runtime_profiles import measure_system_files
            parameters={**parameters,'system_files':[{k:row[k] for k in ('source','relative','expected_sha256')} for row in measure_system_files(system)]}
        core_hash, core_stat = _fingerprint(core)
        game_hash, game_stat = _fingerprint(game)
        if (core_hash != _hash(parameters.get('expected_core_sha256'))
                or game_hash != _hash(parameters.get('expected_game_sha256'))):
            raise ValueError('core/game SHA-256 does not match; nothing loaded')
        self.core_hash, self.game_hash = core_hash, game_hash
        dependencies = parameters.get('game_dependencies', [])
        if type(dependencies) is not list or len(dependencies) > 512:
            raise ValueError('game_dependencies must be a bounded explicit file list')
        # Several Windows cores still use MAX_PATH APIs. Hash-named owned builds
        # need a short staged basename; content identity remains the measured SHA.
        # Disc manifests keep their names and explicit relative dependencies.
        content_name = ('game' + game.suffix.lower()) if not dependencies and len(game.name)>32 and game.suffix.lower() in ('.nes','.sfc','.smc','.md','.gen','.gb','.gbc','.gba','.rom','.bin') else game.name
        copies = [(core, session / 'native' / core.name, core_hash),
                  (game, session / 'content' / content_name, game_hash)]
        names = {content_name.casefold()}
        for item in dependencies:
            if type(item) is not dict or set(item) != {'source', 'relative', 'expected_sha256'}:
                raise ValueError('invalid dependency entry')
            relative = _text(item['relative'], 'relative')
            if ('\\' in relative or ':' in relative or relative.startswith('/')
                    or any(part in ('', '.', '..') for part in relative.split('/'))
                    or relative.casefold() in names):
                raise ValueError('dependency path must be unique and contained')
            source = Path(_text(item['source'], 'dependency source')).resolve()
            destination = session / 'content' / relative
            check_output_paths(source, [session])
            check_output_paths(source, [destination])
            names.add(relative.casefold())
            copies.append((source, destination, _hash(item['expected_sha256'])))
        self._content_dependencies=sorted([{'relative':item['relative'],'sha256':_hash(item['expected_sha256'])} for item in dependencies],key=lambda item:item['relative'])
        if 'system_files' in parameters:
            files=parameters['system_files'];system=session/'system';names=set();self._system_files=[]
            if type(files) is not list or len(files)>256:raise ValueError('system_files requires a bounded explicit list')
            for item in files:
                if type(item) is not dict or set(item)!={'source','relative','expected_sha256'}:raise ValueError('invalid system dependency entry')
                relative=_text(item['relative'],'system-file name')
                if '\\' in relative or ':' in relative or relative.startswith('/') or any(p in ('','.','..') for p in relative.split('/')) or relative.casefold() in names:raise ValueError('unsafe system dependency name')
                names.add(relative.casefold());source=Path(_text(item['source'],'system-file source'))
                for candidate in (source,*source.parents):
                    if candidate.is_symlink() or candidate.is_junction():raise ValueError('linked system dependency is unsupported')
                source=source.absolute();expected=_hash(item['expected_sha256']);check_output_paths(source,[session])
                copies.append((source,system/relative,expected));self._system_files.append({'relative':relative,'sha256':expected})
            self._system_files.sort(key=lambda item:item['relative'])
        for index, (source, destination, _) in enumerate(copies):
            check_output_paths(source, [destination])
            for _, other, _ in copies[index + 1:]:
                if destination in other.parents or other in destination.parents:
                    raise ValueError('runtime snapshot files have conflicting directory paths')
        total = sum(source.stat().st_size for source, _, _ in copies)
        if total > SNAPSHOT_LIMIT or core_stat.st_size > 256 * 1024 * 1024:
            raise ValueError('runtime inputs exceed snapshot budget')
        parent = session.parent
        while not parent.exists():
            parent = parent.parent
        if shutil.disk_usage(parent).free < total + 64 * 1024 * 1024:
            raise ValueError('insufficient free space for isolated runtime snapshots')
        seed = None
        provenance = None
        if parameters.get('game_save') is not None:
            seed = _payload(parameters['game_save'], 'save_ram_base64')
            self._check_binding(parameters['game_save'],require_runtime=False)
            supplied = parameters['game_save'].get('provenance', {})
            supplied = supplied if type(supplied) is dict else {}
            ancestor = supplied.get('ancestor_state_sha256')
            ancestor = _hash(ancestor) if ancestor is not None else None
            derived = supplied.get('state_derived')
            derived = derived if type(derived) is bool else None
            provenance = {'origin': 'game_save_continuation',
                          'state_derived': True if ancestor else derived,
                          'ancestor_state_sha256': ancestor,
                          'parent_checkpoint_sha256': parameters['game_save']['sha256'],
                          'trust': 'supplied_checkpoint_metadata'}
        session.mkdir(parents=True, exist_ok=False)
        self.session = session
        remaining = SNAPSHOT_LIMIT
        for source, destination, expected_hash in copies:
            remaining -= _snapshot(source, destination, expected_hash, remaining)
        snapshot_core, snapshot_game = copies[0][1], copies[1][1]
        save_dir = session / 'working-save'
        save_dir.mkdir()
        if seed is not None:
            _publish(save_dir / (snapshot_game.stem + '.srm'), seed)
        frontend = LibretroFrontend(snapshot_core, system_dir=system, save_dir=save_dir,
                                    assets_dir=session / 'assets', core_options=options)
        try:
            loaded = frontend.load_game(snapshot_game)
            seed_verification = frontend.verify_save_seed(seed) if seed is not None else None
            av = frontend.av_info()
            normal_save = 'available' if frontend.memory_region('save_ram') else 'unavailable'
        except BaseException as exc:
            self._close_failed_frontend(frontend, exc)
            raise
        if provenance is not None:
            self.run_mode = 'game_save_continuation'
            self.provenance = provenance
        self.frontend = frontend
        self._memory_session_id = secrets.token_hex(16)
        self._effective_core_options = dict(loaded.get('core_options', {}))
        return {'ok': True, 'loaded': loaded, 'av': av, 'save_seed_verification':seed_verification, **self._binding(),
                'capabilities': {'input': 'implemented', 'software_video': 'unobserved',
                                 'audio_capture': 'unobserved', 'save_state': 'unobserved',
                                 'normal_save': normal_save}}

    def handle(self, operation, parameters):
        if operation == 'load':
            return self.load(parameters)
        allowed = {'hello': set(), 'close': set(), 'advance': {'frames', 'buttons', 'port'},
                   'capture': set(), 'audio': set(), 'save_state': set(),
                   'load_state': {'snapshot'}, 'save_game': set(),
                   'read_memory': {'region', 'offset', 'length'}}
        if operation not in allowed or set(parameters) - allowed[operation]:
            raise ValueError('unknown operation or parameters')
        if operation == 'hello':
            return {'ok': True, 'protocol_version': VERSION, 'tool_version': ROMANCER_VERSION,
                    'core_loaded': self.frontend is not None,
                    'memory_read': {'version': 1, 'regions': [0, 1, 2, 3], 'max_bytes': 4096}}
        if operation == 'close':
            self.close()
            return {'ok': True, 'closed': True}
        frontend = self.frontend
        if frontend is None:
            raise ValueError('load a core first')
        if operation == 'read_memory':
            if set(parameters) != {'region', 'offset', 'length'}:
                raise ValueError('read_memory requires exactly region, offset and length')
            region, offset, length = (parameters[key] for key in ('region', 'offset', 'length'))
            if (type(region) is not int or not 0 <= region <= 3
                    or type(offset) is not int or offset < 0
                    or type(length) is not int or not 1 <= length <= 4096):
                raise ValueError('invalid bounded memory read parameters')
            try:
                size = int(frontend.lib.retro_get_memory_size(region))
            except BaseException as exc:
                self._close_failed_frontend(frontend, exc)
                raise
            if not 0 < size <= 256 * 1024 * 1024 or offset > size or length > size - offset:
                raise ValueError('memory region unavailable or read outside its bounds')
            try:
                pointer = frontend.lib.retro_get_memory_data(region)
                pointer = ctypes.cast(pointer, ctypes.c_void_p).value
            except BaseException as exc:
                self._close_failed_frontend(frontend, exc)
                raise
            maximum = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
            if pointer is None or pointer < 4096 or offset > maximum - pointer or length > maximum - pointer - offset:
                raise ValueError('memory pointer unavailable or arithmetic out of bounds')
            try:
                raw = ctypes.string_at(pointer + offset, length)
                second_size = int(frontend.lib.retro_get_memory_size(region))
                second_pointer = ctypes.cast(frontend.lib.retro_get_memory_data(region), ctypes.c_void_p).value
                if second_size != size or second_pointer != pointer:
                    raise ValueError('native memory region changed during observation')
            except BaseException as exc:
                self._close_failed_frontend(frontend, exc)
                raise
            self._memory_sequence += 1
            result = {'ok': True, **self._binding(), 'scope': 'native_memory_observation',
                      'memory_read_version': 1, 'tool_version': ROMANCER_VERSION,
                      'worker_session_id': self._memory_session_id,
                      'sequence': self._memory_sequence, 'epoch': self._memory_epoch,
                      'frame_index': frontend.frame_index, 'core_options': dict(self._effective_core_options),
                      'region': region, 'region_size': size, 'offset': offset, 'length': length,
                      'raw_hex': raw.hex(), 'data_sha256': hashlib.sha256(raw).hexdigest(),
                      'memory_written': False, 'write_event_observed': False, 'atomic_snapshot_verified': False}
            from .script_schema import canonical_bytes
            result['observation_id'] = hashlib.sha256(canonical_bytes(
                {key: value for key, value in result.items() if key != 'ok'}, max_bytes=1024*1024)).hexdigest()
            return result
        if operation == 'advance':
            frames = parameters.get('frames')
            port = parameters.get('port', 0)
            buttons = parameters.get('buttons', [])
            if type(frames) is not int or not 1 <= frames <= 600 or type(port) is not int or not 0 <= port <= 3:
                raise ValueError('frame budget is 1..600 and port is 0..3')
            if type(buttons) is not list or len(buttons) > 16 or any(type(button) is not str for button in buttons):
                raise ValueError('buttons must be a bounded string list')
            frontend.buttons_to_mask(buttons)
            frame = frontend.run_frames(frames, buttons, port=port, release_after=True)
            return {'ok': True, 'frame_index': frontend.frame_index,
                    'frame': frame.summary() if frame is not None else None,
                    'audio': frontend.audio_summary(), **self._binding()}
        if operation == 'capture':
            frame = frontend.last_frame
            if frame is None or frontend.hardware_video_seen:
                raise ValueError('no current software frame; execute a frame first')
            if len(frame.rgb) > 8 * 1024 * 1024:
                raise ValueError('software frame exceeds capture budget')
            return {'ok': True, **frame.summary(), **self._binding(),
                    'rgb24_base64': base64.b64encode(frame.rgb).decode('ascii')}
        if operation == 'audio':
            captured = frontend.drain_audio()
            pcm = captured.pop('pcm_s16le')
            return {'ok': True, **captured, **self._binding(),
                    'sample_rate': frontend.av_info()['timing']['sample_rate'],
                    'observed': bool(pcm), 'complete': not captured['dropped_frames'] and not captured['invalid_batches'],
                    'pcm_s16le_base64': base64.b64encode(pcm).decode('ascii')}
        if operation == 'save_state':
            size = int(frontend.lib.retro_serialize_size())
            if not 0 < size <= STATE_LIMIT:
                raise ValueError('save state unavailable or exceeds 8 MiB')
            state = frontend.serialize()
            return {'ok': True, **self._binding(), 'sha256': hashlib.sha256(state).hexdigest(),
                    'state_base64': base64.b64encode(state).decode('ascii')}
        if operation == 'load_state':
            snapshot = parameters.get('snapshot')
            state = _payload(snapshot, 'state_base64')
            self._check_binding(snapshot)
            try:
                frontend.unserialize(state)
                frontend.last_frame = None
                frontend.drain_audio()
            except BaseException as exc:
                # A rejected native import may already have mutated the core.
                self._close_failed_frontend(frontend, exc)
                raise
            self.run_mode = 'imported_save_state'
            self._memory_epoch += 1
            self.provenance = {'origin': 'imported_save_state', 'state_derived': True,
                               'ancestor_state_sha256': snapshot['sha256'],
                               'parent_checkpoint_sha256': snapshot['sha256'], 'trust': 'current_worker'}
            return {'ok': True, **self._binding()}
        if operation == 'save_game':
            region_size = int(frontend.lib.retro_get_memory_size(0))
            if not 0 < region_size <= STATE_LIMIT:
                raise ValueError('normal save RAM unavailable or exceeds 8 MiB')
            data = frontend.memory_region('save_ram')
            if len(data) != region_size:
                raise ValueError('normal save RAM size changed')
            self._checkpoint += 1
            name = f'game-save-{self._checkpoint:06d}'
            artifact = self.session / (name + '.srm')
            result = {'ok': True, **self._binding(), 'sha256': hashlib.sha256(data).hexdigest(),
                      'save_ram_base64': base64.b64encode(data).decode('ascii'), 'path': str(artifact),
                      'scope': 'exposed_save_ram_snapshot', 'in_game_save_event_verified': False}
            _publish(artifact, data)
            _publish(self.session / (name + '.json'), json.dumps(result, indent=2).encode('utf-8'))
            return result
        raise ValueError('unsupported operation')

    def _close_failed_frontend(self, frontend, error):
        self.frontend = None
        try:
            frontend.close()
        except Exception as cleanup_error:
            error.add_note(f'Frontend cleanup also failed: {cleanup_error}')

    def close(self):
        if self.frontend is not None:
            frontend, self.frontend = self.frontend, None
            frontend.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private ROMancer emulator worker')
    parser.add_argument('--token', required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[0-9a-f]{64}', args.token):
        parser.error('invalid worker token')
    workspace = Workspace()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(10)
        print(json.dumps({'protocol_version': VERSION, 'port': listener.getsockname()[1], 'pid': os.getpid()}), flush=True)
        try:
            connection, _ = listener.accept()
            with connection, connection.makefile('rb') as reader:
                last_id = 0
                while raw := reader.readline(REQUEST_LIMIT + 1):
                    request = decode(raw, REQUEST_LIMIT)
                    if (set(request) != {'protocol_version', 'id', 'token', 'operation', 'timeout', 'parameters'}
                            or type(request['protocol_version']) is not int or request['protocol_version'] != VERSION
                            or type(request['id']) is not int or request['id'] <= last_id
                            or type(request['token']) is not str or not hmac.compare_digest(request['token'], args.token)
                            or type(request['parameters']) is not dict or type(request['operation']) is not str):
                        raise ValueError('invalid or unauthenticated protocol request')
                    timeout = request['timeout']
                    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
                        raise ValueError('invalid operation timeout')
                    last_id = request['id']
                    # Bound native stalls inside the directly launched worker process.
                    watchdog = threading.Timer(timeout + 0.25, os._exit, args=(124,))
                    watchdog.daemon = True
                    watchdog.start()
                    try:
                        try:
                            result = workspace.handle(request['operation'], request['parameters'])
                        except (ValueError, OSError, LibretroError, OverflowError) as exc:
                            result = {'ok': False, 'error': str(exc), 'error_code': type(exc).__name__}
                        response = {'protocol_version': VERSION, 'id': last_id, 'result': result}
                        connection.sendall(encode(response, RESPONSE_LIMIT))
                    finally:
                        watchdog.cancel()
                    if request['operation'] == 'close':
                        break
        except (OSError, ValueError, RecursionError) as exc:
            print(f'Worker stopped: {exc}', file=__import__('sys').stderr, flush=True)
        finally:
            workspace.close()


if __name__ == '__main__':
    main()
