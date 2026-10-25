"""Private capture storage. Integrity and supplied annotations are not gameplay proof."""
from contextlib import contextmanager, closing
from datetime import datetime
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid

from .history import canonical_json, strict_json_loads
from .cd_patch import check_output_paths

STORE_NAME = '.romancer-evidence'
DB_NAME = 'captures.sqlite3'
MAX_SOURCE = 1024 * 1024
MAX_PNG = 16 * 1024 * 1024
MAX_RGB = 8 * 1024 * 1024
MAX_RECORD = 64 * 1024
MAX_ANNOTATION = 16 * 1024
MAX_CAPTURES = 4096
MAX_ANNOTATIONS = 32768
MAX_METADATA_TOTAL = 64 * 1024 * 1024
MAX_BLOB_TOTAL = 512 * 1024 * 1024
MAX_DATABASE = 768 * 1024 * 1024
LOCK_TIMEOUT = 2.0
CHUNK_SIZE = 64 * 1024
SCHEMA = {
    'store_meta': 'CREATE TABLE store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
    'blobs': 'CREATE TABLE blobs (sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL, media_type TEXT NOT NULL, content BLOB NOT NULL)',
    'captures': 'CREATE TABLE captures (capture_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL)',
    'annotations': 'CREATE TABLE annotations (annotation_id TEXT PRIMARY KEY, capture_id TEXT NOT NULL REFERENCES captures(capture_id), record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL)',
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError('unexpected record fields: expected ' + names)


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside supported bounds')


def _text(value, maximum=256, *, blank=False):
    if (type(value) is not str or len(value) > maximum or '\0' in value
            or (not blank and not value.strip())):
        raise ValueError('invalid bounded text')


def _hex(value, length=64):
    if type(value) is not str or re.fullmatch('[0-9a-f]{'+str(length)+'}', value) is None:
        raise ValueError('invalid identifier/digest')


def _json(value, maximum=MAX_RECORD):
    nodes = 0
    def visit(item, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 10000 or depth > 32:
            raise ValueError('JSON depth/node budget exceeded')
        if type(item) is str:
            if len(item) > maximum:
                raise ValueError('JSON string exceeds byte budget')
        elif type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError('JSON keys must be strings')
                visit(key, depth+1)
                visit(child, depth+1)
        elif type(item) is list:
            for child in item:
                visit(child, depth+1)
        elif item is not None and type(item) not in (bool, int, float):
            raise ValueError('plain JSON types required')
    visit(value)
    return canonical_json(value, max_bytes=maximum)


def _parse(raw, maximum=MAX_SOURCE):
    result = strict_json_loads(raw, max_bytes=maximum)
    _json(result, maximum)
    return result


def _path(path):
    path = Path(path)
    if os.name == 'nt' and path.drive and not path.root:
        raise ValueError('drive-relative path is ambiguous')
    path = path.absolute()
    if os.name == 'nt' and (os.path.isreserved(path) or str(path).startswith(('\\\\?\\', '\\\\.\\'))):
        raise ValueError('reserved/ambiguous path')
    for part in (path, *path.parents):
        if os.path.lexists(part):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('linked/reparse paths are not permitted')
    return path.resolve()


def _regular(path, single=False):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or (single and info.st_nlink != 1):
        raise ValueError('ordinary file required')
    return info


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_file(path, limit=MAX_SOURCE):
    path = _path(path)
    before = _regular(path)
    if before.st_size > limit:
        raise ValueError('source byte budget exceeded')
    data = bytearray()
    with path.open('rb') as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise ValueError('source changed before read')
        while chunk := stream.read(min(CHUNK_SIZE, limit-len(data)+1)):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('source byte budget exceeded')
        if (len(data) != before.st_size or _identity(os.fstat(stream.fileno())) != _identity(before)
                or _identity(path.lstat()) != _identity(before)):
            raise ValueError('source changed during read')
    # Some filesystems coalesce timestamps for rapid same-length writes.
    # Independently reread the bytes before treating this snapshot as stable.
    observed = hashlib.sha256()
    count = 0
    with path.open('rb') as verify:
        if _identity(os.fstat(verify.fileno())) != _identity(before):
            raise ValueError('source changed before verification')
        while chunk := verify.read(min(CHUNK_SIZE, limit-count+1)):
            count += len(chunk)
            if count > limit:raise ValueError('source byte budget exceeded')
            observed.update(chunk)
        if (count != len(data) or observed.digest() != hashlib.sha256(data).digest()
                or _identity(os.fstat(verify.fileno())) != _identity(before)
                or _identity(path.lstat()) != _identity(before)):
            raise ValueError('source changed during verification')
    return bytes(data)


def _root(project):
    root = _path(project)
    if not root.is_dir():
        raise ValueError('existing project directory required')
    return root


def _marker(directory):
    _path(directory)
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('ordinary store directory required')
    _regular(directory / 'owner.json', True)
    marker = _parse(_read_file(directory / 'owner.json', MAX_RECORD), MAX_RECORD)
    _fields(marker, 'schema_version store_id directory_identity')
    _int(marker['schema_version'], 1, 1)
    _hex(marker['store_id'], 32)
    if marker['directory_identity'] != [info.st_dev, info.st_ino]:
        raise ValueError('store ownership mismatch')
    return marker


def _footprint(directory):
    marker = _marker(directory)
    if set(p.name for p in directory.iterdir()) - {'owner.json', DB_NAME, 'operation.lock'}:
        raise ValueError('unknown/recovery files require explicit recovery')
    _regular(directory / DB_NAME, True)
    if (directory / DB_NAME).stat().st_size > MAX_DATABASE:
        raise ValueError('database byte budget exceeded')
    with (directory / DB_NAME).open('rb') as stream:
        header = stream.read(20)
    if header[:16] != b'SQLite format 3\0' or header[18:20] != b'\x01\x01':
        raise ValueError('DELETE-journal SQLite database required')
    return marker


def _unlink_owned(path, info):
    try:
        if os.path.samestat(path.lstat(), info):
            path.unlink()
    except FileNotFoundError:
        pass


@contextmanager
def _database(project):
    directory = _root(project) / STORE_NAME
    lock = directory / 'operation.lock'
    end = time.monotonic()+LOCK_TIMEOUT
    while True:
        marker = _marker(directory)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            _regular(lock, True)
            if time.monotonic() >= end:
                raise OSError('capture store lock busy; explicit recovery may be required')
            time.sleep(0.01)
    owned = os.fstat(fd)
    os.close(fd)
    try:
        if _footprint(directory) != marker:
            raise ValueError('store changed')
        with closing(sqlite3.connect((directory / DB_NAME).as_uri()+'?mode=rw', uri=True,
                                     isolation_level=None, timeout=LOCK_TIMEOUT)) as connection:
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA foreign_keys=ON')
            if (connection.execute('PRAGMA user_version').fetchone()[0] != 1
                    or dict(connection.execute('SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL')) != SCHEMA
                    or dict(connection.execute('SELECT key, value FROM store_meta')) != {'store_id': marker['store_id'], 'schema_version': '1'}
                    or connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]):
                raise ValueError('store schema/integrity mismatch')
            pages = MAX_DATABASE // connection.execute('PRAGMA page_size').fetchone()[0]
            connection.execute(f'PRAGMA max_page_count={pages}')
            _metadata_limits(connection)
            if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError('store contains orphan annotation metadata')
            yield connection, directory, {'owner': marker, 'lock': owned,
                                          'database': _regular(directory / DB_NAME, True)}
    finally:
        _unlink_owned(lock, owned)


def init_capture_store(project):
    directory = _root(project) / STORE_NAME
    if os.path.lexists(directory):
        raise ValueError('capture store already exists')
    directory.mkdir(mode=0o700)
    info = directory.stat()
    marker = dict(schema_version=1, store_id=uuid.uuid4().hex,
                  directory_identity=[info.st_dev, info.st_ino])
    # Initialization failures retain their owned footprint for explicit recovery.
    with (directory / 'owner.json').open('xb') as stream:
        stream.write(_json(marker).encode())
        stream.flush()
        os.fsync(stream.fileno())
    with closing(sqlite3.connect(directory / DB_NAME)) as connection:
        connection.execute('PRAGMA journal_mode=DELETE')
        with connection:
            for sql in SCHEMA.values():
                connection.execute(sql)
            connection.execute('PRAGMA user_version=1')
            connection.executemany('INSERT INTO store_meta VALUES (?,?)',
                                  [('store_id', marker['store_id']), ('schema_version', '1')])
    return {'ok': True, 'scope': 'capture_ingestion', 'status': 'INITIALIZED'}


def _validate_capture(record):
    _json(record)
    _fields(record, 'schema_version canonical_version capture_id created_utc tool_version origin image build run import_source natural_progress_verified')
    _int(record['schema_version'], 1, 1)
    _int(record['canonical_version'], 1, 1)
    _hex(record['capture_id'], 32)
    _text(record['created_utc'])
    if datetime.fromisoformat(record['created_utc']).utcoffset() is None:
        raise ValueError('capture timestamp must be timezone-aware')
    _text(record['tool_version'])
    if record['natural_progress_verified'] is not False:
        raise ValueError('capture cannot prove natural progression')
    image = record['image']
    _fields(image, 'blob_sha256 byte_size width height rgb_sha256 media_type normalization')
    _hex(image['blob_sha256'])
    _hex(image['rgb_sha256'])
    _int(image['byte_size'], 1, MAX_PNG)
    _int(image['width'], 1, 4096)
    _int(image['height'], 1, 4096)
    if image['width']*image['height']*3 > MAX_RGB or image['media_type'] != 'image/png' or image['normalization'] != 'rgb24':
        raise ValueError('unsupported image format/bounds')
    build = record['build']
    if build is not None:
        _fields(build, 'build_id identity locations association')
        _hex(build['build_id'])
        if _sha(_json(build['identity']).encode()) != build['build_id']:
            raise ValueError('build identity hash mismatch')
        _fields(build['locations'], 'inputs output')
    if record['origin'] == 'imported_image':
        if record['run'] is not None or (build and build['association'] != 'imported_claim'):
            raise ValueError('import cannot claim native run')
        source = record['import_source']
        _fields(source, 'path_hint image_sha256 manifest_sha256 manifest_kind manifest_path_hint declared_context')
        _text(source['path_hint'], 4096)
        _hex(source['manifest_sha256'])
        if source['image_sha256'] != image['blob_sha256'] or source['manifest_kind'] not in ('original_file', 'canonical_api_input'):
            raise ValueError('invalid manifest/image provenance')
        if source['manifest_kind'] == 'original_file':
            _text(source['manifest_path_hint'], 4096)
            if not Path(source['manifest_path_hint']).is_absolute():
                raise ValueError('original manifest path must be absolute')
        elif source['manifest_path_hint'] is not None:
            raise ValueError('canonical API input has no original manifest path')
    elif record['origin'] == 'native_worker':
        if record['import_source'] is not None or not build or build['association'] != 'measured_run_output':
            raise ValueError('native capture requires measured build binding')
        run = record['run']
        _fields(run, 'run_id worker_tool_version core_sha256 game_sha256 core_info av core_options game_dependencies frame run_mode provenance dependency_coverage steps initial_state_sha256 initial_game_save_sha256 build_checks')
        _hex(run['run_id'], 32)
        _text(run['worker_tool_version'])
        _hex(run['core_sha256'])
        for key in ('core_info', 'av', 'core_options'):
            if type(run[key]) is not dict:
                raise ValueError('runtime metadata must be objects')
        _fields(run['frame'], 'index width height pitch pixel_format sha256')
        _int(run['frame']['index'], 1, 2**63-1)
        _int(run['frame']['pitch'], 1, 2**63-1)
        _text(run['frame']['pixel_format'])
        if run['game_sha256'] != build['identity']['output']['sha256']:
            raise ValueError('native game does not match build')
        if run['frame']['sha256'] != image['rgb_sha256'] or any(run['frame'][k] != image[k] for k in ('width', 'height')):
            raise ValueError('native frame binding mismatch')
        if run['run_mode'] not in ('cold_boot', 'imported_save_state', 'game_save_continuation') or run['dependency_coverage'] != 'supplied_paths_only':
            raise ValueError('unsupported native run mode/scope')
        _fields(run['provenance'], 'origin state_derived ancestor_state_sha256 parent_checkpoint_sha256 trust')
        provenance = run['provenance']
        if provenance['origin'] != run['run_mode']:
            raise ValueError('run provenance mismatch')
        if provenance['state_derived'] is not None and type(provenance['state_derived']) is not bool:
            raise ValueError('unknown/boolean state ancestry required')
        for value in [provenance['ancestor_state_sha256'], provenance['parent_checkpoint_sha256'],
                      run['initial_state_sha256'], run['initial_game_save_sha256']]:
            if value is not None:
                _hex(value)
        if provenance['ancestor_state_sha256'] and provenance['state_derived'] is not True:
            raise ValueError('state ancestor cannot be cleared')
        if run['run_mode'] == 'cold_boot':
            if (provenance['state_derived'] is not False or provenance['parent_checkpoint_sha256'] is not None
                    or run['initial_state_sha256'] is not None or run['initial_game_save_sha256'] is not None):
                raise ValueError('cold boot cannot have checkpoint ancestry')
        elif run['run_mode'] == 'imported_save_state':
            if (provenance['state_derived'] is not True or not run['initial_state_sha256']
                    or provenance['ancestor_state_sha256'] != run['initial_state_sha256']
                    or provenance['parent_checkpoint_sha256'] != run['initial_state_sha256']):
                raise ValueError('imported-state binding mismatch')
        elif not run['initial_game_save_sha256'] or provenance['parent_checkpoint_sha256'] != run['initial_game_save_sha256']:
            raise ValueError('game-save ancestry binding mismatch')
        expected_trust = 'supplied_checkpoint_metadata' if run['run_mode'] == 'game_save_continuation' else 'current_worker'
        if provenance['trust'] != expected_trust:
            raise ValueError('unsupported provenance trust')
        if type(run['steps']) is not list or not 1 <= len(run['steps']) <= 100:
            raise ValueError('1..100 acknowledged steps required')
        total = 0
        previous = 0
        for step in run['steps']:
            _fields(step, 'frames buttons port frame_index')
            _int(step['frames'], 1, 600)
            _int(step['port'], 0, 3)
            _int(step['frame_index'], previous+1, 2**63-1)
            if type(step['buttons']) is not list or len(step['buttons']) > 16 or any(type(b) is not str or not b for b in step['buttons']):
                raise ValueError('invalid acknowledged buttons')
            previous = step['frame_index']
            total += step['frames']
        if total > 6000 or run['frame']['index'] > previous:
            raise ValueError('frame/step bounds mismatch')
        if type(run['game_dependencies']) is not list or len(run['game_dependencies']) > 512:
            raise ValueError('invalid dependency list')
        for dependency in run['game_dependencies']:
            _fields(dependency, 'relative expected_sha256')
            _text(dependency['relative'], 4096)
            _hex(dependency['expected_sha256'])
        _fields(run['build_checks'], 'before after')
        for identifier in run['build_checks'].values():
            _hex(identifier, 32)
    else:
        raise ValueError('unsupported capture origin')


def _decode(text, digest, maximum):
    if type(text) is not str or len(text) > maximum or _sha(text.encode()) != digest:
        raise ValueError('corrupt record hash/size')
    record = _parse(text, maximum)
    if _json(record, maximum) != text:
        raise ValueError('noncanonical record')
    return record


def _load_capture(connection, identifier):
    _hex(identifier, 32)
    row = connection.execute('SELECT record_json,record_sha256 FROM captures WHERE capture_id=?', (identifier,)).fetchone()
    if row is None:
        raise ValueError('capture not found')
    record = _decode(*row, MAX_RECORD)
    _validate_capture(record)
    if record['capture_id'] != identifier:
        raise ValueError('capture identity mismatch')
    return record


def _validate_entry(entry, capture, source):
    _fields(entry, 'kind text method author locator region resource supersedes')
    if entry['kind'] not in ('text', 'scene', 'speaker', 'note', 'resource') or entry['method'] not in ('manual', 'imported_ocr', 'imported_report', 'profile_label'):
        raise ValueError('unsupported annotation kind/method')
    _text(entry['text'], 4096)
    _text(entry['author'])
    if entry['locator'] is not None:
        _text(entry['locator'])
    if entry['method'] == 'imported_ocr' and (not source or not entry['locator']):
        raise ValueError('imported OCR needs an explicit source and engine/report locator')
    if entry['supersedes'] is not None:
        _hex(entry['supersedes'], 32)
    region = entry['region']
    if region is not None:
        if type(region) is not list or len(region) != 4:
            raise ValueError('invalid annotation region')
        x, y, width, height = region
        for value in (x, y):
            _int(value, 0, 4095)
        for value in (width, height):
            _int(value, 1, 4096)
        if x+width > capture['image']['width'] or y+height > capture['image']['height']:
            raise ValueError('region outside capture')
    resource = entry['resource']
    if entry['kind'] != 'resource':
        if resource is not None:
            raise ValueError('only resource annotations contain resource bindings')
    else:
        _fields(resource, 'build_id artifact_role artifact_sha256 resource_id offset length')
        build = capture['build']
        if build is None or resource['build_id'] != build['build_id']:
            raise ValueError('resource belongs to another/unbound build')
        _text(resource['resource_id'])
        _text(resource['artifact_role'], 128)
        inputs = build['identity']['inputs']
        if any(item['role'] == 'output' for item in inputs):
            raise ValueError('ambiguous output artifact role')
        candidates = [item for item in inputs if item['role'] == resource['artifact_role']]
        if resource['artifact_role'] == 'output':
            candidates = [build['identity']['output']]
        if len(candidates) != 1 or resource['artifact_sha256'] != candidates[0]['sha256']:
            raise ValueError('resource artifact identity mismatch')
        _int(resource['offset'], 0, candidates[0]['size'])
        _int(resource['length'], 1, candidates[0]['size'])
        if resource['offset']+resource['length'] > candidates[0]['size']:
            raise ValueError('resource range exceeds artifact')


def _validate_annotation(record, capture):
    _json(record, MAX_ANNOTATION)
    _fields(record, 'schema_version annotation_id capture_id created_utc origin entry source')
    _int(record['schema_version'], 1, 1)
    _hex(record['annotation_id'], 32)
    _text(record['created_utc'])
    if record['capture_id'] != capture['capture_id'] or record['origin'] != 'imported_annotation':
        raise ValueError('invalid annotation binding/origin')
    source = record['source']
    if source is not None:
        _fields(source, 'sha256 path_hint')
        _hex(source['sha256'])
        if source['path_hint'] is not None:
            _text(source['path_hint'], 4096)
    _validate_entry(record['entry'], capture, source)


def _load_annotations(connection, capture):
    rows = connection.execute('SELECT annotation_id,record_json,record_sha256 FROM annotations WHERE capture_id=? ORDER BY annotation_id',
                              (capture['capture_id'],)).fetchmany(257)
    if len(rows) > 256:
        raise ValueError('capture annotation budget exceeded')
    result = []
    for identifier, text, digest in rows:
        record = _decode(text, digest, MAX_ANNOTATION)
        _validate_annotation(record, capture)
        if record['annotation_id'] != identifier:
            raise ValueError('annotation identity mismatch')
        result.append(record)
    _annotation_graph(result)
    return result


def _annotation_graph(records):
    parents = {r['annotation_id']: r['entry']['supersedes'] for r in records}
    used = set()
    for parent in parents.values():
        if parent is not None:
            if parent not in parents or parent in used:
                raise ValueError('unknown/cross-capture or competing supersession')
            used.add(parent)
    for identifier in parents:
        seen = set()
        while identifier is not None:
            if identifier in seen:
                raise ValueError('cyclic annotation supersession')
            seen.add(identifier)
            identifier = parents[identifier]


def _put_annotations(connection, capture, records):
    if type(records) not in (list, tuple) or len(records) > 64:
        raise ValueError('annotation batch exceeds 64 entries')
    existing = _load_annotations(connection, capture)
    if len(existing)+len(records) > 256:
        raise ValueError('capture annotation budget exceeded')
    for record in records:
        _validate_annotation(record, capture)
        if record['source'] is not None:
            _blob(connection, record['source']['sha256'], MAX_SOURCE)
    _annotation_graph([*existing, *records])
    for record in records:
        text = _json(record, MAX_ANNOTATION)
        connection.execute('INSERT INTO annotations VALUES (?,?,?,?)',
                           (record['annotation_id'], capture['capture_id'], text, _sha(text.encode())))


def _blob(connection, digest, limit=MAX_PNG):
    _hex(digest)
    row = connection.execute('SELECT size,media_type,length(content) FROM blobs WHERE sha256=?', (digest,)).fetchone()
    if row is None or type(row[0]) is not int or row[0] != row[2] or not 0 <= row[0] <= limit:
        raise ValueError('missing/corrupt blob size')
    raw = connection.execute('SELECT content FROM blobs WHERE sha256=?', (digest,)).fetchone()[0]
    if type(raw) is not bytes or _sha(raw) != digest:
        raise ValueError('corrupt blob hash')
    return raw, row[1]


def _deadline(deadline):
    if deadline is not None:
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError('invalid publication deadline')
        if time.monotonic() >= deadline:
            raise TimeoutError('capture publication deadline expired')


def _before_commit(directory, marker):
    if (_marker(directory) != marker['owner']
            or not os.path.samestat(_regular(directory / 'operation.lock', True), marker['lock'])
            or not os.path.samestat(_regular(directory / DB_NAME, True), marker['database'])):
        raise ValueError('store ownership changed during write')


def _metadata_limits(connection):
    total = 0
    for table, limit, count_limit in [('captures', MAX_RECORD, MAX_CAPTURES),
                                       ('annotations', MAX_ANNOTATION, MAX_ANNOTATIONS)]:
        count, largest, size = connection.execute(
            f'SELECT count(*),coalesce(max(length(CAST(record_json AS BLOB))),0),coalesce(sum(length(CAST(record_json AS BLOB))),0) FROM {table}').fetchone()
        if count > count_limit or largest > limit:
            raise ValueError('metadata record/count budget exceeded')
        total += size
    if total > MAX_METADATA_TOTAL:
        raise ValueError('metadata aggregate budget exceeded')


def _quotas(connection):
    for table, limit in [('captures', MAX_CAPTURES), ('annotations', MAX_ANNOTATIONS)]:
        if connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] > limit:
            raise ValueError('record count budget exceeded')
    metadata = sum(connection.execute(f'SELECT coalesce(sum(length(record_json)),0) FROM {table}').fetchone()[0]
                   for table in ('captures', 'annotations'))
    if metadata > MAX_METADATA_TOTAL or connection.execute('SELECT coalesce(sum(length(content)),0) FROM blobs').fetchone()[0] > MAX_BLOB_TOTAL:
        raise ValueError('aggregate store budget exceeded')


