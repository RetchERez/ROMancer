"""Positive patch-only CUE releases and verified complete-set reconstruction."""
import ctypes

import json
import os
from pathlib import Path

import tempfile
import zipfile
import errno
from .assets import checked_path
from .container_workspace import parse_cue
from .streaming_bps import create_patch,apply_patch,_scan,_recheck,_cancel,_destination,_space,MAX_PATCH,CHUNK


def _name(name):
    if type(name) is not str or not name or len(name)>256 or '\\' in name or ':' in name or name.startswith('/') or any(p in ('','.','..') for p in name.split('/')):raise ValueError('unsafe patch set member name')
    return name


def _members(cue):
    parsed=parse_cue(cue)
    return parsed,[{'path':row['name'],**{k:row[k] for k in ('size','sha256')}} for row in parsed['members']]


class DirectoryPublicationUnavailable(ValueError):pass


def _publish_directory(source,target):
    if target.exists():raise ValueError('output directory already exists')
    if os.name=='nt':
        import time
        source=checked_path(Path(source));target=checked_path(Path(target));owned=source.stat()
        for attempt in range(6):
            if target.exists():raise ValueError('output directory already exists')
            checked_path(source);checked_path(target)
            if not os.path.samestat(owned,source.stat()):raise ValueError('staged directory identity changed')
            try:os.rename(source,target);return
            except PermissionError as error:
                if getattr(error,'winerror',None) not in (5,32,33) or attempt==5:raise
                # Scanners can briefly hold a just-verified restore tree open.
                # Retry the same no-replace operation; never copy or overwrite.
                time.sleep(.05*(2**attempt))
        return
    library=ctypes.CDLL(None,use_errno=True)
    if not hasattr(library,'renameat2'):raise DirectoryPublicationUnavailable('atomic no-replace directory publication unavailable on this host')
    rename=library.renameat2;rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];rename.restype=ctypes.c_int
    if rename(-100,os.fsencode(source),-100,os.fsencode(target),1)!=0:
        error=ctypes.get_errno()
        if error in (errno.EINVAL,errno.ENOSYS,errno.EOPNOTSUPP):raise DirectoryPublicationUnavailable('This host/filesystem lacks atomic no-replace directory publication. Use Windows or a supported Linux filesystem.')
        raise OSError(error,'cannot publish complete output directory')


def create_patch_set(source_cue,target_cue,destination,title,*,cancelled=lambda:False):
    source_cue=checked_path(Path(source_cue));target_cue=checked_path(Path(target_cue));destination=_destination(destination,(source_cue,target_cue))
    from .asset_schema import label
    label(title,256);left,originals=_members(source_cue);right,targets=_members(target_cue)
    if left['cue']!=right['cue'] or left['tracks']!=right['tracks'] or [r['path'] for r in originals]!=[r['path'] for r in targets]:raise ValueError('patch sets require matching CUE relationships and member names')
    _space(destination.parent,sum(r['size'] for r in targets)*3)
    with tempfile.TemporaryDirectory(prefix='.patchset-',dir=destination.parent) as temp:
        temp=Path(temp);files=[];patches=[]
        for index,(a,b) in enumerate(zip(originals,targets)):
            _cancel(cancelled);name=_name(a['path']);src=source_cue.parent/name;tgt=target_cue.parent/name
            row={'path':name,'source':{k:a[k] for k in ('size','sha256')},'target':{k:b[k] for k in ('size','sha256')},'patch':None}
            if row['source']!=row['target']:
                patch_name=f'patches/{index:03d}.bps';patch=temp/f'{index:03d}.bps';result=create_patch(src,tgt,patch,{'title':title},cancelled=cancelled)
                row['patch']={'path':patch_name,'size':result['size'],'sha256':result['sha256']};patches.append((patch_name,patch))
            files.append(row)
        manifest={'schema_version':1,'format':'ROMancer-CUE-BPS1','title':title,'credit':'By RetchEWretched','cue':left['cue'],'tracks':left['tracks'],'files':files}
        raw=json.dumps(manifest,sort_keys=True,ensure_ascii=True,indent=2).encode();archive=temp/'release.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            z.writestr('PATCHSET.json',raw);z.writestr('README.txt','By RetchEWretched\n\nApply this patch set to the complete original CUE set using ROMancer. Every original member SHA-256 must match PATCHSET.json. Keep original files unchanged.\n')
            for name,path in patches:_cancel(cancelled);z.write(path,name)
        # Exercise the complete independent installer before exposing the release.
        apply_patch_set(source_cue,archive,temp/'verified',cancelled=cancelled)
        # Reparse/re-hash both real sets, rather than trusting the earlier inventory.
        if _members(source_cue)[0]!=left or _members(target_cue)[0]!=right:raise ValueError('disc dependencies changed')
        for row in files:
            for parent,key in [(source_cue.parent,'source'),(target_cue.parent,'target')]:
                current=_scan(parent/row['path'],cancelled=cancelled)
                if any(current[k]!=row[key][k] for k in ('size','sha256')):raise ValueError('disc member changed before publication')
        measured=_scan(archive,16*1024**3,cancelled=cancelled);_cancel(cancelled);os.link(archive,destination)
    return {'ok':True,'status':'VERIFIED','format':'ROMancer-CUE-BPS1','path':str(destination),'size':measured['size'],'sha256':measured['sha256'],'manifest':manifest}


