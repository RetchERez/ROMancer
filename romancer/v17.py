
from __future__ import annotations
import json, tempfile
from pathlib import Path
from .util import write_json
from .proof_v17 import evaluate_invariants, compare_modes, build_proof_bundle
VERSION='17.0.0'

def add_v17_parsers(sub):
    s=sub.add_parser('prove',help='[v17] Evaluate declared static/runtime/semantic invariants and accepted differences'); s.add_argument('manifest'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('proof-compare',help='[v17] Compare two structured result manifests with explicit equivalence modes'); s.add_argument('baseline'); s.add_argument('candidate'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('proof-bundle',help='[v17] Build a reproducible proof bundle without ROM/disc/save artifacts'); s.add_argument('manifest'); s.add_argument('--out-dir',required=True); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('v17-self-test',help='[v17] Test proof invariants, comparison modes and proof bundle creation'); s.add_argument('--out'); s.add_argument('--json',action='store_true')

def v17_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix='romancer_v17_') as td0:
        td=Path(td0)
        m={'invariants':[{'name':'source hash','status':'PASS','required':True},{'name':'optional coverage','status':'WARN','required':False}], 'differences':[{'id':'text-change','mode':'intentional-different'}]}
        p=td/'proof_manifest.json'; p.write_text(json.dumps(m))
        ev=evaluate_invariants(str(p)); tests.append({'name':'proof accepts required pass and documented diff','ok':ev['valid'] and ev['optional_warning_count']==1})
        bad=evaluate_invariants({'invariants':[{'name':'runtime','status':'FAIL','required':True}]}); tests.append({'name':'proof rejects required failure','ok':not bad['valid']})
        a=td/'a.json'; b=td/'b.json'; a.write_text(json.dumps({'frame':{'semantic':'battle_menu','sha':'a'}})); b.write_text(json.dumps({'frame':{'semantic':'battle_menu','sha':'b'}}))
        cmp=compare_modes(str(a),str(b)); tests.append({'name':'comparison detects semantic equivalence','ok':cmp['rows'][0]['mode']=='semantically-equivalent'})
        bun=build_proof_bundle(str(p),str(td/'bundle')); tests.append({'name':'proof bundle records proof hash','ok':Path(bun['dir'],'proof.json').exists() and bun['valid']})
    res={'tool':'ROMancer','version':VERSION,'feature':'v17 self-test','ok':all(t['ok'] for t in tests),'tests':tests}
    if out: write_json(out,res)
    return res

def dispatch_v17(args):
    c=getattr(args,'cmd','')
    if c=='prove': return True,evaluate_invariants(args.manifest,args.out)
    if c=='proof-compare': return True,compare_modes(args.baseline,args.candidate,args.out)
    if c=='proof-bundle': return True,build_proof_bundle(args.manifest,args.out_dir,args.out)
    if c=='v17-self-test': return True,v17_self_test(args.out)
    return False,None
