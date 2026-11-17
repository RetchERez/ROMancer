"""Positive-inventory, license, byte-identity and obvious-secret release checks.

This is a bounded local packaging check, not a comprehensive security audit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.package_source import APPROVED_FILES,MAX_MEMBER_BYTES,MAX_TOTAL_BYTES
from tools.install_windows import INSTALL_LAYOUT,safe_name

PUBLIC_FILES={'LICENSE','README.txt','THIRD_PARTY_NOTICES.txt',
              '.gitignore','.gitattributes','.editorconfig','package.json','package-lock.json',
              '.github/workflows/ci.yml'}
MIT_SHA256='ef0a7141fe64a7187fa20240e1b0bb1b43e96085358a716dbb454a4386a766d0'
SECRET=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{40,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|#token=[A-Za-z0-9_-]{30,})')
LOCAL_USER=re.compile(rb'[A-Za-z]:[/\\]+Users[/\\]+(?!Public[/\\]|<)[^/\\\s"\']+',re.I)


def _members(archive,*,limit,total_limit=256*1024**2):
    result={};seen=set();total=0
    for item in archive.infolist():
        name=safe_name(item.filename)
        if name.casefold() in seen:raise ValueError('duplicate archive member')
        seen.add(name.casefold())
        if item.is_dir() or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('non-file archive member')
        total+=item.file_size
        if item.file_size>limit or total>total_limit or len(seen)>10000:raise ValueError('archive exceeds audit budget')
        result[name]=archive.read(item)
    return result


def _source_files(files):
    if set(files)-APPROVED_FILES:raise ValueError('unapproved source members: '+', '.join(sorted(set(files)-APPROVED_FILES)[:8]))
    if sum(map(len,files.values()))>MAX_TOTAL_BYTES:raise ValueError('source exceeds byte budget')
    for name,raw in files.items():
        if SECRET.search(raw):raise ValueError('credential pattern in '+name)
        if LOCAL_USER.search(raw):raise ValueError('local-user path in '+name)
    missing=APPROVED_FILES-set(files)
    if missing:raise ValueError('missing public release files: '+', '.join(sorted(missing)))
    license=files['LICENSE']
    if hashlib.sha256(license).hexdigest()!=MIT_SHA256:
        raise ValueError('project MIT license is incomplete')
    package=json.loads(files['package.json']);lock=json.loads(files['package-lock.json'])
    if package.get('license')!='MIT' or package.get('devDependencies',{}).get('esbuild')!='0.25.12':raise ValueError('unexpected development dependency/license')
    if lock.get('packages',{}).get('node_modules/esbuild',{}).get('version')!='0.25.12':raise ValueError('development lock differs from pin')


def audit_source(path):
    with zipfile.ZipFile(path) as archive:files=_members(archive,limit=MAX_MEMBER_BYTES)
    _source_files(files)
    return {'ok':True,'kind':'source','license':'MIT','members':len(files),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def audit_windows(path,source,downloads,*,cores=None,observers=None):
    from tools.package_windows import PINS,runtime_members,generated_root_files
    from romancer import ROMANCER_VERSION,ROMANCER_RELEASE_NAME,ROMANCER_BUILD_LABEL
    with zipfile.ZipFile(source) as archive:source_files=_members(archive,limit=MAX_MEMBER_BYTES)
    _source_files(source_files)
    with zipfile.ZipFile(path) as archive:files=_members(archive,limit=384*1024**2,total_limit=1024*1024**2)
    if 'BUNDLE.json' not in files:raise ValueError('missing Windows manifest')
    manifest=json.loads(files['BUNDLE.json']);rows={}
    from romancer.bundled_cores import CORE_PINS,core_members
    engines=core_members(cores) if cores is not None else {}
    from romancer.bundled_debuggers import observer_files
    from romancer.observer_pins import OBSERVER_FAMILIES
    native=observer_files(observers) if observers is not None else {}
    identity={'schema_version':1,'product':'ROMancer','version':ROMANCER_VERSION,
              'release_name':ROMANCER_RELEASE_NAME,'build_label':ROMANCER_BUILD_LABEL,
              'credit':'By RetchEWretched','platform':'windows-amd64','install_layout':INSTALL_LAYOUT,'runtime':PINS,
              'engines':{'included':bool(engines),'systems':CORE_PINS if engines else {}}}
    if native:identity['observers']={'included':True,'families':OBSERVER_FAMILIES,'source_included':True}
    if (type(manifest) is not dict or set(manifest)!=set(identity)|{'files'}
            or any(manifest.get(k)!=v or type(manifest.get(k)) is not type(v) for k,v in identity.items())
            or type(manifest.get('files')) is not list):raise ValueError('Windows manifest identity differs')
    for row in manifest['files']:
        if (type(row) is not dict or set(row)!={'path','size','sha256'}
                or type(row['size']) is not int or row['size']<0
                or type(row['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',row['sha256'])):
            raise ValueError('invalid Windows manifest member record')
        name=safe_name(row['path'])
        if name in rows:raise ValueError('duplicate manifest member')
        rows[name]=row
    if set(rows)!=set(files)-{'BUNDLE.json'}:raise ValueError('Windows manifest membership differs')
    for name,row in rows.items():
        if row['size']!=len(files[name]) or row['sha256']!=hashlib.sha256(files[name]).hexdigest():raise ValueError('Windows member hash differs: '+name)
    expected={f'app/{name}':raw for name,raw in source_files.items() if name!='README.txt'}
    for kind,pin in PINS.items():
        prefix='python/' if kind=='python' else 'python/Lib/site-packages/'
        expected.update({prefix+name:raw for name,raw in runtime_members(Path(downloads)/pin['file'],pin['sha256'],kind)})
    expected['python/python314._pth']=b'python314.zip\n.\nLib/site-packages\n../app\n'
    expected['LICENSE']=source_files['LICENSE'];expected.update(generated_root_files(readme=source_files['README.txt']))
    expected.update({'cores/'+name:raw for name,raw in engines.items()})
    expected.update({'debuggers/'+name:p.read_bytes() for name,p in native.items()})
    if set(files)!=set(expected)|{'BUNDLE.json'}:raise ValueError('Windows package contains unexpected or missing files')
    for name,raw in expected.items():
        if files[name]!=raw:raise ValueError('Windows pinned/source bytes differ: '+name)
    if json.loads(files['RUNTIME-ORIGINS.json'])!=PINS or manifest.get('runtime')!=PINS:raise ValueError('runtime origin metadata differs')
    required=['python/LICENSE.txt','python/Lib/site-packages/pillow-12.3.0.dist-info/licenses/LICENSE']
    if any(name not in files for name in required):raise ValueError('missing runtime notices')
    return {'ok':True,'kind':'windows','version':manifest['version'],'members':len(files),'pinned_runtime_verified':True,'engines_bundled':bool(engines),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--windows',type=Path);parser.add_argument('--downloads',type=Path);parser.add_argument('--observers',type=Path);parser.add_argument('--cores',type=Path);args=parser.parse_args()
    print(json.dumps(audit_source(args.source)))
    if args.windows:
        if not args.downloads:parser.error('--downloads is required to audit pinned Windows runtime bytes')
        print(json.dumps(audit_windows(args.windows,args.source,args.downloads,cores=args.cores,observers=args.observers)))


if __name__=='__main__':main()
