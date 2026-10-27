"""Deliberate first-use downloads of pinned official tools, never ROM uploads.

External binaries are not part of ROMancer's release inventory. Only fixed
upstream artifacts can be prepared; no caller URL, executable or path is accepted.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,Request,build_opener
import uuid
import zipfile
from .assets import checked_path

HOSTS={'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','codeload.github.com'}
MESEN=('https://github.com/nesdev-org/MesenCE/releases/download/2.2.1/Mesen_2.2.1_Windows.zip',34259023,'c19e10b3b3865eb0e86e4d01bf09a5027a4452081c04b5bd5b6cbbf76e346fd6')
MESEN_SOURCE=('https://codeload.github.com/nesdev-org/MesenCE/zip/20ba206cef5ba207c21203176d02cb9f43dda9fb',4423524,'a16a880173d73c8320ad15203e9e69b59e0789da0fe8cf5358ec33c1b92b2886')
MAME=('https://github.com/mamedev/mame/releases/download/mame0289/mame0289b_x64.exe',87626249,'a1aa7912168c9d1b05e611906bc21b8b9be3935822aead36d12a1da363150b7d')
SEVEN_ZR=('https://github.com/ip7z/7zip/releases/download/26.04/7zr.exe',602624,'256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282')
MAME_NOTICES={'COPYING':'1bacfdc30348e82256ff7626ad8f5489b57b52c0da75e3572bec3b3c791f76a8',
 'BSD-2-Clause':'3b50c5c18a9c5557618a30c1cfe7e70cd3dfa9227ec8f14df54f200bbbe1132e',
 'BSD-3-Clause':'13f9eb8c17572e626c11e2c5523594907973a4ecf3ab73030345879eef894775',
 'BSL-1.0':'fbbd4ec0e2c5878ab05acc0248454537c3ea6e790d057cafc5558d4fab2a25af',
 'CC0':'daa216b67f1f917d3d0f69c93d8b191e848a1cd10694b723ab61eab72d3ae9fd',
 'GPL-2.0':'451337b1aa550e4dd838535c514a5e06f6a936887a3e7e7239e0d65a35a2772a',
 'LGPL-2.1':'9c430893db6b214c0c2d207fe7da097a0a3b036b0172010f25e01fd5774583ea',
 'MIT':'09fa29fbc395300ae6bcdd61be1a8d2995c2aa76214b25e96d95941d8270ae4c',
 'Zlib':'f3afb7c6441a05344d39c56738bf933ad5696ce815611c6d32fd94229d7e0116'}
LOCK=threading.Lock()


def official_url(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Debugger downloads must stay on the fixed official HTTPS asset hosts.')


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        official_url(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_info(system):
    from .native_debugger import backend_capabilities
    capability=backend_capabilities(system)
    if not capability['supported_system']:raise ValueError('No pinned debugger is available for this system.')
    genesis=system=='genesis'
    return {'requires_network':True,'bundled':False,'download_bytes':(MAME[1]+SEVEN_ZR[1]) if genesis else MESEN[1]+MESEN_SOURCE[1],
        'upstream':capability['upstream'],'license':'GPL-2.0-or-later' if genesis else 'GPL-3.0-or-later',
        'source_url':capability['upstream']+'/tree/'+('f34f02505e32c1993c6a782b6814232cbfc74e36' if genesis else '20ba206cef5ba207c21203176d02cb9f43dda9fb'),
        'preparable':capability['host_supported'],'scope':'A deliberate first-use download into this local workspace. Nothing is uploaded. Later captures use the verified cache offline.'}


def cache_root(workspace,system):
    family=cache_family(system);parent=checked_path(Path(workspace)/'debuggers');active=checked_path(parent/(family+'.active.json'))
    if active.exists():
        if not active.is_file() or active.stat().st_size>512:raise ValueError('Debugger cache selection is invalid. Prepare a verified replacement.')
        try:record=json.loads(active.read_text(encoding='utf-8'))
        except (OSError,ValueError) as error:raise ValueError('Debugger cache selection cannot be read. Prepare a verified replacement.') from error
        if type(record) is not dict or set(record)!={'generation'} or type(record['generation']) is not str or re.fullmatch(re.escape(family)+r'-[0-9a-f]{32}',record['generation']) is None:
            raise ValueError('Debugger cache selection is invalid. Prepare a verified replacement.')
        return checked_path(parent/record['generation'])
    return checked_path(parent/family)


def cache_family(system):
    download_info(system)
    return 'mame-0.289' if system=='genesis' else 'mesence-2.2.1'


def preferred_root(workspace,system):
    from .native_debugger import backend_root
    bundled=backend_root(system)
    if bundled.exists():return bundled
    cached=cache_root(workspace,system)
    return cached if cached.exists() else bundled


def verify_prepared(root,system):
    from .native_debugger import verify_backend
    backend=verify_backend(root,system=system)
    manifest=checked_path(root/'backend.json')
    if not manifest.is_file() or manifest.stat().st_size>16384:raise ValueError('Prepared debugger source metadata is missing or invalid.')
    try:metadata=json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:raise ValueError('Prepared debugger source metadata cannot be read.') from error
    if type(metadata) is not dict or metadata.get('schema_version')!=1 or metadata.get('backend')!=backend:raise ValueError('Prepared debugger source identity differs.')
    if system=='genesis':
        for name,digest in MAME_NOTICES.items():
            path=checked_path(root/name)
            if not path.is_file() or path.stat().st_size>65536 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('A prepared upstream notice is missing or changed.')
    else:
        verify_file(root/'COPYING',35147,'8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903')
        verify_file(root/'source-snapshot.zip',MESEN_SOURCE[1],MESEN_SOURCE[2])
    return backend


def download(url,destination,size,digest,*,cancelled):
    official_url(url)
    if type(size) is not int or not 1<=size<=100*1024**2:raise ValueError('Artifact size exceeds its preparation budget.')
    if cancelled():raise KeyboardInterrupt
    destination=checked_path(Path(destination));started=time.monotonic();actual=hashlib.sha256();received=0
    opener=build_opener(OfficialRedirect())
    with opener.open(Request(url,headers={'User-Agent':'ROMancer/1.0 (pinned debugger preparation)'}),timeout=15) as response,destination.open('xb') as output:
        official_url(response.geturl())
        while True:
            if cancelled():raise KeyboardInterrupt
            if time.monotonic()-started>180:raise ValueError('Official tool download exceeded its time budget.')
            chunk=response.read(min(1024**2,size-received+1))
            if not chunk:break
            received+=len(chunk)
            if received>size:raise ValueError('Official tool download exceeds its pinned size.')
            actual.update(chunk);output.write(chunk)
    if received!=size or actual.hexdigest()!=digest:raise ValueError('Official tool download does not match its pinned size and SHA-256.')


def extract_mesen(archive,output,*,cancelled):
    from .native_debugger import MEMBERS
    with zipfile.ZipFile(archive) as source:
        files=source.infolist()
        if len(files)!=1 or files[0].filename!='Mesen.exe' or files[0].is_dir() or files[0].file_size!=MEMBERS['Mesen.exe'][0]:
            raise ValueError('Official Mesen archive member layout differs from the pinned release.')
        with source.open(files[0]) as stream,(output/'Mesen.exe').open('xb') as target:
            while chunk:=stream.read(1024**2):
                if cancelled():raise KeyboardInterrupt
                target.write(chunk)
    verify_file(output/'Mesen.exe',*MEMBERS['Mesen.exe'])


def verify_file(path,size,digest):
    path=checked_path(path)
    if not path.is_file() or path.stat().st_size!=size or path.stat().st_nlink!=1:raise ValueError('Prepared file differs from its pinned extent.')
    with path.open('rb') as source:actual=hashlib.file_digest(source,'sha256').hexdigest()
    if actual!=digest:raise ValueError('Prepared file differs from its pinned hash.')


def hidden(arguments,job,*,cancelled,seconds=30):
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    process=None
    try:
        with (job/'stdout.txt').open('wb') as out,(job/'stderr.txt').open('wb') as err:
            process=subprocess.Popen(arguments,cwd=job,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW,startupinfo=startup)
            deadline=time.monotonic()+seconds
            while process.poll() is None:
                if cancelled():raise KeyboardInterrupt
                if time.monotonic()>deadline:raise ValueError('Tool preparation helper exceeded its time budget.')
                if any((job/n).stat().st_size>2*1024**2 for n in ('stdout.txt','stderr.txt')):raise ValueError('Tool preparation exceeded its output budget.')
                time.sleep(.025)
        if process.returncode!=0:raise ValueError('Pinned preparation helper did not complete (exit '+str(process.returncode)+').')
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=5)


def materialize_mesen(job,runtime,*,cancelled):
    from .native_debugger import MEMBERS,portable_settings,verify_backend
    from .boot_fixtures import make_boot_fixture
    archive=job/'upstream.zip';download(MESEN[0],archive,MESEN[1],MESEN[2],cancelled=cancelled)
    bootstrap=job/'bootstrap';bootstrap.mkdir();extract_mesen(archive,bootstrap,cancelled=cancelled)
    # Settings must exist BEFORE TestRunner starts, or upstream can show setup UI.
    (bootstrap/'settings.json').write_text(json.dumps(portable_settings('nes')),encoding='utf-8',newline='\n')
    (bootstrap/'prepare.lua').write_text('emu.stop(0)\n',encoding='utf-8',newline='\n')
    (bootstrap/'input.nes').write_bytes(make_boot_fixture('nes')['data'])
    hidden([str(bootstrap/'Mesen.exe'),'--testrunner','--timeout=3','prepare.lua','input.nes'],bootstrap,cancelled=cancelled,seconds=15)
    verify_backend(bootstrap)
    for name in MEMBERS:shutil.copyfile(bootstrap/name,runtime/name)
    source=runtime/'source-snapshot.zip';download(MESEN_SOURCE[0],source,MESEN_SOURCE[1],MESEN_SOURCE[2],cancelled=cancelled)
    with zipfile.ZipFile(source) as zipped:
        member='MesenCE-20ba206cef5ba207c21203176d02cb9f43dda9fb/LICENSE';info=zipped.getinfo(member)
        if info.file_size!=35147:raise ValueError('Pinned upstream license extent differs.')
        (runtime/'COPYING').write_bytes(zipped.read(info))
    verify_file(runtime/'COPYING',35147,'8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903')
    return verify_backend(runtime)


def materialize_mame(job,runtime,*,cancelled):
    from .genesis_debugger import verify_backend
    # This is an archive input, never an executable to launch.
    archive=job/'upstream.7z';helper=job/'7zr.exe'
    download(MAME[0],archive,MAME[1],MAME[2],cancelled=cancelled)
    download(SEVEN_ZR[0],helper,SEVEN_ZR[1],SEVEN_ZR[2],cancelled=cancelled)
    members=['mame.exe','COPYING']+['docs\\legal\\'+name for name in MAME_NOTICES if name!='COPYING']
    hidden([str(helper),'e','-t7z','-y','-aos','-bd','-bb0','-bso0','-bsp0','-bse2','-spd','-r-','-mmt1','-o'+str(runtime),'--',str(archive),*members],job,cancelled=cancelled,seconds=60)
    if {p.name for p in runtime.iterdir()}!={'mame.exe',*MAME_NOTICES}:raise ValueError('Prepared archive output contains missing or unexpected members.')
    for name,digest in MAME_NOTICES.items():
        path=checked_path(runtime/name)
        if not path.is_file() or path.stat().st_nlink!=1 or path.stat().st_size>65536:raise ValueError('Upstream notice is missing or invalid.')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Upstream notice hash differs.')
    return verify_backend(runtime)


def prepare_backend(workspace,system,*,cancelled=lambda:False):
    info=download_info(system)
    if not info['preparable']:raise ValueError('Pinned debugger preparation requires a supported Windows x64 host.')
    if not LOCK.acquire(blocking=False):raise ValueError('Another debugger preparation is running. Wait for it to finish.')
    job=None;result=None
    try:
        
        cleanup_pending_stages(workspace)
        family=cache_family(system);cache_parent=checked_path(Path(workspace)/'debuggers');repaired=False
        try:target=cache_root(workspace,system)
        except ValueError:target=cache_parent/family;repaired=True
        if not repaired and target.exists():
            try:return {'ok':True,'status':'READY','backend':verify_prepared(target,system),'download':info,'already_prepared':True,'repaired':False}
            except (OSError,ValueError):repaired=True
        if (cache_parent/(family+'.active.json')).exists():repaired=True
        if repaired:target=cache_parent/(family+'-'+uuid.uuid4().hex)
        parent=checked_path(Path(workspace)/'sessions'/'debugger-install');parent.mkdir(parents=True,exist_ok=True)
        job=parent/uuid.uuid4().hex;job.mkdir();runtime=job/'runtime';runtime.mkdir()
        backend=(materialize_mame if system=='genesis' else materialize_mesen)(job,runtime,cancelled=cancelled)
        if cancelled():raise KeyboardInterrupt
        manifest={'schema_version':1,'backend':backend,'download':info,'delivery':'direct official upstream download on this machine',
            'romancer_redistribution_certified':False,'original_wrapper_license':'MIT',
            'source_scope':'Pinned upstream source snapshot or source links; not a claim that every transitive build input has been audited.'}
        (runtime/'backend.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8',newline='\n')
        activate(runtime,target,system,cancelled=cancelled)
        if repaired:
            active=checked_path(cache_parent/(family+'.active.json'));temporary=cache_parent/(family+'.active-'+uuid.uuid4().hex+'.tmp')
            try:
                with temporary.open('x',encoding='utf-8',newline='\n') as stream:json.dump({'generation':target.name},stream)
                os.replace(temporary,active)
            finally:temporary.unlink(missing_ok=True)
            if cache_root(workspace,system)!=target:raise ValueError('Debugger cache selection changed during repair; check availability again.')
        result={'ok':True,'status':'READY','backend':verify_prepared(target,system),'download':info,'already_prepared':False,'repaired':repaired}
        return result
    finally:
        original_error=sys.exception()
        try:
            if job is not None:
                if job.resolve().parent!=parent.resolve() or re.fullmatch('[0-9a-f]{32}',job.name) is None:raise ValueError('Preparation cleanup escaped owned sessions.')
                try:cleanup_stage(job)
                except PermissionError:
                    try:(job/'cleanup.json').write_text(json.dumps({'kind':'romancer-debugger-cleanup-v1'}),encoding='utf-8',newline='\n')
                    except OSError:pass
                    # A locked official download is not a failed activation.
                    # Preserve the verified result and report the retained data.
                    if result is None:
                        if original_error is None:raise
                        original_error.add_note('A temporary official download awaits a later bounded cleanup retry.')
                    else:
                        result['cleanup_pending']=True;result['pending_install_id']=job.name
                        result['cleanup_scope']='A temporary official package is still locked by the operating system. No user ROM was stored in this preparation stage.'
        finally:LOCK.release()


def cleanup_stage(job):
    for attempt in range(5):
        try:shutil.rmtree(job);return
        except PermissionError:
            if attempt==4:raise
            time.sleep(.1*(attempt+1))


def cleanup_pending_stages(workspace):
    parent=checked_path(Path(workspace)/'sessions'/'debugger-install')
    report={'examined':0,'removed':0,'pending':0,'truncated':False};attempted=0
    if not parent.is_dir():return report
    for index,job in enumerate(parent.iterdir()):
        if index>=16:report['truncated']=True;break
        if re.fullmatch('[0-9a-f]{32}',job.name) is None:continue
        try:
            job=checked_path(job)
            if job.resolve().parent!=parent.resolve() or not job.is_dir():continue
            marker=checked_path(job/'cleanup.json')
            if not marker.is_file() or marker.stat().st_size>512:continue
            contents=json.loads(marker.read_text(encoding='utf-8'))
            if type(contents) is not dict or contents.get('kind')!='romancer-debugger-cleanup-v1':continue
            report['examined']+=1
            if attempted>=3:report['pending']+=1;continue
            attempted+=1;cleanup_stage(job);report['removed']+=1
        except (OSError,ValueError):
            if job.exists():report['pending']+=1
    return report


def activate(runtime,target,system,*,cancelled):
    verify_prepared(runtime,system)
    target.parent.mkdir(parents=True,exist_ok=True)
    try:os.rename(runtime,target);return
    except OSError:
        if target.exists():verify_prepared(target,system);return
    # Some Windows installations lock newly extracted executable directories.
    # The manifest is the readiness barrier: cache consumers always verify it.
    paths=list(runtime.iterdir())
    if len(paths)>32 or any(not checked_path(p).is_file() or p.stat().st_size>400*1024**2 or p.stat().st_nlink!=1 for p in paths):
        raise ValueError('Prepared runtime member extent differs.')
    target.mkdir();created=[]
    try:
        for path in sorted(paths,key=lambda p:(p.name=='backend.json',p.name)):
            if cancelled():raise KeyboardInterrupt
            destination=target/path.name
            shutil.copyfile(path,destination);created.append(destination)
        verify_prepared(target,system)
    except BaseException:
        # Remove only individual files created by this activation, never other
        # contents that may have appeared concurrently in the cache directory.
        for path in reversed(created):
            try:path.unlink()
            except OSError:pass
        try:target.rmdir()
        except OSError:pass
        raise
