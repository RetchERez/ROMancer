"""Application-owned evidence records; imported JSON never grants execution trust."""
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import re
import tempfile
import sqlite3
import stat
import threading
from contextlib import closing,contextmanager
import uuid
from .assets import checked_path
from .script_schema import canonical_bytes,load_script_json
from .workbench_projects import identifier,write_json


_KEY_LOCK=threading.Lock()


@contextmanager
def _key_file_lock(project):
    # Keep this coordination file in place: unlinking a locked inode would let
    # another process create a different lock and bypass mutual exclusion.
    path=checked_path(Path(project)/'.evidence-key.lock')
    with path.open('a+b') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise ValueError('invalid evidence key lock')
        if os.name=='nt':
            import msvcrt
            if info.st_size==0:stream.write(b'0');stream.flush()
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
            try:yield
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def _key(project):
    # Automatic scans and separate AI/CLI processes can initialize concurrently.
    # Keep all readers behind creation, close and permission setup;
    # an existing malformed or linked key must still fail rather than retry.
    with _KEY_LOCK,_key_file_lock(project):
        path=checked_path(Path(project)/'.evidence-key')
        if not path.exists():
            try:
                with path.open('xb') as stream:stream.write(secrets.token_bytes(32))
                if os.name!='nt':path.chmod(0o600)
            except FileExistsError:pass
        if path.stat().st_size!=32 or path.stat().st_nlink!=1:raise ValueError('invalid evidence key')
        return path.read_bytes()


def store_evidence(project,kind,report):
    if kind not in ('route','regression','coverage','runtime','release'):raise ValueError('unsupported evidence kind')
    record={'schema_version':1,'evidence_id':uuid.uuid4().hex,'kind':kind,'report':report}
    record['signature']=hmac.new(_key(project),canonical_bytes(record,max_bytes=8*1024**2),hashlib.sha256).hexdigest()
    write_json(Path(project)/'reports'/(record['evidence_id']+'.json'),record)
    return record


def _historical_index(project):
    path=checked_path(Path(project)/'.historical-evidence/index.json')
    if not path.exists():return {}
    value=load_script_json(path,max_bytes=2*1024**2)
    if type(value) is not dict or value.get('schema_version')!=1 or type(value.get('records')) is not dict or len(value['records'])>8192:raise ValueError('invalid historical evidence index')
    for identifier,key in value['records'].items():
        if not re.fullmatch('[0-9a-f]{32}',identifier) or type(key) is not str or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('invalid historical evidence identity')
    return value['records']


def historical_captures(project):
    path=checked_path(Path(project)/'.historical-evidence/index.json')
    if not path.exists():return set()
    values=load_script_json(path,max_bytes=2*1024**2).get('capture_ids',[])
    if type(values) is not list or len(values)>8192 or any(type(value) is not str or not re.fullmatch('[0-9a-f]{32}',value) for value in values):raise ValueError('invalid historical capture index')
    return set(values)


def quarantine_restored_evidence(project):
    """Archive keys authenticate historical bytes, never fresh local execution."""
    project=Path(project);records=_historical_index(project);captures=historical_captures(project);old=checked_path(project/'.evidence-key')
    if old.exists():
        key=_key(project);key_id=hashlib.sha256(key).hexdigest();folder=project/'.historical-evidence/keys';folder.mkdir(parents=True,exist_ok=True);target=folder/(key_id+'.key')
        if target.exists():
            if target.read_bytes()!=key:raise ValueError('historical key identity mismatch')
        else:
            with target.open('xb') as stream:stream.write(key)
        for path in (project/'reports').glob('*.json'):
            if re.fullmatch('[0-9a-f]{32}',path.stem):records.setdefault(path.stem,key_id)
    if len(records)>8192:raise ValueError('historical evidence budget exceeded')
    folder=project/'.historical-evidence';folder.mkdir(exist_ok=True)
    database=checked_path(project/'.romancer-evidence/captures.sqlite3')
    if database.exists():
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as connection:
            connection.execute('PRAGMA trusted_schema=OFF')
            captures.update(row[0] for row in connection.execute('SELECT capture_id FROM captures LIMIT 8193'))
    if len(captures)>8192:raise ValueError('historical capture budget exceeded')
    write_json(folder/'index.json',{'schema_version':1,'records':records,'capture_ids':sorted(captures)},max_bytes=2*1024**2)
    descriptor,name=tempfile.mkstemp(prefix='.fresh-evidence-',dir=project)
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(secrets.token_bytes(32));stream.flush();os.fsync(stream.fileno())
        os.replace(name,project/'.evidence-key')
        if os.name!='nt':(project/'.evidence-key').chmod(0o600)
    finally:Path(name).unlink(missing_ok=True)


def load_evidence(project,evidence_id,kind=None):
    identifier(evidence_id);path=checked_path(Path(project)/'reports'/(evidence_id+'.json'))
    record=load_script_json(path,max_bytes=8*1024**2);signature=record.pop('signature',None)
    historical=_historical_index(project).get(evidence_id)
    if historical:
        key_path=checked_path(Path(project)/'.historical-evidence/keys'/(historical+'.key'))
        if key_path.stat().st_size!=32 or key_path.stat().st_nlink!=1:raise ValueError('invalid historical evidence key')
        key=key_path.read_bytes()
        if hashlib.sha256(key).hexdigest()!=historical:raise ValueError('historical key identity mismatch')
    else:key=_key(project)
    if (type(signature) is not str or not hmac.compare_digest(signature,hmac.new(key,canonical_bytes(record,max_bytes=8*1024**2),hashlib.sha256).hexdigest())
            or record.get('evidence_id')!=evidence_id or (kind is not None and record.get('kind')!=kind)):
        raise ValueError('evidence record is not application-authenticated')
    return {**record,'runtime_trusted':not bool(historical),'authentication':'historical_import' if historical else 'current_application'}