def _put_blobs(connection, blobs):
    if type(blobs) is not dict or len(blobs) > 66:
        raise ValueError('invalid blob batch')
    for digest, blob in blobs.items():
        _hex(digest)
        _fields(blob, 'media_type content')
        raw = blob['content']
        limit = MAX_PNG if blob['media_type'] == 'image/png' else MAX_SOURCE
        if blob['media_type'] not in ('image/png', 'application/json', 'application/octet-stream') or type(raw) is not bytes or len(raw) > limit or _sha(raw) != digest:
            raise ValueError('invalid blob bytes/type/hash')
        if connection.execute('SELECT 1 FROM blobs WHERE sha256=?', (digest,)).fetchone():
            old, media_type = _blob(connection, digest, limit)
            if old != raw:
                raise ValueError('conflicting existing blob')
            if blob['media_type'] == 'image/png' and media_type != 'image/png':
                connection.execute('UPDATE blobs SET media_type=? WHERE sha256=?', ('image/png', digest))
        else:
            connection.execute('INSERT INTO blobs VALUES (?,?,?,?)', (digest, len(raw), blob['media_type'], raw))


def _verify_references(connection, record):
    image = record['image']
    raw, media = _blob(connection, image['blob_sha256'])
    if len(raw) != image['byte_size'] or media != 'image/png':
        raise ValueError('image reference mismatch')
    if record['import_source'] is not None:
        _blob(connection, record['import_source']['manifest_sha256'], MAX_SOURCE)
    return raw


