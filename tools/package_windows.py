"""Build a pinned Windows amd64 runtime plus the positive ROMancer source set."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.install_windows import safe_name,verify_tree

PINS={
    'python':{'file':'python-3.14.9-embed-amd64.zip','sha256':'3c01d7cfc666f746a6f064f60fb2156ab0ec464d3d738ab796371a46a9bb24a2','url':'https://www.python.org/ftp/python/3.14.9/python-3.14.9-embed-amd64.zip','version':'3.14.9','license':'PSF-2.0 and bundled notices'},
    'pillow':{'file':'pillow-12.3.0-cp314-cp314-win_amd64.whl','sha256':'fdafc9cce40277e0f7a0feabce0ee50dd2fa1800f3b38015e51296b5e814048d','url':'https://files.pythonhosted.org/packages/f1/e0/492879f69d94f91f60fc8cd05ba03650e9520afebb2fb7aa12777d7c7f38/pillow-12.3.0-cp314-cp314-win_amd64.whl','version':'12.3.0','license':'MIT-CMU and bundled notices'}
}


def runtime_members(archive,expected_sha256,kind):
    archive=Path(archive)
    if kind not in PINS or archive.stat().st_size>64*1024**2:raise ValueError('invalid runtime archive')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=expected_sha256:raise ValueError('runtime archive hash differs from pin')
    with zipfile.ZipFile(archive) as z:
        names=set();members=[];total=0
        for entry in z.infolist():
            name=safe_name(entry.filename)
            if entry.is_dir() or name.casefold() in names or entry.file_size>64*1024**2 or (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('invalid runtime member')
            if kind=='python' and '/' in name:raise ValueError('unexpected embedded Python subdirectory')
            if kind=='pillow' and not name.startswith(('PIL/','pillow-12.3.0.dist-info/')):raise ValueError('unexpected Pillow member')
            names.add(name.casefold());raw=z.read(entry);total+=len(raw)
            if total>128*1024**2:raise ValueError('runtime aggregate budget exceeded')
            members.append((name,raw))
        return members


LAUNCHER=r'''param([switch]$NoBrowser,[switch]$Check,[string]$Workspace='')
$ErrorActionPreference='Stop'
try {
    . (Join-Path $PSScriptRoot 'app\desktop_window.ps1')
    $romancerPython=Join-Path $PSScriptRoot 'python\\python.exe'
    if (-not $Workspace) { $Workspace=Join-Path $env:LOCALAPPDATA 'ROMancer\workspace' }
    $romancerProbe=& $romancerPython -I -B -c "import json,sys,PIL;from romancer import ROMANCER_VERSION,ROMANCER_RELEASE_NAME,ROMANCER_BUILD_LABEL;print(json.dumps(dict(product='ROMancer',version=ROMANCER_VERSION,python=sys.version.split()[0],pillow=PIL.__version__)))"
    if ($LASTEXITCODE -ne 0) { throw 'The bundled runtime failed its startup check.' }
    $romancerVersion=($romancerProbe|ConvertFrom-Json).version
    if ($Check) { Write-Output $romancerProbe;exit 0 }
    New-Item -ItemType Directory -Path $Workspace -Force|Out-Null
    $romancerConnection=Join-Path $Workspace 'connection.json'
    if (Test-Path -LiteralPath $romancerConnection) {
        try {
            $romancerOld=Get-Content -LiteralPath $romancerConnection -Raw|ConvertFrom-Json
            $romancerUri=[uri]$romancerOld.url
            if ($romancerUri.Host -eq '127.0.0.1' -and $romancerUri.Scheme -eq 'http') {
                $romancerCheck=Invoke-RestMethod -Uri ($romancerUri.GetLeftPart('Authority')+'/api/call') -Method Post -ContentType 'application/json' -Headers @{Authorization=('Bearer '+$romancerUri.Fragment.Replace('#token=',''))} -Body '{"operation":"system.capabilities","parameters":{}}' -TimeoutSec 2
                if ($romancerCheck.product -eq 'ROMancer' -and $romancerCheck.version -eq $romancerVersion) {
                    if (-not $NoBrowser) {Open-ROMancerWindow -Url $romancerOld.url -Workspace $Workspace};Write-Output 'ROMancer reopened.';exit 0
                }
            }
        } catch {}
    }
    $romancerArgs=@('-I','-B','-m','romancer.workbench_server','--workspace',('"'+$Workspace+'"'),'--no-browser')
    $romancerProcess=Start-Process -FilePath $romancerPython -ArgumentList $romancerArgs -WorkingDirectory (Join-Path $PSScriptRoot 'app') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Workspace 'server.log') -RedirectStandardError (Join-Path $Workspace 'server-errors.log')
    $romancerReady=$false;$romancerDeadline=[DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $romancerDeadline) {
        $romancerProcess.Refresh();if ($romancerProcess.HasExited) {break}
        if (Test-Path -LiteralPath $romancerConnection) {
            try {$romancerInfo=Get-Content -LiteralPath $romancerConnection -Raw|ConvertFrom-Json;if ($romancerInfo.pid -eq $romancerProcess.Id) {$romancerReady=$true;break}} catch {}
        }
        Start-Sleep -Milliseconds 150
    }
    if (-not $romancerReady) {if (-not $romancerProcess.HasExited) {Stop-Process -Id $romancerProcess.Id};throw ('ROMancer could not start. Details: '+(Join-Path $Workspace 'server-errors.log'))}
    if (-not $NoBrowser) {Open-ROMancerWindow -Url $romancerInfo.url -Workspace $Workspace}
    Write-Output 'ROMancer is ready — By RetchEWretched'
} catch {
    if (-not $NoBrowser) {Add-Type -AssemblyName System.Windows.Forms;[System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'ROMancer')|Out-Null}
    throw
}
'''


def generated_root_files(*,readme=None):
    
    files={}
    files['Open ROMancer.ps1']=LAUNCHER.encode('utf-8-sig')
    files['Open ROMancer.cmd']=b'@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0Open ROMancer.ps1"\r\n'
    files['Install ROMancer.cmd']=b'@echo off\r\n"%~dp0python\\python.exe" -I -B "%~dp0app\\tools\\install_windows.py" --payload "%~dp0." --desktop --launch\r\nif errorlevel 1 pause\r\n'
    files['Rollback ROMancer.cmd']=b'@echo off\r\n"%~dp0python\\python.exe" -I -B "%~dp0app\\tools\\install_windows.py" --rollback\r\nif errorlevel 1 pause\r\n'
    files['Uninstall ROMancer.cmd']=b'@echo off\r\n"%~dp0python\\python.exe" -I -B "%~dp0app\\tools\\install_windows.py" --uninstall\r\nif errorlevel 1 pause\r\n'
    if readme is None:
        base=Path(__file__).resolve().parents[1];candidate=base/'README.txt'
        readme=(candidate if candidate.exists() else base.parent/'README.txt').read_bytes()
    files['README.txt']=readme
    files['RUNTIME-ORIGINS.json']=(json.dumps(PINS,indent=2)+'\n').encode('utf-8')
    from PIL import Image,ImageDraw
    icon=Image.new('RGBA',(256,256),(20,34,40,255));draw=ImageDraw.Draw(icon);draw.rounded_rectangle((8,8,248,248),radius=48,outline=(112,212,180),width=8);draw.line([(76,192),(76,62),(146,62),(180,90),(180,116),(146,136),(76,136)],fill=(191,237,219),width=20);draw.line([(132,136),(186,194)],fill=(112,212,180),width=20);buffer=io.BytesIO();icon.save(buffer,format='ICO',sizes=[(16,16),(32,32),(48,48),(128,128),(256,256)])
    files['ROMancer.ico']=buffer.getvalue()
    return files


def build_bundle(app_root,downloads,destination,*,cores=None,observers=None):
    from tools.package_source import package
    from romancer import ROMANCER_VERSION,ROMANCER_RELEASE_NAME,ROMANCER_BUILD_LABEL
    app_root=Path(app_root).resolve();downloads=Path(downloads).resolve();destination=Path(destination).absolute()
    from romancer.bundled_cores import core_members,CORE_PINS
    engines=core_members(cores) if cores is not None else {}
    from romancer.bundled_debuggers import observer_files
    native=observer_files(observers) if observers is not None else {}
    if destination.exists():raise ValueError('bundle output already exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.windows-bundle-',dir=destination.parent) as temp:
        temp=Path(temp);stage=temp/'bundle';stage.mkdir();archive=temp/'source.zip';source=package(app_root,archive)
        with zipfile.ZipFile(archive) as z:
            for row in source['members']:
                if row['path']=='README.txt':continue
                path=stage/'app'/row['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(row['path']))
        for kind,pin in PINS.items():
            prefix=stage/'python' if kind=='python' else stage/'python/Lib/site-packages'
            for name,raw in runtime_members(downloads/pin['file'],pin['sha256'],kind):
                output=prefix/name;output.parent.mkdir(parents=True,exist_ok=True)
                if output.exists():raise ValueError('runtime/source collision')
                output.write_bytes(raw)
        (stage/'python/python314._pth').write_bytes(b'python314.zip\n.\nLib/site-packages\n../app\n')
        from tools.package_source import readme_path
        for name,raw in generated_root_files(readme=readme_path(app_root).read_bytes()).items():(stage/name).write_bytes(raw)
        if (app_root/'LICENSE').is_file():shutil.copyfile(app_root/'LICENSE',stage/'LICENSE')
        for name,raw in engines.items():
            target=stage/'cores'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        for name,path in native.items():
            target=stage/'debuggers'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        rows=[]
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
                rows.append({'path':path.relative_to(stage).as_posix(),'size':path.stat().st_size,'sha256':sha})
        manifest={'schema_version':1,'product':'ROMancer','version':ROMANCER_VERSION,'release_name':ROMANCER_RELEASE_NAME,'build_label':ROMANCER_BUILD_LABEL,'credit':'By RetchEWretched','platform':'windows-amd64','runtime':PINS,'engines':{'included':bool(engines),'systems':CORE_PINS if engines else {}},'files':rows}
        if native:manifest['observers']={'included':True,'families':['MesenCE 2.2.1 + physical-ppu-access-v2','MAME 0.289'],'source_included':True}
        (stage/'BUNDLE.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');verify_tree(stage)
        from romancer.patch_sets import _publish_directory
        _publish_directory(stage,destination)
    return {'ok':True,'path':str(destination),'version':ROMANCER_VERSION,'members':len(rows),'runtime_bundled':True,'engines_bundled':bool(engines)}


def package_bundle(bundle,destination):
    bundle=Path(bundle);destination=Path(destination);verified=verify_tree(bundle)
    if destination.exists():raise ValueError('package output already exists')
    fd,name=tempfile.mkstemp(prefix='.windows-zip-',dir=destination.parent);os.close(fd);temporary=Path(name)
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as z:
            for row in verified['manifest']['files']:z.write(bundle/row['path'],row['path'])
            z.write(bundle/'BUNDLE.json','BUNDLE.json')
        with zipfile.ZipFile(temporary) as z:
            for row in verified['manifest']['files']:
                with z.open(row['path']) as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=row['sha256']:raise ValueError('Windows archive member mismatch')
        verify_tree(bundle);os.link(temporary,destination)
    finally:temporary.unlink(missing_ok=True)
    with destination.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'ok':True,'path':str(destination),'sha256':sha,'version':verified['manifest']['version']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--app',type=Path,required=True);parser.add_argument('--downloads',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--zip',type=Path);parser.add_argument('--observers',type=Path,help='Reviewed native observer pack with complete source and notices');parser.add_argument('--cores',type=Path,help='Verified engine pack, including corresponding source and licenses');args=parser.parse_args()
    print(json.dumps(build_bundle(args.app,args.downloads,args.output,cores=args.cores,observers=args.observers)))
    if args.zip:print(json.dumps(package_bundle(args.output,args.zip)))
