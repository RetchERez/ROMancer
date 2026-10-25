"""Private, content-bound history. Measured evidence proves artifact identity only.

Legacy writers must be stopped during initialization. Filesystem checks protect
ordinary concurrent changes, not hostile path swaps or fabricated owner markers.
"""
from contextlib import contextmanager, closing
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
import uuid

from . import ROMANCER_VERSION

SCHEMA_VERSION = 1
CANONICAL_VERSION = 1
MAX_JSON_BYTES = 64 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_INPUTS = 64
CHUNK_SIZE = 64 * 1024
LOCK_TIMEOUT = 2.0
STORE_NAME = '.romancer-history'
DB_NAME = 'history.sqlite3'
MARKER_NAME = 'owner.json'
LOCK_NAME = 'operation.lock'
SCOPE = 'artifact_identity'
_SCHEMA = {
    'store_meta': 'CREATE TABLE store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
    'builds': 'CREATE TABLE builds (build_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL)',
    'evidence': 'CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, build_id TEXT NOT NULL REFERENCES builds(build_id), record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL)',
    'legacy_metadata': 'CREATE TABLE legacy_metadata (name TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, content BLOB NOT NULL, origin TEXT NOT NULL)',
}


def _json_value(value, depth=0):
    if depth > 64:
        raise ValueError('JSON nesting exceeds 64 levels')
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item, depth + 1)
        return
    raise ValueError('JSON requires string keys, finite numbers, and plain JSON types')


def canonical_json(value, *, max_bytes=MAX_JSON_BYTES):
    """Canonical version 1: sorted keys, compact ASCII JSON, finite numbers."""
    _json_value(value)
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    if len(text.encode('utf-8')) > max_bytes:
        raise ValueError('JSON record exceeds size limit')
    return text


def strict_json_loads(text, *, max_bytes=MAX_JSON_BYTES):
    """Decode bounded UTF-8 JSON without duplicate keys or nonfinite numbers."""
    if type(text) not in (bytes, str):
        raise ValueError('JSON input must be bytes or text')
    if len(text if type(text) is bytes else text.encode('utf-8')) > max_bytes:
        raise ValueError('JSON input exceeds size limit')
    if type(text) is bytes:
        text = text.decode('utf-8')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f'nonfinite JSON number: {value}')
    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except RecursionError as exc:
        raise ValueError('JSON nesting is too deep') from exc
    _json_value(value)
    return value