def apply_patch_set(source_cue,archive,destination,*,cancelled=lambda:False):
    source_cue=checked_path(Path(source_cue));archive=checked_path(Path(archive));destination=_destination(destination,(source_cue,archive))
    encoded=_scan(archive,16*1024**3,cancelled=cancelled);parsed,originals=_members(source_cue)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();names=[_name(i.filename) for i in infos]
        if len(names)>515 or len({n.casefold() for n in names})!=len(names) or any(i.is_dir() or i.file_size>MAX_PATCH or (i.external_attr>>16)&0o170000==0o120000 for i in infos):raise ValueError('invalid patch set ZIP inventory')
        if 'PATCHSET.json' not in names or z.getinfo('PATCHSET.json').file_size>1024**2:raise ValueError('missing or oversized patch set manifest')
        manifest=json.loads(z.read('PATCHSET.json'))
        if type(manifest) is not dict or set(manifest)!={'schema_version','format','title','credit','cue','tracks','files'} or manifest['schema_version']!=1 or manifest['format']!='ROMancer-CUE-BPS1':raise ValueError('invalid patch set manifest')
        if manifest['cue']!=parsed['cue'] or manifest['tracks']!=parsed['tracks']:raise ValueError('original CUE relationships differ')
        rows=manifest['files']
        if type(rows) is not list or len(rows)!=len(originals):raise ValueError('incomplete patch set')
        expected={'PATCHSET.json','README.txt'};total=0
        for row,original in zip(rows,originals):
            if type(row) is not dict or set(row)!={'path','source','target','patch'} or _name(row['path'])!=original['path']:raise ValueError('patch set member mismatch')
            for key in ('source','target'):
                value=row[key]
                if type(value) is not dict or set(value)!={'size','sha256'} or type(value['size']) is not int or not 0<=value['size']<=8*1024**3 or type(value['sha256']) is not str or len(value['sha256'])!=64:raise ValueError('invalid member identity')
            if any(row['source'][k]!=original[k] for k in ('size','sha256')):raise ValueError('original disc member revision mismatch')
            total+=row['target']['size'];patch=row['patch']
            if patch is None:
                if row['source']!=row['target']:raise ValueError('changed member requires a patch')
            else:
                if type(patch) is not dict or set(patch)!={'path','size','sha256'}:raise ValueError('invalid patch identity')
                name=_name(patch['path'])
                if not name.startswith('patches/') or not name.endswith('.bps') or name in expected:raise ValueError('invalid or duplicate patch name')
                expected.add(name)
                if name not in names or z.getinfo(name).file_size!=patch['size']:raise ValueError('missing or changed patch')
        if set(names)!=expected or total>8*1024**3:raise ValueError('unapproved patch set members or aggregate budget exceeded')
        _space(destination.parent,total*2)
        with tempfile.TemporaryDirectory(prefix='.patchset-apply-',dir=destination.parent) as temp:
            temp=Path(temp);stage=temp/'output';stage.mkdir()
            for index,row in enumerate(rows):
                _cancel(cancelled);source=source_cue.parent/row['path'];target=stage/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
                if row['patch'] is None:
                    with source.open('rb',buffering=0) as src,target.open('xb',buffering=0) as out:
                        while chunk:=src.read(CHUNK):_cancel(cancelled);out.write(chunk)
                else:
                    patch=temp/f'{index:03d}.bps'
                    with z.open(row['patch']['path']) as src,patch.open('xb') as out:
                        while chunk:=src.read(CHUNK):_cancel(cancelled);out.write(chunk)
                    actual=_scan(patch,MAX_PATCH,cancelled=cancelled)
                    if any(actual[k]!=row['patch'][k] for k in ('size','sha256')):raise ValueError('patch identity mismatch')
                    apply_patch(source,patch,target,cancelled=cancelled)
                actual=_scan(target,cancelled=cancelled)
                if any(actual[k]!=row['target'][k] for k in ('size','sha256')):raise ValueError('reconstructed member identity mismatch')
            actual=parse_cue(stage/manifest['cue'])
            if actual['tracks']!=manifest['tracks']:raise ValueError('reconstructed CUE relationships mismatch')
            for row in rows:
                current=_scan(source_cue.parent/row['path'],cancelled=cancelled)
                if any(current[k]!=row['source'][k] for k in ('size','sha256')):raise ValueError('original set changed during application')
            _recheck(archive,encoded,16*1024**3,cancelled=cancelled);_cancel(cancelled);_publish_directory(stage,destination)
    return {'ok':True,'status':'VERIFIED','path':str(destination),'cue':manifest['cue'],'members':len(rows),'complete_set_verified':True}