@contextmanager
def _transaction(connection, directory, marker, size=0, deadline=None):
    _deadline(deadline)
    if shutil.disk_usage(directory).free < (directory / DB_NAME).stat().st_size + 2*size + 16*1024*1024:
        raise OSError('insufficient free space for capture transaction/journal')
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        _quotas(connection)
        _before_commit(directory, marker)
        _deadline(deadline)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _insert_capture(project, record, blobs, annotations=(), *, publication_deadline=None):
    record = _parse(_json(record), MAX_RECORD)
    _validate_capture(record)
    with _database(project) as (connection, directory, marker):
        with _transaction(connection, directory, marker, sum(len(b['content']) for b in blobs.values()), publication_deadline):
            _put_blobs(connection, blobs)
            _verify_references(connection, record)
            text = _json(record)
            connection.execute('INSERT INTO captures VALUES (?,?,?)', (record['capture_id'], text, _sha(text.encode())))
            _put_annotations(connection, record, annotations)
    return dict(ok=True, capture_id=record['capture_id'], scope='capture_ingestion')


def _insert_annotations(project, capture_id, records, blobs):
    if type(records) is not list or not 1 <= len(records) <= 64:
        raise ValueError('1..64 annotations required')
    with _database(project) as (connection, directory, marker):
        capture = _load_capture(connection, capture_id)
        with _transaction(connection, directory, marker, sum(len(b['content']) for b in blobs.values())):
            _put_blobs(connection, blobs)
            _put_annotations(connection, capture, records)
    return dict(ok=True, scope='capture_annotations', annotation_ids=[r['annotation_id'] for r in records])


