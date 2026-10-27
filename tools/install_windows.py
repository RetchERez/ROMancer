"""Verified per-user installation. Versions and user projects are preserved."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid


def safe_name(name):
    if type(name) is not str or not name or len(name)>256 or '\\' in name or ':' in name or name.startswith('/') or any(p in ('','.','..') or p.rstrip(' .')!=p or p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(10)],*[f'LPT{i}' for i in range(10)]} for p in name.split('/')):raise ValueError('unsafe bundle member')
    return name


def _ordinary(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        if part.is_symlink() or part.is_junction():raise ValueError('linked installation paths are not supported')
    if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('bundle member must be an ordinary single-link file')
    return path


def _hash(path):
    path=_ordinary(path);before=path.stat();digest=hashlib.sha256();count=0
    with path.open('rb') as stream:
        while chunk:=stream.read(65536):digest.update(chunk);count+=len(chunk)
    after=path.stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or count!=before.st_size:raise ValueError('bundle member changed')
    return {'size':count,'sha256':digest.hexdigest()}


def verify_tree(root):
    root=Path(root).absolute();manifest_path=_ordinary(root/'BUNDLE.json')
    if manifest_path.stat().st_size>4*1024**2:raise ValueError('bundle manifest too large')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if type(manifest) is not dict or manifest.get('schema_version')!=1 or manifest.get('product')!='ROMancer' or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[.a-z0-9-]*)',manifest.get('version','')):raise ValueError('invalid bundle manifest')
    rows=manifest.get('files');names=set();expected={'BUNDLE.json'};total=0
    if type(rows) is not list or not 1<=len(rows)<=8192:raise ValueError('invalid bundle inventory')
    for row in rows:
        if type(row) is not dict or set(row)!={'path','size','sha256'}:raise ValueError('invalid bundle member record')
        name=safe_name(row['path'])
        if name.casefold() in names or name.casefold()=='bundle.json':raise ValueError('duplicate bundle member')
        names.add(name.casefold());expected.add(name)
        if type(row['size']) is not int or not 0<=row['size']<=384*1024**2:raise ValueError('bundle member exceeds budget')
        measured=_hash(root/name)
        if measured!={k:row[k] for k in ('size','sha256')}:raise ValueError('bundle member identity mismatch: '+name)
        total+=row['size']
    if total>1024*1024**2:raise ValueError('bundle aggregate budget exceeded')
    actual=set()
    for path in root.rglob('*'):
        if path.is_symlink() or path.is_junction():raise ValueError('linked bundle directory/member')
        if path.is_file():actual.add(path.relative_to(root).as_posix())
    if actual!=expected:raise ValueError('unlisted or missing bundle members')
    return {'ok':True,'manifest':manifest,'manifest_sha256':_hash(manifest_path)['sha256']}


def _atomic(path,data):
    fd,name=tempfile.mkstemp(prefix='.install-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


ROOT_LAUNCHER='''param([switch]$NoBrowser,[switch]$Check,[string]$Workspace='')
$ErrorActionPreference='Stop'
$romancerActive=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'active.json') -Raw | ConvertFrom-Json
if ($romancerActive.version -notmatch '^[0-9]+[.][0-9]+[.][0-9]+[.a-z0-9-]*$') { throw 'Invalid installed version' }
$romancerLauncher=Join-Path $PSScriptRoot ('versions\\'+$romancerActive.version+'\\Open ROMancer.ps1')
if (-not $Workspace) { $Workspace=Join-Path $PSScriptRoot 'workspace' }
& $romancerLauncher -Workspace $Workspace -NoBrowser:$NoBrowser -Check:$Check
'''


def install(payload,destination):
    payload=Path(payload).absolute();destination=Path(destination).absolute();verified=verify_tree(payload);version=verified['manifest']['version']
    if payload==destination or payload in destination.parents or destination in payload.parents:raise ValueError('installation must be separate from payload')
    for part in (destination,*destination.parents):
        if part.is_symlink() or part.is_junction():raise ValueError('linked installation directory')
    destination.mkdir(parents=True,exist_ok=True);versions=destination/'versions';versions.mkdir(exist_ok=True)
    target=versions/version
    if target.exists():
        if verify_tree(target)['manifest_sha256']!=verified['manifest_sha256']:raise ValueError('installed version differs; preserve it and use a new version')
    else:
        with tempfile.TemporaryDirectory(prefix='.install-',dir=versions) as temp:
            stage=Path(temp)/'payload';stage.mkdir()
            for row in verified['manifest']['files']:
                source=payload/row['path'];output=stage/row['path'];output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,output)
            shutil.copyfile(payload/'BUNDLE.json',stage/'BUNDLE.json');verify_tree(stage);verify_tree(payload)
            from romancer.patch_sets import _publish_directory
            _publish_directory(stage,target)
    active_path=destination/'active.json';previous=json.loads(active_path.read_text()) if active_path.exists() else None
    legacy=None;launcher=destination/'Open ROMancer.ps1'
    if previous is None and launcher.exists():
        legacy='Open ROMancer-before-v60-'+uuid.uuid4().hex+'.ps1';shutil.copyfile(_ordinary(launcher),destination/legacy)
    active={'schema_version':1,'version':version,'manifest_sha256':verified['manifest_sha256'],'previous':previous if previous and previous.get('version')!=version else (previous or {}).get('previous'),'legacy_launcher':legacy or (previous or {}).get('legacy_launcher')}
    # Existing versions/workspaces remain intact; switching the small pointer is reversible.
    _atomic(active_path,(json.dumps(active,indent=2)+'\n').encode());_atomic(launcher,ROOT_LAUNCHER.encode())
    return {'ok':True,'status':'INSTALLED','version':version,'root':str(destination),'workspace':str(destination/'workspace')}


def rollback(destination):
    destination=Path(destination).absolute();active=json.loads((destination/'active.json').read_text())
    if active.get('previous'):
        previous=active['previous'];verified=verify_tree(destination/'versions'/previous['version'])
        if verified['manifest_sha256']!=previous['manifest_sha256']:raise ValueError('previous version changed')
        _atomic(destination/'active.json',(json.dumps(previous,indent=2)+'\n').encode())
    elif active.get('legacy_launcher'):
        legacy=_ordinary(destination/safe_name(active['legacy_launcher']))
        connection=destination/'workspace/connection.json'
        if connection.exists():
            _ordinary(connection);os.rename(connection,connection.parent/('connection-before-rollback-'+uuid.uuid4().hex+'.json'))
        _atomic(destination/'Open ROMancer.ps1',legacy.read_bytes());(destination/'active.json').unlink()
    else:raise ValueError('no previous installation recorded')
    return {'ok':True,'status':'ROLLED_BACK','projects_preserved':True}


def uninstall(destination):
    destination=Path(destination).absolute()
    # Deactivate only. Keeping version folders gives recovery without deleting projects.
    active=destination/'active.json'
    if active.exists():
        _atomic(destination/'last-active.json',active.read_bytes());active.unlink()
        launcher=destination/'Open ROMancer.ps1'
        if launcher.exists() and launcher.read_text()==ROOT_LAUNCHER:launcher.unlink()
    return {'ok':True,'status':'DEACTIVATED','projects_preserved':True,'version_folders_preserved':True}


def desktop_shortcut(destination):
    if os.name!='nt':raise ValueError('desktop entry requires Windows')
    # Pass paths as environment data, never as interpolated PowerShell source.
    env=os.environ.copy();env['ROMANCER_INSTALL_ROOT']=str(destination)
    script="$w=New-Object -ComObject WScript.Shell;$p=Join-Path ($w.SpecialFolders.Item('Desktop')) 'ROMancer.lnk';$s=$w.CreateShortcut($p);$s.TargetPath=Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe';$s.Arguments='-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File '+[char]34+(Join-Path $env:ROMANCER_INSTALL_ROOT 'Open ROMancer.ps1')+[char]34;$s.WorkingDirectory=$env:ROMANCER_INSTALL_ROOT;$s.WindowStyle=7;$a=Get-Content -LiteralPath (Join-Path $env:ROMANCER_INSTALL_ROOT 'active.json') -Raw|ConvertFrom-Json;$s.IconLocation=(Join-Path $env:ROMANCER_INSTALL_ROOT ('versions\\'+$a.version+'\\ROMancer.ico'));$s.Description='ROMancer — By RetchEWretched';$s.Save()"
    subprocess.run(['powershell.exe','-NoProfile','-WindowStyle','Hidden','-Command',script],env=env,check=True,creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--payload',type=Path);parser.add_argument('--install-root',type=Path,default=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'ROMancer');parser.add_argument('--desktop',action='store_true');parser.add_argument('--launch',action='store_true');parser.add_argument('--rollback',action='store_true');parser.add_argument('--uninstall',action='store_true');args=parser.parse_args()
    if args.rollback:result=rollback(args.install_root)
    elif args.uninstall:result=uninstall(args.install_root)
    else:
        if args.payload is None:parser.error('--payload required')
        result=install(args.payload,args.install_root)
        if args.desktop:desktop_shortcut(args.install_root)
    print(json.dumps(result))
    if args.launch:
        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',str(args.install_root/'Open ROMancer.ps1')],creationflags=subprocess.CREATE_NO_WINDOW)


if __name__=='__main__':main()
