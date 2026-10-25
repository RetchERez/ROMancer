"""One bounded native-worker capture; no imported reply can select this origin.

The execution/publication deadline excludes preflight and retains the client's
separately bounded startup/cleanup overhead. Expiry always blocks publication.
"""
import base64
import datetime
import hashlib
import math
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys
import tempfile
import time
import uuid

from . import ROMANCER_VERSION, history, runtime_protocol
from .cd_patch import check_output_paths
from .libretro_frontend import BUTTON_IDS, write_rgb_png
from .runtime_client import RuntimeClient

CONFIG_LIMIT = 1024 * 1024
CHECKPOINT_LIMIT = 12 * 1024 * 1024
PAYLOAD_LIMIT = 8 * 1024 * 1024
RGB_LIMIT = 8 * 1024 * 1024
PNG_LIMIT = 16 * 1024 * 1024
RECORD_LIMIT = 64 * 1024
READ_CHUNK = 64 * 1024
MAX_STEPS = 100
MAX_FRAMES = 6000
FRAME_FIELDS = ('index', 'width', 'height', 'pitch', 'pixel_format', 'sha256')
PROVENANCE_FIELDS = {'origin', 'state_derived', 'ancestor_state_sha256',
                     'parent_checkpoint_sha256', 'trust'}


def _fields(value, required, optional=()):
    if type(value) is not dict or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError('missing or unexpected fields')


def _text(value, limit=4096):
    if type(value) is not str or not value.strip() or len(value) > limit or '\0' in value:
        raise ValueError('expected a bounded nonblank string')
    return value


def _hash(value, length=64):
    if type(value) is not str or re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is None:
        raise ValueError('invalid digest or identifier')
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside allowed bounds')
    return value


def _path(value, base, *, kind='file'):
    text = _text(value)
    windows = PureWindowsPath(text)
    if windows.drive and not windows.root:
        raise ValueError('drive-relative path is ambiguous')
    if ntpath.isreserved(text) or any(part in ('.', '..') for part in text.replace('\\', '/').split('/')):
        raise ValueError('reserved or ambiguous path')
    path = Path(text)
    path = (base / path).absolute() if not path.is_absolute() else path.absolute()
    for candidate in (path, *path.parents):
        if candidate.exists() or candidate.is_symlink():
            info = candidate.lstat()
            if (candidate.is_symlink() or candidate.is_junction()
                    or getattr(info, 'st_file_attributes', 0) & 0x400):
                raise ValueError('linked or reparse paths are not allowed')
    if kind == 'new':
        if path.exists():
            raise ValueError('session directory must be new')
    else:
        info = path.stat()
        if kind == 'file' and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            raise ValueError('input must be an ordinary single-link file')
        if kind == 'directory' and not stat.S_ISDIR(info.st_mode):
            raise ValueError('expected an ordinary directory')
    return path


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def _read_stable(path, limit):
    selected = path.lstat()
    if not stat.S_ISREG(selected.st_mode) or selected.st_nlink != 1 or selected.st_size > limit:
        raise ValueError('source is nonregular, linked, or exceeds byte budget')
    data = bytearray()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if _identity(opened) != _identity(selected):
            raise ValueError('source changed before read')
        while chunk := stream.read(min(READ_CHUNK, limit - len(data) + 1)):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('source exceeds actual read budget')
        held_after, path_after = os.fstat(stream.fileno()), path.lstat()
        # Windows path-stat and handle-stat can expose different ctime meanings.
        # Compare ctime only within each API, retaining both change detectors.
        if (_identity(opened) != _identity(held_after)
                or _identity(opened) != _identity(path_after)
                or opened.st_ctime_ns != held_after.st_ctime_ns
                or selected.st_ctime_ns != path_after.st_ctime_ns):
            raise ValueError('source changed during read')
    return bytes(data)