def get_capture(project, capture_id, *, after_annotation_id=None, limit=16):
    _int(limit, 1, 32)
    if after_annotation_id is not None:
        _hex(after_annotation_id, 32)
    with _database(project) as (connection, _, __):
        record = _load_capture(connection, capture_id)
        raw = _verify_references(connection, record)
        annotations = [r for r in _load_annotations(connection, record) if after_annotation_id is None or r['annotation_id'] > after_annotation_id]
        page = annotations[:limit]
        for annotation in page:
            if annotation['source'] is not None:
                _blob(connection, annotation['source']['sha256'], MAX_SOURCE)
    from .workbench_evidence import historical_captures
    historical=capture_id in historical_captures(project)
    return dict(ok=True, scope='capture_integrity', runtime_trusted=not historical, authentication='historical_import' if historical else 'current_application', record=record, annotations=page, has_more=len(annotations)>limit,
                next_after_annotation_id=page[-1]['annotation_id'] if len(annotations)>limit else None,
                png_bytes=raw, image_integrity='PASS', build_currentness='NOT_CHECKED')


def search_captures(project, query):
    if type(query) is not dict or set(query) - {'text', 'scene', 'build_id', 'resource_id', 'origin', 'run_mode', 'include_superseded', 'after_id', 'limit'}:
        raise ValueError('invalid capture search fields')
    query = _parse(_json(query))
    limit = query.get('limit', 20)
    _int(limit, 1, 100)
    for key in ('text', 'scene', 'resource_id'):
        if key in query:
            _text(query[key])
    for key, size in (('build_id', 64), ('after_id', 32)):
        if key in query:
            _hex(query[key], size)
    if 'resource_id' in query and 'build_id' not in query:
        raise ValueError('resource search requires exact build ID')
    if ('origin' in query and query['origin'] not in ('native_worker', 'imported_image')
            or 'run_mode' in query and query['run_mode'] not in ('cold_boot', 'imported_save_state', 'game_save_continuation')
            or type(query.get('include_superseded', False)) is not bool):
        raise ValueError('invalid provenance/search option')
    matches = []
    with _database(project) as (connection, _, __):
        _quotas(connection)
        # Validate every metadata row, even those outside the chosen filters.
        identifiers = [row[0] for row in connection.execute('SELECT capture_id FROM captures ORDER BY capture_id')]
        for identifier in identifiers:
            capture = _load_capture(connection, identifier)
            annotations = _load_annotations(connection, capture)
            if not query.get('include_superseded', False):
                superseded = {a['entry']['supersedes'] for a in annotations}
                annotations = [a for a in annotations if a['annotation_id'] not in superseded]
            build = capture['build']
            run = capture['run']
            if ('after_id' in query and identifier <= query['after_id']
                    or 'build_id' in query and (not build or build['build_id'] != query['build_id'])
                    or 'origin' in query and capture['origin'] != query['origin']
                    or 'run_mode' in query and (not run or run['run_mode'] != query['run_mode'])):
                continue
            selected = set()
            matched = True
            for key in ('text', 'scene', 'resource_id'):
                if key not in query:
                    continue
                hits = []
                for annotation in annotations:
                    entry = annotation['entry']
                    if (key == 'text' and query[key].casefold() in entry['text'].casefold()
                            or key == 'scene' and entry['kind'] == 'scene' and query[key].casefold() == entry['text'].casefold()
                            or key == 'resource_id' and entry['kind'] == 'resource' and query[key] == entry['resource']['resource_id']):
                        hits.append(annotation['annotation_id'])
                if not hits:
                    matched = False
                selected.update(hits)
            if not matched:
                continue
            shown = [a for a in annotations if not selected or a['annotation_id'] in selected]
            snippets = [dict(annotation_id=a['annotation_id'], kind=a['entry']['kind'], method=a['entry']['method'],
                             text=a['entry']['text'][:256], source_sha256=a['source']['sha256'] if a['source'] else None)
                        for a in shown[:8]]
            matches.append(dict(capture_id=identifier, image=dict(capture['image']),
                                build_id=build['build_id'] if build else None,
                                association=build['association'] if build else None,
                                origin=capture['origin'], run_mode=run['run_mode'] if run else None,
                                provenance=run['provenance'] if run else None,
                                natural_progress_verified=False, annotations=snippets,
                                annotation_matches=len(shown), annotations_truncated=len(shown)>8,
                                image_integrity='NOT_CHECKED', build_currentness='NOT_CHECKED'))
    page = matches[:limit]
    while True:
        result = dict(ok=True, scope='capture_search', matches=page, has_more=len(matches)>len(page),
                      next_after_id=page[-1]['capture_id'] if page and len(matches)>len(page) else None)
        try:
            canonical_json(result, max_bytes=MAX_SOURCE)
            return result
        except ValueError:
            if len(page) <= 1:
                raise
            page = page[:-1]


