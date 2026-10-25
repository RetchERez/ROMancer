
from __future__ import annotations
import json, tempfile
from pathlib import Path
from .util import write_json
from .knowledge_commons_v16 import export_capsule, import_capsule, diff_capsules, audit_capsule

VERSION='16.0.0'

def add_v16_parsers(sub):
    s=sub.add_parser('knowledge-export',help='[v16] Export a safe ROMancer knowledge capsule without ROM/disc/save bytes'); s.add_argument('source'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('knowledge-import-capsule',help='[v16] Import a knowledge capsule as verified only for exact hash/revalidated facts'); s.add_argument('capsule'); s.add_argument('target'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('knowledge-diff-capsules',help='[v16] Diff two ROMancer knowledge capsules'); s.add_argument('a'); s.add_argument('b'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('knowledge-audit-capsule',help='[v16] Audit a knowledge capsule for shape and asset leakage indicators'); s.add_argument('capsule'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('v16-self-test',help='[v16] Test knowledge capsule export/import/diff/audit'); s.add_argument('--out'); s.add_argument('--json',action='store_true')

def v16_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix='romancer_v16_') as td0:
        td=Path(td0)
        src={'game':{'title':'Fixture','rom_sha256':'aaa'},'facts':[{'id':'r1','claim':'routine','status':'VERIFIED'}],'routines':[{'id':'main','addr':'C2/1000'}]}
        sp=td/'src.json'; sp.write_text(json.dumps(src))
        cap=export_capsule(str(sp)); tests.append({'name':'capsule export keeps metadata','ok':cap['format']=='rkc-json-v1' and cap['collections']['facts'][0]['id']=='r1'})
        tgt=td/'target.json'; tgt.write_text(json.dumps({'game':{'rom_sha256':'bbb'}}))
        imp=import_capsule(cap,str(tgt)); tests.append({'name':'different hash imports unverified','ok':imp['candidate_count']>=1 and imp['verified_count']==0})
        cap2=json.loads(json.dumps(cap)); cap2['collections']['facts'][0]['claim']='routine changed'; cap2['collections']['facts'].append({'id':'r2','claim':'new'})
        d=diff_capsules(cap,cap2); tests.append({'name':'capsule diff detects changed and added','ok':d['changed_count']==1 and d['added_count']==1})
        audit=audit_capsule(cap); tests.append({'name':'capsule audit passes safe capsule','ok':audit['ok']})
    res={'tool':'ROMancer','version':VERSION,'feature':'v16 self-test','ok':all(t['ok'] for t in tests),'tests':tests}
    if out: write_json(out,res)
    return res

def dispatch_v16(args):
    c=getattr(args,'cmd','')
    if c=='knowledge-export': return True, export_capsule(args.source,args.out)
    if c=='knowledge-import-capsule': return True, import_capsule(args.capsule,args.target,args.out)
    if c=='knowledge-diff-capsules': return True, diff_capsules(args.a,args.b,args.out)
    if c=='knowledge-audit-capsule': return True, audit_capsule(args.capsule,args.out)
    if c=='v16-self-test': return True, v16_self_test(args.out)
    return False,None