def _fields(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError(f'expected exactly these fields: {", ".join(fields)}')


def _text(value, label, limit=256):
    if type(value) is not str or not value.strip() or len(value) > limit or '\0' in value:
        raise ValueError(f'{label} must be a nonblank string of at most {limit} characters')
    return value


def _hex_id(value, length=64):
    if type(value) is not str or re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is None:
        raise ValueError('invalid content/evidence identifier')


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _windows_path(path):
    if os.name == 'nt' and (os.path.isreserved(path)
            or str(path).replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\'))):
        raise ValueError('Windows reserved or ambiguous history/artifact path')


def _no_links(path):
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError(f'symlink/junction paths are not allowed here: {candidate}')


def _project(project):
    path = Path(project).absolute()
    _windows_path(path)
    _no_links(path)
    if not path.is_dir():
        raise ValueError('project must be an existing ordinary directory')
    return path.resolve()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _regular(path, *, single=False):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_junction() or (single and info.st_nlink != 1):
        raise ValueError(f'expected an ordinary {"single-link " if single else ""}file: {path}')
    return info


def _read_stable(path, *, limit=None, keep=False):
    before = _regular(path)
    if limit is not None and before.st_size > limit:
        raise ValueError('metadata exceeds 8 MiB limit')
    digest = hashlib.sha256()
    chunks = []
    size = 0
    with path.open('rb') as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise ValueError(f'file changed before hashing: {path}')
        while chunk := stream.read(CHUNK_SIZE):
            size += len(chunk)
            if size > before.st_size or (limit is not None and size > limit):
                raise ValueError(f'file changed during hashing: {path}')
            digest.update(chunk)
            if keep:
                chunks.append(chunk)
        if (size != before.st_size or _identity(os.fstat(stream.fileno())) != _identity(before)
                or _identity(path.lstat()) != _identity(before)):
            raise ValueError(f'file changed during hashing: {path}')
    return {'identity': _identity(before), 'sha256': digest.hexdigest(), 'size': size,
            'content': b''.join(chunks) if keep else None}


def _check_snapshot_identity(path, snapshot):
    if _identity(_regular(path)) != snapshot['identity']:
        raise ValueError(f'file changed after hashing: {path}')


def _capture_metadata(root):
    captures = {}
    for name, kind in (('project.json', dict), ('evidence/evidence.json', list)):
        path = root / name
        _no_links(path)
        if not os.path.lexists(path):
            captures[name] = None
            continue
        capture = _read_stable(path, limit=MAX_METADATA_BYTES, keep=True)
        if type(strict_json_loads(capture['content'], max_bytes=MAX_METADATA_BYTES)) is not kind:
            raise ValueError(f'invalid legacy metadata root type: {name}')
        captures[name] = capture
    return captures


def _recheck_metadata(root, captures):
    for name, captured in captures.items():
        path = root / name
        _no_links(path)
        if captured is None:
            if os.path.lexists(path):
                raise ValueError(f'legacy metadata created during capture: {name}')
        else:
            current = _read_stable(path, limit=MAX_METADATA_BYTES)
            if any(current[key] != captured[key] for key in ('identity', 'sha256', 'size')):
                raise ValueError(f'legacy metadata changed during capture: {name}')


def _marker(store):
    _no_links(store)
    info = store.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('history store must be a directory')
    _regular(store / MARKER_NAME, single=True)
    marker = strict_json_loads(_read_stable(store / MARKER_NAME, limit=MAX_JSON_BYTES, keep=True)['content'])
    _fields(marker, ('schema_version', 'store_id', 'directory_identity'))
    if type(marker['schema_version']) is not int or marker['schema_version'] != SCHEMA_VERSION:
        raise ValueError('unsupported history marker schema')
    _hex_id(marker['store_id'], 32)
    if marker['directory_identity'] != [info.st_dev, info.st_ino]:
        raise ValueError('history directory ownership mismatch')
    return marker


def _footprint(store, *, lock_info=None):
    marker = _marker(store)
    allowed = {MARKER_NAME, DB_NAME, LOCK_NAME}
    if {p.name for p in store.iterdir()} - allowed:
        raise ValueError('unknown or recovery files in history store; explicit recovery required')
    _regular(store / DB_NAME, single=True)
    # A WAL database can create sidecars on opening. Reject it before SQLite.
    with (store / DB_NAME).open('rb') as stream:
        header = stream.read(20)
    if header[:16] != b'SQLite format 3\0' or header[18:20] != b'\x01\x01':
        raise ValueError('history database must be valid SQLite using DELETE journaling')
    lock = store / LOCK_NAME
    if os.path.lexists(lock):
        info = _regular(lock, single=True)
        if lock_info is not None and not os.path.samestat(info, lock_info):
            raise ValueError('history operation lock was replaced')
    elif lock_info is not None:
        raise ValueError('history operation lock disappeared')
    return marker


def _unlink_owned(path, info):
    try:
        if os.path.samestat(path.lstat(), info):
            path.unlink()
    except FileNotFoundError:
        pass


@contextmanager
def _locked(project):
    root = _project(project)
    store = root / STORE_NAME
    # Waiting never removes someone else's lock, including abandoned locks.
    deadline = time.monotonic() + LOCK_TIMEOUT
    lock = store / LOCK_NAME
    while True:
        # An active writer can temporarily have a journal; wait on its lock first.
        _marker(store)
        if os.path.lexists(lock):
            try:
                _regular(lock, single=True)
            except FileNotFoundError:
                continue
            except ValueError:
                # Windows can expose an ordinary delete-pending file with zero
                # links between the existence check and validation. Another
                # writer released it; retry without removing anybody's lock.
                try:
                    current=lock.lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(current.st_mode) or current.st_nlink!=0:
                    raise
            if time.monotonic() >= deadline:
                raise OSError('history operation lock busy or abandoned; explicit recovery may be required')
            time.sleep(0.01)
            continue
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        break
    info = None
    try:
        info = os.fstat(fd)
        stream = os.fdopen(fd, 'wb')
        fd = None  # The stream now owns the descriptor, including on interruption.
        with closing(stream):
            stream.write(uuid.uuid4().hex.encode('ascii'))
            stream.flush()
        marker = _footprint(store, lock_info=info)
        yield store, marker, info
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            if info is not None:
                _unlink_owned(lock, info)


def _connect(path, *, readonly=False):
    uri = path.as_uri() + ('?mode=ro&immutable=1' if readonly else '?mode=rw')
    connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=LOCK_TIMEOUT)
    connection.execute('PRAGMA trusted_schema=OFF')
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def _schema_check(connection, marker):
    if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
        raise ValueError('unsupported history database schema')
    objects = connection.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
    if dict(objects) != _SCHEMA:
        raise ValueError('unexpected history database schema objects')
    expected = {'schema_version': str(SCHEMA_VERSION), 'canonical_version': str(CANONICAL_VERSION),
                'store_id': marker['store_id']}
    if dict(connection.execute('SELECT key, value FROM store_meta')) != expected:
        raise ValueError('history database ownership/schema metadata mismatch')
    if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
        raise ValueError('history database integrity check failed')


@contextmanager
def _database(store, marker, lock_info, *, readonly=False, artifacts=()):
    current = _footprint(store, lock_info=lock_info)
    if current != marker:
        raise ValueError('history owner marker changed')
    _reject_store_artifacts(store, artifacts)
    with closing(_connect(store / DB_NAME, readonly=readonly)) as connection:
        _schema_check(connection, marker)
        yield connection


@contextmanager
def _transaction(connection):
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _initial_footprint(store, marker, owned):
    if _marker(store) != marker or set(store.iterdir()) != set(owned):
        raise ValueError('history initialization footprint changed')
    for path, info in owned.items():
        if not os.path.samestat(_regular(path, single=True), info):
            raise ValueError('history initialization file identity changed')


def init_history(project: Path) -> dict:
    """Create a new owned store and preserve stable, quiescent legacy metadata."""
    root = _project(project)
    store = root / STORE_NAME
    if os.path.lexists(store):
        raise ValueError('history store already exists; refusing replacement or automatic recovery')
    captures = _capture_metadata(root)
    store.mkdir(mode=0o700)
    directory_info = store.stat()
    owned = {}
    marker = {'schema_version': SCHEMA_VERSION, 'store_id': uuid.uuid4().hex,
              'directory_identity': [directory_info.st_dev, directory_info.st_ino]}
    try:
        with (store / MARKER_NAME).open('xb') as stream:
            owned[store / MARKER_NAME] = os.fstat(stream.fileno())
            stream.write(canonical_json(marker).encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        fd, name = tempfile.mkstemp(prefix='.init-', suffix='.sqlite3', dir=store)
        temporary = Path(name)
        owned[temporary] = os.fstat(fd)
        os.close(fd)
        _initial_footprint(store, marker, owned)
        with closing(_connect(temporary)) as connection:
            connection.execute('PRAGMA journal_mode=DELETE')
            with _transaction(connection):
                for sql in _SCHEMA.values():
                    connection.execute(sql)
                connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                connection.executemany('INSERT INTO store_meta VALUES (?, ?)',
                    [('schema_version', str(SCHEMA_VERSION)), ('canonical_version', str(CANONICAL_VERSION)),
                     ('store_id', marker['store_id'])])
                for source_name, capture in captures.items():
                    if capture is not None:
                        connection.execute('INSERT INTO legacy_metadata VALUES (?, ?, ?, ?)',
                            (source_name, capture['sha256'], capture['content'], 'imported_legacy_metadata'))
        verified_snapshot = _read_stable(temporary)
        _initial_footprint(store, marker, owned)
        with closing(_connect(temporary, readonly=True)) as connection:
            _schema_check(connection, marker)
            backups = connection.execute('SELECT name, source_sha256, content, origin FROM legacy_metadata').fetchall()
            expected = [(name, item['sha256'], item['content'], 'imported_legacy_metadata')
                        for name, item in captures.items() if item is not None]
            if sorted(backups) != sorted(expected):
                raise ValueError('legacy metadata backup verification failed')
        _recheck_metadata(root, captures)
        if _read_stable(temporary) != verified_snapshot:
            raise ValueError('temporary history database changed after verification')
        _initial_footprint(store, marker, owned)
        # Recheck identities and absence after the last long database read.
        for source_name, capture in captures.items():
            path = root / source_name
            _no_links(path)
            if capture is None:
                if os.path.lexists(path):
                    raise ValueError(f'legacy metadata created during initialization: {source_name}')
            else:
                _check_snapshot_identity(path, capture)
        os.link(temporary, store / DB_NAME)
        _unlink_owned(temporary, owned[temporary])
        _footprint(store)
        return {'schema_version': SCHEMA_VERSION, 'scope': 'history_metadata', 'ok': True,
                'build_id': None, 'status': 'INITIALIZED', 'database': str(store / DB_NAME),
                'tool_version': ROMANCER_VERSION,
                'imported_metadata': [{'name': name, 'sha256': item['sha256'], 'size': item['size']}
                                      for name, item in captures.items() if item is not None]}
    except BaseException:
        # Unknown/recovery files or a published database are never removed.
        if (os.path.samestat(store.stat(), directory_info)
                and set(store.iterdir()).issubset(owned)):
            for path, info in owned.items():
                _unlink_owned(path, info)
            if not any(store.iterdir()):
                store.rmdir()
        raise


def _config(config):
    canonical_json(config)
    _fields(config, ('inputs', 'output', 'adapter', 'profile', 'settings'))
    inputs = config['inputs']
    if type(inputs) is not list or not 1 <= len(inputs) <= MAX_INPUTS:
        raise ValueError('configuration requires 1 to 64 ordered inputs')
    roles = []
    for item in inputs:
        _fields(item, ('role', 'path'))
        roles.append(_text(item['role'], 'input role', 128))
        _text(item['path'], 'input path', 4096)
    if len(set(roles)) != len(roles):
        raise ValueError('input roles must be distinct')
    _text(config['output'], 'output path', 4096)
    for key in ('adapter', 'profile'):
        _fields(config[key], ('name', 'version'))
        _text(config[key]['name'], key + ' name')
        _text(config[key]['version'], key + ' version')
    if type(config['settings']) is not dict:
        raise ValueError('settings must be an explicit JSON object')


def _locate(path, base):
    candidate = Path(path)
    _windows_path(candidate)
    return (candidate if candidate.is_absolute() else Path(base) / candidate).resolve()


def _reject_store_artifacts(store, paths):
    entries = list(store.iterdir())
    for path in paths:
        _windows_path(path)
        resolved = Path(path).resolve()
        if resolved == store or store in resolved.parents:
            raise ValueError('artifacts cannot be inside the history store')
        for entry in entries:
            try:
                if os.path.samefile(resolved, entry):
                    raise ValueError('artifact aliases a history store file')
            except FileNotFoundError:
                pass


def _content(snapshot):
    return {'sha256': snapshot['sha256'], 'size': snapshot['size']}


def _record_text(record):
    text = canonical_json(record)
    return text, _digest(text)


def _decode_record(text, digest):
    value = strict_json_loads(text)
    if canonical_json(value) != text or _digest(text) != digest:
        raise ValueError('corrupt history record hash or canonical encoding')
    return value


def _load_build(connection, build_id):
    _hex_id(build_id)
    row = connection.execute('SELECT record_json, record_sha256 FROM builds WHERE build_id=?', (build_id,)).fetchone()
    if row is None:
        raise ValueError('build ID not found')
    record = _decode_record(*row)
    _fields(record, ('schema_version', 'build_id', 'identity', 'locations'))
    identity = record['identity']
    _fields(identity, ('schema_version', 'canonical_version', 'tool_version', 'inputs', 'output',
                       'adapter', 'profile', 'settings'))
    if (type(record['schema_version']) is not int or record['schema_version'] != SCHEMA_VERSION
            or type(identity['schema_version']) is not int or identity['schema_version'] != SCHEMA_VERSION
            or type(identity['canonical_version']) is not int or identity['canonical_version'] != CANONICAL_VERSION
            or record['build_id'] != build_id or _digest(canonical_json(identity)) != build_id):
        raise ValueError('corrupt build identity or schema')
    _text(identity['tool_version'], 'tool version')
    _fields(record['locations'], ('inputs', 'output'))
    locations = record['locations']
    if type(identity['inputs']) is not list or type(locations['inputs']) is not list or len(identity['inputs']) != len(locations['inputs']):
        raise ValueError('corrupt input locations')
    config = {'inputs': [], 'output': locations['output'], 'adapter': identity['adapter'],
              'profile': identity['profile'], 'settings': identity['settings']}
    for item, location in zip(identity['inputs'], locations['inputs']):
        _fields(item, ('role', 'sha256', 'size'))
        _fields(location, ('role', 'path'))
        if item['role'] != location['role']:
            raise ValueError('input role/location mismatch')
        config['inputs'].append(location)
    _fields(identity['output'], ('sha256', 'size'))
    for item in [*identity['inputs'], identity['output']]:
        _hex_id(item['sha256'])
        if type(item['size']) is not int or item['size'] < 0:
            raise ValueError('invalid artifact size')
    _config(config)
    for path in _build_paths(record):
        if not path.is_absolute():
            raise ValueError('recorded artifact locations must be absolute')
    return record


def _build_paths(record):
    return [Path(item['path']) for item in record['locations']['inputs']] + [Path(record['locations']['output'])]


def get_build(project: Path, build_id: str) -> dict:
    """Return a detached, validated stored record without checking current artifacts."""
    _hex_id(build_id)
    with _locked(project) as (store, marker, lock_info):
        with _database(store, marker, lock_info, readonly=True) as connection:
            return _load_build(connection, build_id)


def register_build(project: Path, config: dict, base: Path) -> dict:
    """Register declared content/configuration, not proof of production or playability."""
    _config(config)
    # Round-trip detaches the caller's mutable configuration while it is measured.
    config = strict_json_loads(canonical_json(config))
    paths = [_locate(item['path'], base) for item in config['inputs']] + [_locate(config['output'], base)]
    with _locked(project) as (store, marker, lock_info):
        _reject_store_artifacts(store, paths)
        with _database(store, marker, lock_info, readonly=True):
            pass
        snapshots = [_read_stable(path) for path in paths]
        identity = {'schema_version': SCHEMA_VERSION, 'canonical_version': CANONICAL_VERSION,
                    'tool_version': ROMANCER_VERSION,
                    'inputs': [dict(role=item['role'], **_content(snapshot))
                               for item, snapshot in zip(config['inputs'], snapshots)],
                    'output': _content(snapshots[-1]), 'adapter': config['adapter'],
                    'profile': config['profile'], 'settings': config['settings']}
        build_id = _digest(canonical_json(identity))
        record = {'schema_version': SCHEMA_VERSION, 'build_id': build_id, 'identity': identity,
                  'locations': {'inputs': [{'role': item['role'], 'path': str(path)}
                                            for item, path in zip(config['inputs'], paths)],
                                'output': str(paths[-1])}}
        text, digest = _record_text(record)
        for path, snapshot in zip(paths, snapshots):
            if _read_stable(path) != snapshot:
                raise ValueError(f'artifact changed during registration: {path}')
        with _database(store, marker, lock_info, artifacts=paths) as connection:
            # The final long read may outlast changes to an earlier artifact.
            for path, snapshot in zip(paths, snapshots):
                _check_snapshot_identity(path, snapshot)
            with _transaction(connection):
                existing = connection.execute('SELECT 1 FROM builds WHERE build_id=?', (build_id,)).fetchone()
                if existing:
                    record = _load_build(connection, build_id)
                else:
                    connection.execute('INSERT INTO builds VALUES (?, ?, ?)', (build_id, text, digest))
        return {'schema_version': SCHEMA_VERSION, 'scope': SCOPE, 'ok': True,
                'build_id': build_id, 'status': 'REGISTERED', 'tool_version': ROMANCER_VERSION,
                'identity': record['identity'], 'locations': record['locations']}


def _measure(record):
    observations = []
    snapshots = []
    paths = _build_paths(record)
    expected = [*record['identity']['inputs'], record['identity']['output']]
    for index, (path, wanted) in enumerate(zip(paths, expected)):
        item = {'kind': 'input' if index < len(expected) - 1 else 'output',
                'role': wanted.get('role'), 'path': str(path), 'sha256': None, 'size': None,
                'status': 'BLOCKED', 'error': None}
        measured = None
        try:
            measured = _read_stable(path)
        except (ValueError, OSError) as exc:
            item['error'] = str(exc)[:2048]
        else:
            item.update(_content(measured))
            item['status'] = 'PASS' if _content(measured) == _content(wanted) else 'FAIL'
        observations.append(item)
        snapshots.append(measured)
    # No additional content reads: invalidate observations changed during later hashes.
    for path, snapshot, item in zip(paths, snapshots, observations):
        if snapshot is None:
            continue  # An unreadable/unmeasured artifact is already BLOCKED.
        try:
            _check_snapshot_identity(path, snapshot)
        except (ValueError, OSError) as exc:
            item.update({'status': 'BLOCKED', 'sha256': None, 'size': None,
                         'error': str(exc)[:2048]})
    return observations


def _status(statuses):
    return 'BLOCKED' if 'BLOCKED' in statuses else ('FAIL' if 'FAIL' in statuses else 'PASS')


def check_build(project: Path, build_id: str) -> dict:
    """Hash each recorded artifact and persist a measured identity-only result."""
    _hex_id(build_id)
    with _locked(project) as (store, marker, lock_info):
        with _database(store, marker, lock_info, readonly=True) as connection:
            build = _load_build(connection, build_id)
        paths = _build_paths(build)
        _reject_store_artifacts(store, paths)
        observations = _measure(build)
        status = _status([item['status'] for item in observations])
        evidence_id = uuid.uuid4().hex
        record = {'schema_version': SCHEMA_VERSION, 'canonical_version': CANONICAL_VERSION,
                  'scope': SCOPE, 'tool_version': ROMANCER_VERSION, 'build_id': build_id,
                  'evidence_id': evidence_id, 'check_kind': 'artifact_identity', 'origin': 'measured',
                  'status': status, 'observations': observations}
        text, digest = _record_text(record)
        with _database(store, marker, lock_info, artifacts=paths) as connection:
            with _transaction(connection):
                connection.execute('INSERT INTO evidence VALUES (?, ?, ?, ?)',
                                   (evidence_id, build_id, text, digest))
        return dict(record, ok=status == 'PASS')


def _load_evidence(connection, evidence_id):
    _hex_id(evidence_id, 32)
    row = connection.execute('SELECT build_id, record_json, record_sha256 FROM evidence WHERE evidence_id=?',
                             (evidence_id,)).fetchone()
    if row is None:
        return None
    record = _decode_record(row[1], row[2])
    _fields(record, ('schema_version', 'canonical_version', 'scope', 'tool_version', 'build_id',
                     'evidence_id', 'check_kind', 'origin', 'status', 'observations'))
    if (type(record['schema_version']) is not int or record['schema_version'] != SCHEMA_VERSION
            or type(record['canonical_version']) is not int or record['canonical_version'] != CANONICAL_VERSION
            or record['scope'] != SCOPE or record['check_kind'] != 'artifact_identity'
            or record['origin'] != 'measured' or record['evidence_id'] != evidence_id
            or record['build_id'] != row[0] or record['status'] not in ('PASS', 'FAIL', 'BLOCKED')):
        raise ValueError('corrupt or unsupported evidence record')
    _text(record['tool_version'], 'tool version')
    build = _load_build(connection, record['build_id'])
    wanted = [*build['identity']['inputs'], build['identity']['output']]
    observations = record['observations']
    if type(observations) is not list or len(observations) != len(wanted):
        raise ValueError('corrupt evidence observations')
    for index, (item, expected, path) in enumerate(zip(observations, wanted, _build_paths(build))):
        _fields(item, ('kind', 'role', 'path', 'sha256', 'size', 'status', 'error'))
        if (item['kind'] != ('input' if index < len(wanted) - 1 else 'output')
                or item['role'] != expected.get('role') or item['path'] != str(path)):
            raise ValueError('evidence artifact binding mismatch')
        if item['status'] == 'BLOCKED':
            if item['sha256'] is not None or item['size'] is not None:
                raise ValueError('blocked evidence cannot assert observed content')
            _text(item['error'], 'blocked reason', 2048)
        else:
            _hex_id(item['sha256'])
            if type(item['size']) is not int or item['size'] < 0 or item['error'] is not None:
                raise ValueError('invalid observed artifact')
            if item['status'] != ('PASS' if _content(item) == _content(expected) else 'FAIL'):
                raise ValueError('evidence status contradicts observed hashes')
    if record['status'] != _status([item['status'] for item in observations]):
        raise ValueError('evidence aggregate contradicts observations')
    return record


def evaluate_build(project: Path, build_id: str, evidence_ids: list[str]) -> dict:
    """Evaluate selected evidence with fresh hashing; never insert new evidence."""
    _hex_id(build_id)
    if type(evidence_ids) is not list or not evidence_ids or len(evidence_ids) > 128:
        raise ValueError('evaluation requires 1 to 128 unique evidence IDs')
    for evidence_id in evidence_ids:
        _hex_id(evidence_id, 32)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError('duplicate evidence IDs')
    with _locked(project) as (store, marker, lock_info):
        with _database(store, marker, lock_info, readonly=True) as connection:
            build = _load_build(connection, build_id)
            evidence = [_load_evidence(connection, identifier) for identifier in evidence_ids]
        _reject_store_artifacts(store, _build_paths(build))
        observations = _measure(build)
        statuses = [item['status'] for item in observations]
        reasons = []
        for identifier, item in zip(evidence_ids, evidence):
            if item is None:
                statuses.append('BLOCKED')
                reasons.append(f'evidence not found: {identifier}')
            elif item['build_id'] != build_id:
                statuses.append('FAIL')
                reasons.append(f'evidence belongs to another build: {identifier}')
            else:
                statuses.append(item['status'])
                if item['status'] != 'PASS':
                    reasons.append(f'evidence did not pass: {identifier}')
        status = _status(statuses)
        return {'schema_version': SCHEMA_VERSION, 'scope': SCOPE, 'ok': status == 'PASS',
                'build_id': build_id, 'tool_version': ROMANCER_VERSION, 'status': status,
                'evidence_ids': list(evidence_ids), 'observations': observations, 'reasons': reasons}
