"""Explicit private project migration, verified backup/restore and dead-lock recovery."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import socket
import sqlite3
import tempfile
import uuid
import zipfile
from .assets import checked_path
from .script_schema import load_script_json,canonical_bytes
from . import workbench_projects as p

ROLES={'sources','builds','reports','sessions','captures'}
MAX_SET=16*1024**3


def migrate_project(project):
    project=checked_path(project)
    with p.locked(project) as value:
        if value['format']=='romancer-workbench-v2':return {'ok':True,'status':'CURRENT'}
        backup=project/'project.v1.backup.json'
        if backup.exists():raise ValueError('migration backup already exists; inspect recovery first')
        for row in value['sources']+value['builds']:p._measure(row['path'],row)
        with backup.open('xb') as out:out.write((project/'project.json').read_bytes())
        value.update(format='romancer-workbench-v2',schema_version=2)
        p.write_json(project/'project.json',value)
    return {'ok':True,'status':'MIGRATED','backup':str(backup)}


def _member(name):
    if type(name) is not str or not name or '\\' in name or ':' in name or name.startswith('/') or any(x in ('','.','..') for x in name.split('/')):raise ValueError('unsafe backup member')
    return PurePosixPath(name)


def backup_project(project,destination,roles):
    project=checked_path(project);destination=checked_path(destination)
    if type(roles) is not list or not roles or set(roles)-ROLES or len(roles)!=len(set(roles)):raise ValueError('choose private backup roles')
    if destination.exists() or destination.is_relative_to(project):raise ValueError('choose a new backup path outside the project')
    with p.locked(project) as value:
        files=[];total=0
        from .workbench_files import list_inputs
        input_roles={r['path']:('sessions' if r['kind']=='save' else 'sources') for r in list_inputs(project)}
        for path in sorted(project.rglob('*')):
            rel=path.relative_to(project);first=rel.parts[0]
            checked_path(path)
            if path.is_dir():continue
            if first.startswith('.workbench-lock') or path.name in ('operation.lock',) or path.name.startswith(('.metadata-','.build-')):continue
            included=first in roles or first in ('plans','drafts','containers','routes','catalog') or rel.as_posix()=='project.json'
            included|=rel.as_posix() in ('inputs.json','bookmarks.json','build-notes.json')
            included|=first=='inputs' and input_roles.get(rel.as_posix()) in roles
            included|=first=='saves' and 'sessions' in roles
            # Scenes & colors: recorded scenes, their replay savestates and the pending change list.
            # renders/ (preview pictures) and work/ (patched copies for replays) are rebuilt on demand.
            included|=first=='trace-scenes' and 'sessions' in roles and not (len(rel.parts)>2 and rel.parts[2] in ('renders','work'))
            included|=first=='patch-previews' and 'builds' in roles
            included|=first=='.romancer-history' and 'builds' in roles
            included|=first=='.romancer-evidence' and 'captures' in roles
            included|=first in ('.evidence-key','.historical-evidence','exports','exports.json') and 'reports' in roles
            if not included:continue
            measure=p._measure(path);total+=measure['size']
            if total>MAX_SET or len(files)>=8192:raise ValueError('private backup budget exceeded')
            files.append((path,rel.as_posix(),measure))
        if shutil.disk_usage(destination.parent).free<total+1024**2:raise ValueError('insufficient backup space')
        fd,name=tempfile.mkstemp(prefix='.backup-',dir=destination.parent);os.close(fd)
        try:
            manifest={'format':'romancer-private-backup-v1','project_id':value['project_id'],'origin_root':str(project),'roles':roles,'members':[]}
            with zipfile.ZipFile(name,'w',zipfile.ZIP_STORED,allowZip64=True) as archive:
                for path,rel,measure in files:
                    with path.open('rb') as source,archive.open(rel,'w',force_zip64=True) as target:shutil.copyfileobj(source,target,65536)
                    p._measure(path,measure);manifest['members'].append({'name':rel,**measure})
                archive.writestr('backup-manifest.json',canonical_bytes(manifest,max_bytes=4*1024**2))
            _verify_archive(Path(name))
            os.link(name,destination)
        finally:Path(name).unlink(missing_ok=True)
    return {'ok':True,'status':'BACKED_UP','path':str(destination),'roles':roles,'members':len(files),'private':True}


def _verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist();names=[i.filename for i in infos]
        if len(names)!=len(set(n.casefold() for n in names)) or len(names)>8193:raise ValueError('duplicate or excessive backup members')
        for name in names:_member(name)
        if 'backup-manifest.json' not in names:raise ValueError('missing private backup manifest')
        if archive.getinfo('backup-manifest.json').file_size>4*1024**2:raise ValueError('manifest exceeds budget')
        manifest=json.loads(archive.read('backup-manifest.json'));p.identifier(manifest['project_id'])
        if manifest.get('format')!='romancer-private-backup-v1':raise ValueError('not a ROMancer private backup')
        members=manifest['members']
        if set(names)!={m['name'] for m in members}|{'backup-manifest.json'}:raise ValueError('backup member set mismatch')
        if sum(i.file_size for i in infos)>MAX_SET:raise ValueError('backup too large')
        for member in members:
            info=archive.getinfo(member['name'])
            if info.file_size!=member['size'] or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('invalid backup member')
            sha=hashlib.sha256()
            with archive.open(info) as source:
                while chunk:=source.read(65536):sha.update(chunk)
            if sha.hexdigest()!=member['sha256']:raise ValueError('backup member hash mismatch')
        return manifest


def _rebind(project,origin,published_root=None):
    """Only mutable location records/owner markers change. Signed reports remain byte exact."""
    from . import history as h
    for store_name,db_name in (('.romancer-history','history.sqlite3'),('.romancer-evidence','captures.sqlite3')):
        store=project/store_name
        if not store.exists():continue
        marker=load_script_json(store/'owner.json',max_bytes=4096);p.identifier(marker['store_id'])
        if (store/'operation.lock').exists():raise ValueError('store recovery required')
        with closing(sqlite3.connect(store/db_name)) as connection:
            connection.execute('PRAGMA trusted_schema=OFF')
            if connection.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('backup database corrupt')
            if dict(connection.execute('SELECT key,value FROM store_meta'))['store_id']!=marker['store_id']:raise ValueError('backup store ownership mismatch')
            if store_name=='.romancer-history':
                h._schema_check(connection,marker)
                for (build_id,) in connection.execute('SELECT build_id FROM builds').fetchall():
                    record=h._load_build(connection,build_id)
                    locations=record['locations']
                    def relocated(raw):
                        # Origin may be a Windows path restored on Linux; normalize separators first.
                        raw=raw.replace('\\','/');prefix=origin.replace('\\','/').rstrip('/')+'/'
                        if not raw.startswith(prefix):return raw # external historical locations remain historical
                        rel=raw[len(prefix):];_member(rel);return str(checked_path((published_root or project)/rel))
                    locations['output']=relocated(locations['output'])
                    for item in locations['inputs']:item['path']=relocated(item['path'])
                    text,sha=h._record_text(record)
                    connection.execute('UPDATE builds SET record_json=?,record_sha256=? WHERE build_id=?',(text,sha,build_id))
            connection.commit()
        marker['directory_identity']=[store.stat().st_dev,store.stat().st_ino];p.write_json(store/'owner.json',marker)


def restore_project(archive,root):
    archive=checked_path(archive);manifest=_verify_archive(archive)
    if not {'sources','builds','reports','sessions','captures'}<=set(manifest['roles']):raise ValueError('restore requires a complete private backup')
    root=checked_path(root);root.mkdir(parents=True,exist_ok=True);destination=root/manifest['project_id']
    if destination.exists():raise ValueError('project already exists; choose another workspace')
    staging=Path(tempfile.mkdtemp(prefix='.restore-',dir=root));project=staging/destination.name;project.mkdir()
    try:
        if shutil.disk_usage(root).free<sum(m['size'] for m in manifest['members'])+1024**2:raise ValueError('insufficient restore space')
        with zipfile.ZipFile(archive) as z:
            names=[info.filename for info in z.infolist()]
            if len(names)!=len(set(name.casefold() for name in names)) or set(names)!={m['name'] for m in manifest['members']}|{'backup-manifest.json'}:raise ValueError('backup inventory changed before extraction')
            for member in manifest['members']:
                info=z.getinfo(member['name'])
                if info.file_size!=member['size'] or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('backup member changed before extraction')
                target=project/member['name'];target.parent.mkdir(parents=True,exist_ok=True);sha=hashlib.sha256();count=0
                with z.open(info) as source,target.open('xb') as out:
                    while chunk:=source.read(65536):
                        count+=len(chunk)
                        if count>member['size']:raise ValueError('extracted member exceeds manifest budget')
                        sha.update(chunk);out.write(chunk)
                if count!=member['size'] or sha.hexdigest()!=member['sha256']:raise ValueError('extracted backup member differs from verified manifest')
                p._measure(target,member)
        raw=load_script_json(project/'project.json',max_bytes=p.MAX_STORE)
        for row in raw['sources']+raw['builds']:
            old=row['path'].replace('\\','/');prefix=manifest['origin_root'].replace('\\','/').rstrip('/')+'/'
            if old.startswith(prefix):row['path']=old[len(prefix):]
        raw.update(format='romancer-workbench-v2',schema_version=2);p.write_json(project/'project.json',raw)
        for folder in ('sources','builds','plans','reports','exports','sessions'):(project/folder).mkdir(exist_ok=True)
        value=p.read_project(project)
        for row in value['sources']+value['builds']:p._measure(row['path'],row)
        # Finish trust/location changes while hidden, then publish one complete tree.
        from .workbench_evidence import quarantine_restored_evidence
        from .patch_sets import _publish_directory
        quarantine_restored_evidence(project)
        _rebind(project,manifest['origin_root'],destination)
        _publish_directory(project,destination)
        return {'ok':True,'status':'RESTORED','project_id':destination.name,'path':str(destination),'historical_evidence':True}
    finally:
        # Leave any failed staged data for inspection, never advertise it as a project.
        if not any(staging.iterdir()):staging.rmdir()


def recover_lock(project):
    project=checked_path(project);lock=project/'.workbench-lock';owner=load_script_json(checked_path(lock/'owner.json'),max_bytes=4096)
    if owner.get('host')!=socket.gethostname() or type(owner.get('pid')) is not int or owner['pid']<=0:raise ValueError('lock owner cannot be verified on this computer')
    p.identifier(owner['session']);pid=owner['pid']
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        handle=kernel.OpenProcess(0x1000,False,pid)
        if handle:kernel.CloseHandle(ctypes.c_void_p(handle));raise ValueError('project owner is still active')
        if ctypes.get_last_error()!=87:raise ValueError('cannot establish that owner has exited')
    else:
        try:os.kill(pid,0)
        except ProcessLookupError:pass
        except PermissionError:raise ValueError('lock owner liveness is unknown') from None
        else:raise ValueError('project owner is still active')
    if load_script_json(lock/'owner.json',max_bytes=4096)!=owner:raise ValueError('lock owner changed')
    backup=project/('.recovered-lock-'+uuid.uuid4().hex);os.rename(lock,backup)
    return {'ok':True,'status':'RECOVERED','backup':str(backup)}