def _protect_sources(project, paths):
    root = _root(project)
    for supplied in paths:
        path = _path(supplied)
        for name in (STORE_NAME, '.romancer-history'):
            directory = root / name
            if path == directory or directory in path.parents:
                raise ValueError('source/output cannot be inside a private store')
            if directory.is_dir():
                for entry in directory.iterdir():
                    if path.exists() and entry.is_file() and os.path.samefile(entry, path):
                        raise ValueError('source/output aliases store file')


def export_capture(project, capture_id, destination):
    result = get_capture(project, capture_id)
    destination = _path(destination)
    _protect_sources(project, [destination])
    record = result['record']
    sources = []
    if record['build']:
        locations = record['build']['locations']
        sources = [locations['output'], *(item['path'] for item in locations['inputs'])]
    if record['import_source']:
        sources.append(record['import_source']['path_hint'])
        if record['import_source']['manifest_path_hint'] is not None:
            sources.append(record['import_source']['manifest_path_hint'])
    with _database(project) as (connection, _, __):
        sources.extend(item['source']['path_hint'] for item in _load_annotations(connection, record)
                       if item['source'] and item['source']['path_hint'])
    for source in sources:
        check_output_paths(Path(source), [destination])
    if os.path.lexists(destination):
        raise ValueError('export refuses existing output')
    if not destination.parent.is_dir():
        raise ValueError('export parent must exist')
    fd, name = tempfile.mkstemp(prefix='.capture-', dir=destination.parent)
    temporary = Path(name)
    owned = os.fstat(fd)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(result['png_bytes'])
            stream.flush()
            os.fsync(stream.fileno())
        _path(destination)
        os.link(temporary, destination)
    finally:
        _unlink_owned(temporary, owned)
    return dict(ok=True, scope='capture_integrity', path=str(destination), sha256=_sha(result['png_bytes']), role='private_capture')
