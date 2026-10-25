"""Owned projects, immutable imported copies, and content-bound fixed byte builds."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from .asset_schema import fields, label, number
from .assets import checked_path, hash_stream, identity, digest
from .history import init_history, register_build
from .script_schema import canonical_bytes, load_script_json

MAX_SOURCE=8*1024**3
MAX_STORE=8*1024**2


def identifier(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}|[0-9a-f]{64}',value):
        raise ValueError('invalid content identifier')
    return value


def write_json(path,value,*,max_bytes=MAX_STORE):
    """Replace only an owned metadata file; never a game or user-selected output."""
    path=checked_path(Path(path))
    if path.name=='project.json' and type(value) is dict and value.get('format')=='romancer-workbench-v2':
        value=json.loads(canonical_bytes(value,max_bytes=max_bytes))
        for row in value.get('sources',[])+value.get('builds',[]):
            candidate=Path(row['path'])
            if candidate.is_absolute():row['path']=candidate.relative_to(path.parent).as_posix()
    raw=canonical_bytes(value,max_bytes=max_bytes)
    fd,name=tempfile.mkstemp(prefix='.metadata-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_project(project):
    project=checked_path(Path(project))
    value=load_script_json(project/'project.json',max_bytes=MAX_STORE)
    if type(value) is not dict or value.get('format') not in ('romancer-workbench-v1','romancer-workbench-v2'):raise ValueError('not a ROMancer workbench project')
    identifier(value['project_id'])
    if project.name!=value['project_id']:raise ValueError('project identity differs from directory')
    if value['format']=='romancer-workbench-v2':
        for row in value.get('sources',[])+value.get('builds',[]):
            stored=row['path']
            if type(stored) is not str or '\\' in stored or ':' in stored or stored.startswith('/') or '..' in stored.split('/'):raise ValueError('unsafe relative project path')
            path=checked_path(project/stored)
            if path.parent not in (project/'sources',project/'builds'):raise ValueError('artifact path escapes project')
            row['path']=str(path)
    return value


@contextmanager
def locked(project):
    project=checked_path(Path(project));lock=project/'.workbench-lock'
    try:lock.mkdir()
    except FileExistsError:raise ValueError('project is busy; retry after the current operation') from None
    import socket
    owner={'pid':os.getpid(),'session':uuid.uuid4().hex,'host':socket.gethostname()}
    try:
        write_json(lock/'owner.json',owner)
        yield read_project(project)
    finally:
        current=load_script_json(lock/'owner.json',max_bytes=4096)
        if current!=owner:raise ValueError('project lock owner changed')
        (lock/'owner.json').unlink();lock.rmdir()


def create_project(root:Path,name:str)->dict:
    label(name,120);root=checked_path(Path(root));root.mkdir(parents=True,exist_ok=True)
    project=root/uuid.uuid4().hex;project.mkdir()
    for folder in ('sources','builds','plans','reports','exports','sessions'): (project/folder).mkdir()
    value={'format':'romancer-workbench-v2','schema_version':2,'project_id':project.name,'name':name,
           'sources':[],'builds':[],'demo':False}
    write_json(project/'project.json',value);init_history(project)
    from .capture_store import init_capture_store
    init_capture_store(project)
    return {**value,'ok':True,'path':str(project),'status':'CREATED'}


def list_projects(root:Path)->list[dict]:
    root=checked_path(Path(root))
    if not root.exists():return []
    result=[]
    for path in sorted(root.iterdir()):
        if not re.fullmatch('[0-9a-f]{32}',path.name):continue
        try:value=read_project(path)
        except (ValueError,OSError):continue
        result.append({**value,'path':str(path)})
        if len(result)>=512:break
    return result


def _measure(path,expected=None,*,cancelled=lambda:False):
    path=checked_path(Path(path));before=path.stat()
    if not path.is_file() or before.st_nlink!=1 or before.st_size>MAX_SOURCE:raise ValueError('input must be an ordinary file within the 8 GiB budget')
    with path.open('rb') as stream:
        if identity(os.fstat(stream.fileno()))!=identity(before):raise ValueError('input changed before reading')
        hasher=hashlib.sha256()
        while chunk:=stream.read(65536):
            if cancelled():raise KeyboardInterrupt
            hasher.update(chunk)
        if cancelled():raise KeyboardInterrupt
        sha=hasher.hexdigest()
        if identity(os.fstat(stream.fileno()))!=identity(before):raise ValueError('input changed while reading')
    if identity(path.stat())!=identity(before):raise ValueError('input changed after reading')
    result={'sha256':sha,'size':before.st_size}
    if expected is not None and any(result[k]!=expected[k] for k in result):raise ValueError('source revision changed; import the new revision')
    return result


def _publish_copy(source,destination,expected,edits=(),*,cancelled=lambda:False):
    source=checked_path(Path(source));destination=checked_path(Path(destination))
    if destination.exists():raise ValueError('output already exists')
    _measure(source,expected,cancelled=cancelled)
    if shutil.disk_usage(destination.parent).free<expected['size']+1024*1024:raise ValueError('insufficient space for a separate verified output')
    fd,name=tempfile.mkstemp(prefix='.build-',dir=destination.parent);temporary=Path(name)
    try:
        sha=hashlib.sha256()
        with source.open('rb') as incoming,os.fdopen(fd,'w+b') as outgoing:
            while chunk:=incoming.read(65536):
                if cancelled():raise KeyboardInterrupt
                outgoing.write(chunk)
            for edit in edits:
                outgoing.seek(edit['offset']);before=bytes.fromhex(edit['before']);after=bytes.fromhex(edit['after'])
                if outgoing.read(len(before))!=before:raise ValueError('old-byte precondition failed')
                outgoing.seek(edit['offset']);outgoing.write(after)
            outgoing.flush();os.fsync(outgoing.fileno());outgoing.seek(0)
            # Independent stream comparison: every byte, including all unrelated bytes.
            incoming.seek(0);offset=0
            while original:=incoming.read(65536):
                if cancelled():raise KeyboardInterrupt
                actual=outgoing.read(len(original));wanted=bytearray(original)
                for edit in edits:
                    start=max(offset,edit['offset']);end=min(offset+len(original),edit['offset']+len(bytes.fromhex(edit['after'])))
                    if start<end:wanted[start-offset:end-offset]=bytes.fromhex(edit['after'])[start-edit['offset']:end-edit['offset']]
                if actual!=wanted:raise ValueError('independent output verification failed')
                sha.update(actual);offset+=len(actual)
            if outgoing.read(1):raise ValueError('unexpected output extension')
        _measure(source,expected,cancelled=cancelled)
        if cancelled():raise KeyboardInterrupt
        os.link(temporary,destination)
        return {'sha256':sha.hexdigest(),'size':expected['size']}
    finally:temporary.unlink(missing_ok=True)


def register_source(project:Path,source:Path,system:str|None,*,cancelled=lambda:False)->dict:
    project=Path(project);source=checked_path(Path(source))
    if system not in (None,'Unknown','NES','SNES','Genesis','Game Boy','Sega CD','GBA'):raise ValueError('unsupported console label')
    with locked(project) as value:
        if len(value['sources'])>=512:raise ValueError('project source limit reached')
        measured=_measure(source,cancelled=cancelled);artifact_id=uuid.uuid4().hex
        destination=project/'sources'/(artifact_id+source.suffix[:16])
        measured=_publish_copy(source,destination,measured,cancelled=cancelled)
        from .system_identify import identify_system
        from .system_registry import get_system
        assessment=identify_system(destination,expected_sha256=measured['sha256'],cancelled=cancelled)
        system_id=assessment.get('system_id')
        detected_label=get_system(system_id)['label'] if system_id is not None else 'Unknown'
        detected={'system':detected_label,'sha256':measured['sha256'],'size_bytes':measured['size'],
            'format':(assessment.get('container') or {}).get('format'),'notes':assessment.get('warnings',[])}
        registered=register_build(project,{'inputs':[{'role':'original','path':str(destination.absolute())}],
            'output':str(destination.absolute()),'adapter':{'name':'imported-revision','version':'1'},
            'profile':{'name':'identity-only','version':'1'},'settings':{}},project)
        record={'artifact_id':artifact_id,'name':source.name,'path':str(destination.absolute()),'build_id':registered['build_id'],**measured,
                'system':system or detected_label,'kind':'source','identification':detected,
                'system_id':system_id,'system_assessment':assessment}
        value['sources'].append(record);write_json(project/'project.json',value)
        return {**record,'ok':True,'status':'IMPORTED','original_preserved':True}


def assess_artifact(record,cancelled=lambda:False):
    from .system_identify import identify_system
    from .system_registry import get_system
    assessment=identify_system(Path(record['path']),expected_sha256=record['sha256'],cancelled=cancelled)
    record['system_id']=assessment.get('system_id');record['system_assessment']=assessment
    record['system']=get_system(record['system_id'])['label'] if record['system_id'] else 'Unknown'
    return record


def artifact(project,artifact_id):
    identifier(artifact_id);value=read_project(project)
    for row in value['sources']+value['builds']:
        if row['artifact_id']==artifact_id:
            path=checked_path(Path(row['path']))
            if path.parent not in (Path(project).absolute()/'sources',Path(project).absolute()/'builds'):
                raise ValueError('artifact path escapes project storage')
            return row
    raise ValueError('artifact is not in the selected project')


def inspect_resource(project:Path,artifact_id:str,offset:int,length:int)->dict:
    row=artifact(project,artifact_id);number(offset,0,row['size']);number(length,1,4096)
    _measure(row['path'],row)
    with Path(row['path']).open('rb') as stream:stream.seek(offset);raw=stream.read(min(length,row['size']-offset))
    return {'ok':True,'status':'INSPECTED','artifact_id':artifact_id,'sha256':row['sha256'],'size':row['size'],
            'offset':offset,'length':len(raw),'hex':raw.hex(),'text':''.join(chr(b) if 32<=b<127 else '·' for b in raw)}


def plan_byte_edits(project:Path,artifact_id:str,edits:list[dict])->dict:
    project=Path(project)
    with locked(project):
        row=artifact(project,artifact_id);_measure(row['path'],row)
        edits=json.loads(canonical_bytes(edits,max_bytes=1024*1024))
        if type(edits) is not list or not 1<=len(edits)<=1024:raise ValueError('provide 1..1024 edits')
        end=-1;total=0
        for edit in sorted(edits,key=lambda e:e.get('offset',-1)):
            fields(edit,'offset before after');number(edit['offset'],0,row['size'])
            for key in ('before','after'):
                if type(edit[key]) is not str or not re.fullmatch('(?:[0-9a-f]{2}){1,4096}',edit[key]):raise ValueError('provide 1..4096 bytes as lowercase hex')
            if len(edit['before'])!=len(edit['after']) or edit['before']==edit['after']:raise ValueError('fixed edit must change bytes without resizing')
            if edit['offset']<end:raise ValueError('overlapping byte edits')
            end=edit['offset']+len(bytes.fromhex(edit['before']));total+=len(edit['before'])//2
            if end>row['size'] or total>65536:raise ValueError('edit range or aggregate budget exceeded')
            with Path(row['path']).open('rb') as stream:
                stream.seek(edit['offset'])
                if stream.read(len(edit['before'])//2).hex()!=edit['before']:raise ValueError('old-byte precondition failed')
        plan={'schema_version':1,'operation':'byte-build','source_id':artifact_id,'source_sha256':row['sha256'],
              'source_size':row['size'],'edits':sorted(edits,key=lambda e:e['offset']),
              'integrity':'Generic byte edit; console checksums and game semantics have not been verified.'}
        plan_id=digest(plan);plan['plan_id']=plan_id;path=project/'plans'/(plan_id+'.json')
        if not path.exists():write_json(path,plan)
        return {**plan,'ok':True,'status':'PLANNED','changed_bytes':total}


def apply_build(project:Path,plan_id:str,*,cancelled=lambda:False)->dict:
    project=Path(project);identifier(plan_id)
    with locked(project) as value:
        plan=load_script_json(project/'plans'/(plan_id+'.json'),max_bytes=MAX_STORE)
        if plan.pop('plan_id',None)!=plan_id or digest(plan)!=plan_id:raise ValueError('plan identity mismatch')
        row=artifact(project,plan['source_id'])
        if row['sha256']!=plan['source_sha256'] or row['size']!=plan['source_size']:raise ValueError('stale plan')
        destination=project/'builds'/(plan_id+Path(row['path']).suffix)
        measured=_publish_copy(row['path'],destination,row,plan['edits'],cancelled=cancelled)
        registered=register_build(project,{'inputs':[{'role':'original','path':row['path']}],
            'output':str(destination.absolute()),'adapter':{'name':'generic-fixed-bytes','version':'1'},
            'profile':{'name':'explicit-byte-plan','version':'1'},'settings':{'plan_id':plan_id}},project)
        record={'artifact_id':uuid.uuid4().hex,'name':'Build '+str(len(value['builds'])+1),'kind':'build',
                'path':str(destination.absolute()),'system':row['system'],**measured,
                'source_id':row['artifact_id'],'plan_id':plan_id,'build_id':registered['build_id']}
        if 'container_parent' in row:record['container_parent']=row['container_parent']
        assess_artifact(record,cancelled)
        value['builds'].append(record);write_json(project/'project.json',value)
        return {**record,'ok':True,'status':'BUILT','original_preserved':True,'independent_byte_check':True,
                'integrity':plan['integrity']}