def _decode(value, limit, *, nonempty=True):
    if type(value) is not str or len(value) > 4 * ((limit + 2) // 3):
        raise ValueError('encoded payload exceeds budget or has wrong type')
    decoded = base64.b64decode(value, validate=True)
    if len(decoded) > limit or (nonempty and not decoded):
        raise ValueError('decoded payload is empty or exceeds budget')
    return decoded


def _checkpoint(value, field, load):
    if type(value) is not dict:
        raise ValueError('checkpoint must be a JSON object')
    payload = _decode(value.get(field), PAYLOAD_LIMIT)
    if hashlib.sha256(payload).hexdigest() != _hash(value.get('sha256')):
        raise ValueError('checkpoint payload digest mismatch')
    for key in ('core', 'game'):
        if _hash(value.get(key + '_sha256')) != load['expected_' + key + '_sha256']:
            raise ValueError('checkpoint identity mismatch')
    if 'provenance' in value:
        _provenance(value['provenance'])
    return value


def _provenance(value):
    _fields(value, PROVENANCE_FIELDS)
    if value['state_derived'] is not None and type(value['state_derived']) is not bool:
        raise ValueError('invalid state ancestry flag')
    for key in ('ancestor_state_sha256', 'parent_checkpoint_sha256'):
        if value[key] is not None:
            _hash(value[key])
    if value['ancestor_state_sha256'] is not None and value['state_derived'] is not True:
        raise ValueError('state ancestry was lost')
    if value['origin'] not in ('cold_boot', 'imported_save_state', 'game_save_continuation'):
        raise ValueError('unknown run origin')
    if value['trust'] not in ('current_worker', 'supplied_checkpoint_metadata'):
        raise ValueError('unknown provenance trust')


def _envelope(operation, parameters, timeout):
    # Conservative ID/timeout width includes the full authenticated envelope.
    return runtime_protocol.encode({'protocol_version': runtime_protocol.VERSION,
        'id': 999999, 'token': '0' * 64, 'operation': operation,
        'timeout': 1.2345678901234567e-100, 'parameters': parameters}, runtime_protocol.REQUEST_LIMIT)


def _json_structure(value):
    nodes = 0

    def visit(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 32 or nodes > 10000:
            raise ValueError('JSON depth/node budget exceeded')
        if type(item) is dict:
            for key, child in item.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)

    visit(value)


def _preflight(config, base):
    _json_structure(config)
    config = history.strict_json_loads(history.canonical_json(config, max_bytes=CONFIG_LIMIT),
                                     max_bytes=CONFIG_LIMIT)
    _fields(config, {'load', 'steps', 'initial_state_file', 'timeout'})
    timeout = config['timeout']
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError('timeout must be finite and positive, at most 120 seconds')
    base = _path(str(base), Path.cwd(), kind='directory')
    load = config['load']
    _fields(load, {'core', 'game', 'expected_core_sha256', 'expected_game_sha256', 'session_dir'},
            {'system_dir', 'core_options', 'game_dependencies', 'game_save'})
    for key in ('expected_core_sha256', 'expected_game_sha256'):
        _hash(load[key])
    for key in ('core', 'game'):
        load[key] = str(_path(load[key], base))
    session = _path(load['session_dir'], base, kind='new')
    load['session_dir'] = str(session)
    if load.get('system_dir') is not None:
        system = _path(load['system_dir'], base, kind='directory')
        if system == session or system in session.parents or session in system.parents:
            raise ValueError('system directory must be separate from session')
        load['system_dir'] = str(system)
    options = load.get('core_options', {})
    if type(options) is not dict or len(options) > 128:
        raise ValueError('invalid core options')
    for key, value in options.items():
        _text(key, 256)
        if type(value) is not str or len(value) > 1024 or '\0' in value:
            raise ValueError('core option values must be bounded strings')
    dependencies = load.get('game_dependencies', [])
    if type(dependencies) is not list or len(dependencies) > 512:
        raise ValueError('invalid explicit dependency list')
    names = {Path(load['game']).name.casefold()}
    sources = [Path(load['core']), Path(load['game'])]
    destinations = [session / 'content' / Path(load['game']).name]
    for item in dependencies:
        _fields(item, {'source', 'relative', 'expected_sha256'})
        relative = _text(item['relative'])
        if ('\\' in relative or ':' in relative or relative.startswith('/')
                or ntpath.isreserved(relative)
                or any(part in ('', '.', '..') for part in relative.split('/'))
                or relative.casefold() in names):
            raise ValueError('unsafe or duplicate dependency path')
        names.add(relative.casefold())
        _hash(item['expected_sha256'])
        source = _path(item['source'], base)
        item['source'] = str(source)
        sources.append(source)
        destinations.append(session / 'content' / relative)
    for index, destination in enumerate(destinations):
        if any(destination in other.parents or other in destination.parents for other in destinations[index + 1:]):
            raise ValueError('conflicting dependency paths')
    for source in sources:
        check_output_paths(source, [session])
    if sources[0].stat().st_size > 256 * 1024 * 1024 or sum(p.stat().st_size for p in sources) > 8 * 1024**3:
        raise ValueError('worker snapshot budget exceeded')
    steps = config['steps']
    if type(steps) is not list or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError('capture requires 1..100 input steps')
    total = 0
    for step in steps:
        _fields(step, {'frames', 'buttons', 'port'})
        total += _integer(step['frames'], 1, 600)
        _integer(step['port'], 0, 3)
        buttons = step['buttons']
        if (type(buttons) is not list or len(buttons) > 16
                or any(type(b) is not str or b.lower().strip() not in BUTTON_IDS for b in buttons)):
            raise ValueError('invalid RetroPad buttons')
    if total > MAX_FRAMES:
        raise ValueError('run exceeds 6000 total frames')
    state = None
    if config['initial_state_file'] is not None:
        path = _path(config['initial_state_file'], base)
        check_output_paths(path, [session])
        value = history.strict_json_loads(_read_stable(path, CHECKPOINT_LIMIT), max_bytes=CHECKPOINT_LIMIT)
        _json_structure(value)
        state = _checkpoint(value, 'state_base64', load)
    save = load.get('game_save')
    if save is not None:
        save = _checkpoint(save, 'save_ram_base64', load)
    _envelope('load', load, timeout)
    if state is not None:
        _envelope('load_state', {'snapshot': state}, timeout)
    for step in steps:
        _envelope('advance', step, timeout)
    return config, state, save


def _expected_provenance(save=None, state=None):
    if state is not None:
        return {'origin': 'imported_save_state', 'state_derived': True,
                'ancestor_state_sha256': state['sha256'], 'parent_checkpoint_sha256': state['sha256'],
                'trust': 'current_worker'}
    if save is not None:
        supplied = save.get('provenance', {})
        ancestor = supplied.get('ancestor_state_sha256')
        return {'origin': 'game_save_continuation',
                'state_derived': True if ancestor else supplied.get('state_derived'),
                'ancestor_state_sha256': ancestor, 'parent_checkpoint_sha256': save['sha256'],
                'trust': 'supplied_checkpoint_metadata'}
    return {'origin': 'cold_boot', 'state_derived': False, 'ancestor_state_sha256': None,
            'parent_checkpoint_sha256': None, 'trust': 'current_worker'}


def _binding(result, load, provenance):
    for key in ('core', 'game'):
        if _hash(result.get(key + '_sha256')) != load['expected_' + key + '_sha256']:
            raise ValueError('worker identity binding mismatch')
    _provenance(result.get('provenance'))
    if (result.get('provenance') != provenance or result.get('run_mode') != provenance['origin']
            or result.get('dependency_coverage') != 'supplied_paths_only'
            or result.get('natural_progress_verified') is not False):
        raise ValueError('worker run/provenance binding mismatch')


def _frame(value, index):
    _fields(value, FRAME_FIELDS)
    if _integer(value['index'], 1, MAX_FRAMES) != index:
        raise ValueError('stale or inconsistent frame index')
    width = _integer(value['width'], 1, 4096)
    height = _integer(value['height'], 1, 4096)
    if width * height * 3 > RGB_LIMIT:
        raise ValueError('frame RGB exceeds budget')
    if value['pixel_format'] not in ('RGB565', 'XRGB8888', '0RGB1555'):
        raise ValueError('unsupported software pixel format')
    _integer(value['pitch'], width * (4 if value['pixel_format'] == 'XRGB8888' else 2), 1024 * 1024)
    _hash(value['sha256'])
    return dict(value)


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('capture execution/publication deadline expired')
    return min(remaining, 120.0)


def _request(client, deadline, operation, **parameters):
    client.timeout = _remaining(deadline)
    result = client.request(operation, **parameters)
    _remaining(deadline)
    if type(result) is not dict or result.get('ok') is not True:
        reason = result.get('error') if type(result) is dict else None
        detail = ': ' + reason[:512] if type(reason) is str else ''
        raise ValueError(f'worker {operation} failed or returned an invalid acknowledgement{detail}')
    return result


def _build_check(project, build_id):
    result = history.check_build(project, build_id)
    if (result.get('ok') is not True or result.get('status') != 'PASS'
            or result.get('build_id') != build_id or result.get('scope') != 'artifact_identity'
            or result.get('origin') != 'measured' or result.get('check_kind') != 'artifact_identity'):
        raise ValueError('registered build identity check did not pass')
    _hash(result.get('evidence_id'), 32)
    return result['evidence_id']


def capture_run(project: Path, build_id: str, config: dict, base: Path, *, cancelled=None) -> dict:
    """Record one frame from an owned worker, never from caller-supplied replies."""
    client = None
    session = None
    cleanup_error = None
    try:
        config, state, save = _preflight(config, base)
        load = config['load']
        session = Path(load['session_dir'])
        project = _path(str(project), Path.cwd(), kind='directory')
        for store in (project / '.romancer-history', project / '.romancer-evidence'):
            if session == store or session in store.parents or store in session.parents:
                raise ValueError('session must not overlap history or evidence stores')
        _hash(build_id)
        build = history.get_build(project, build_id)
        if (build.get('build_id') != build_id
                or hashlib.sha256(history.canonical_json(build['identity']).encode()).hexdigest() != build_id
                or build['identity']['output']['sha256'] != load['expected_game_sha256']):
            raise ValueError('selected game does not match registered build identity')
        before = _build_check(project, build_id)
        deadline = time.monotonic() + config['timeout']
        primary = None
        try:
            client = RuntimeClient([sys.executable, '-m', 'romancer.runtime_worker'], timeout=config['timeout'],cancelled=cancelled)
            _remaining(deadline)
            hello = _request(client, deadline, 'hello')
            if (type(hello.get('protocol_version')) is not int
                    or hello['protocol_version'] != runtime_protocol.VERSION
                    or hello.get('core_loaded') is not False):
                raise ValueError('worker is not a fresh compatible instance')
            worker_version = _text(hello.get('tool_version'), 256)
            loaded = _request(client, deadline, 'load', **load)
            provenance = _expected_provenance(save)
            _binding(loaded, load, provenance)
            details = loaded.get('loaded')
            if type(details) is not dict or details.get('loaded') is not True:
                raise ValueError('native game load was not acknowledged')
            core_info, options, av = details.get('core'), details.get('core_options'), loaded.get('av')
            if any(type(value) is not dict for value in (core_info, options, av)):
                raise ValueError('worker load metadata is absent')
            if state is not None:
                imported = _request(client, deadline, 'load_state', snapshot=state)
                provenance = _expected_provenance(state=state)
                _binding(imported, load, provenance)
            steps, index = [], 0
            for step in config['steps']:
                advanced = _request(client, deadline, 'advance', **step)
                _binding(advanced, load, provenance)
                index += step['frames']
                if type(advanced.get('frame_index')) is not int or advanced['frame_index'] != index:
                    raise ValueError('advance index does not match acknowledged input')
                frame = _frame(advanced.get('frame'), index)
                steps.append(dict(step, frame_index=index))
                # Audio is not indexed, but drain it to avoid retaining an entire run.
                audio = _request(client, deadline, 'audio')
                _binding(audio, load, provenance)
            captured = _request(client, deadline, 'capture')
            _binding(captured, load, provenance)
            current_frame = _frame({key: captured.get(key) for key in FRAME_FIELDS}, index)
            if current_frame != frame:
                raise ValueError('capture differs from last acknowledged frame')
            rgb = _decode(captured.get('rgb24_base64'), RGB_LIMIT)
            if (len(rgb) != frame['width'] * frame['height'] * 3
                    or hashlib.sha256(rgb).hexdigest() != frame['sha256']):
                raise ValueError('captured RGB byte count or digest mismatch')
            closed = _request(client, deadline, 'close')
            if closed.get('closed') is not True:
                raise ValueError('worker close was not explicitly acknowledged')
            exit_code = client.process.wait(timeout=_remaining(deadline))
            if type(exit_code) is not int or exit_code != 0:
                raise ValueError('worker did not exit successfully')
            _remaining(deadline)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            if client is not None:
                client.timeout = config['timeout']
                client.cancelled = None
                try:
                    client.close()
                    if client.process.poll() is None:
                        raise RuntimeError('worker cleanup left a live owned process')
                except Exception as exc:
                    cleanup_error = type(exc).__name__
                    # A failed graceful cleanup must not strand the owned child.
                    # The existing client's abort has its own finite kill/wait bounds.
                    try:
                        client._abort()
                    except Exception as abort_error:
                        cleanup_error += '; abort: ' + type(abort_error).__name__
                    if primary is None:
                        raise
        _remaining(deadline)
        after = _build_check(project, build_id)
        _remaining(deadline)
        _path(str(session), Path.cwd(), kind='directory')
        with tempfile.TemporaryDirectory(prefix='capture-encode-', dir=session) as directory:
            png_path = Path(directory) / 'frame.png'
            write_rgb_png(png_path, frame['width'], frame['height'], rgb)
            png = _read_stable(png_path, PNG_LIMIT)
        _remaining(deadline)
        image_hash = hashlib.sha256(png).hexdigest()
        record = {
            'schema_version': 1, 'canonical_version': 1, 'capture_id': uuid.uuid4().hex,
            'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'tool_version': ROMANCER_VERSION, 'origin': 'native_worker',
            'image': {'blob_sha256': image_hash, 'byte_size': len(png),
                      'width': frame['width'], 'height': frame['height'],
                      'rgb_sha256': frame['sha256'], 'media_type': 'image/png', 'normalization': 'rgb24'},
            'build': {'build_id': build_id, 'identity': build['identity'], 'locations': build['locations'],
                      'association': 'measured_run_output'},
            'run': {'run_id': uuid.uuid4().hex, 'worker_tool_version': worker_version,
                    'core_sha256': load['expected_core_sha256'], 'game_sha256': load['expected_game_sha256'],
                    'core_info': core_info, 'av': av, 'core_options': options,
                    'game_dependencies': [{key: item[key] for key in ('relative', 'expected_sha256')}
                                          for item in load.get('game_dependencies', [])],
                    'frame': frame, 'run_mode': provenance['origin'], 'provenance': provenance,
                    'dependency_coverage': 'supplied_paths_only', 'steps': steps,
                    'initial_state_sha256': state['sha256'] if state is not None else None,
                    'initial_game_save_sha256': save['sha256'] if save is not None else None,
                    'build_checks': {'before': before, 'after': after}},
            'import_source': None, 'natural_progress_verified': False,
        }
        history.canonical_json(record, max_bytes=RECORD_LIMIT)
        from .capture_store import _insert_capture
        _remaining(deadline)
        return _insert_capture(project, record, {image_hash: {'media_type': 'image/png', 'content': png}},
                               publication_deadline=deadline)
    except Exception as exc:
        # Errors may contain native diagnostics. Never return auth or checkpoint data.
        error = str(exc)
        token = getattr(client, '_token', None)
        if type(token) is str and token:
            error = error.replace(token, '[redacted]')
        error = re.sub(r'[A-Za-z0-9+/]{128,}={0,2}', '[payload omitted]', error)[:2048]
        result = {'ok': False, 'status': 'BLOCKED', 'scope': 'capture_ingestion',
                  'error': error, 'error_code': type(exc).__name__, 'written': False}
        if session is not None and session.is_dir():
            result['session_dir'] = str(session)
        if cleanup_error:
            result['cleanup_error'] = cleanup_error
        return result
