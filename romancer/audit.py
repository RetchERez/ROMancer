from __future__ import annotations
from pathlib import Path
from typing import Any
import json, zipfile
from .util import read_bytes, sha1, sha256, crc32_hex


def audit_project(project:str)->dict[str,Any]:
    p=Path(project); issues=[]
    if not p.exists(): return {'ok':False,'issues':[{'severity':'error','issue':'project path does not exist'}]}
    for jf in p.rglob('*.json'):
        try: json.loads(jf.read_text(encoding='utf-8'))
        except Exception as e: issues.append({'severity':'error','file':str(jf),'issue':'invalid JSON','detail':str(e)})
    k=p/'knowledge.json'
    if k.exists():
        db=json.loads(k.read_text(encoding='utf-8'))
        for f in db.get('findings',[]):
            if f.get('status')=='confirmed' and not f.get('evidence'): issues.append({'severity':'warning','issue':'confirmed finding lacks evidence','claim':f.get('claim')})
    for m in p.rglob('manifest.json'):
        try:
            obj=json.loads(m.read_text(encoding='utf-8'))
            if obj.get('validation_status') in (None,'unverified'): issues.append({'severity':'warning','file':str(m),'issue':'patch manifest unverified'})
        except Exception: pass
    return {'tool':'ROMancer','feature':'v0.9 audit-project','project':project,'issue_count':len(issues),'issues':issues,'ok':not any(i['severity']=='error' for i in issues)}

def report_check(folder:str)->dict[str,Any]:
    p=Path(folder); issues=[]
    for f in p.rglob('*'):
        if f.is_file() and f.suffix.lower()=='.json':
            try: json.loads(f.read_text(encoding='utf-8'))
            except Exception as e: issues.append({'file':str(f),'issue':'invalid json','detail':str(e)})
        if f.is_file() and f.suffix.lower() in ('.txt','.md'):
            txt=f.read_text(encoding='utf-8',errors='replace')
            if 'TODO' in txt: issues.append({'file':str(f),'issue':'contains TODO marker'})
    return {'tool':'ROMancer','feature':'v0.9 report-check','folder':folder,'issue_count':len(issues),'issues':issues}

def package_release(workspace:str, out:str)->dict[str,Any]:
    src=Path(workspace); dst=Path(out); dst.mkdir(parents=True,exist_ok=True)
    copied=[]
    for pat in ['*.ips','README.txt','manifest.json','reports/*.txt','reports/*.json','build/*.ips']:
        for f in src.glob(pat):
            target=dst/f.name; shutil_copy=False
            import shutil; shutil.copy2(f,target); copied.append(str(target))
    checks=[]
    for f in dst.iterdir():
        if f.is_file():
            b=f.read_bytes(); checks.append(f'{f.name}\tSHA1={sha1(b)}\tSHA256={sha256(b)}\tCRC32={crc32_hex(b)}')
    (dst/'checksums.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8')
    zip_path=str(dst)+'.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for f in dst.iterdir():
            if f.is_file(): z.write(f,arcname=f.name)
    return {'tool':'ROMancer','feature':'v0.9 package-release','release_folder':str(dst),'zip':zip_path,'files':copied+ [str(dst/'checksums.txt')]}
