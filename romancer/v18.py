
from __future__ import annotations
import json, tempfile
from pathlib import Path
from .util import write_json
from .cross_engine_v18 import architecture_match, model_game, engine_template
VERSION='18.0.0'

def add_v18_parsers(sub):
    s=sub.add_parser('architecture-match',help='[v18] Match observations against cross-engine system templates'); s.add_argument('observations'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('model-game',help='[v18] Build a conservative cross-engine game model from observations'); s.add_argument('observations'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('engine-template',help='[v18] Emit a system-specific hypothesis/test template'); s.add_argument('engine'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('v18-self-test',help='[v18] Test architecture matching, model generation, and templates'); s.add_argument('--out'); s.add_argument('--json',action='store_true')

def v18_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix='romancer_v18_') as td0:
        p=Path(td0)/'obs.json'; p.write_text(json.dumps({'observations':[{'kind':'state','state':'SHOP','currency':100,'resource':'currency'},{'kind':'shop','action':'buy','price':10,'currency':'gil'},{'kind':'dialogue','text_box':True,'choice':False},{'kind':'combat','state':'BATTLE','hp':30,'enemy':'slime'}]}))
        m=architecture_match(str(p)); tests.append({'name':'architecture match finds shop and battle','ok':any(x['engine']=='ShopEngine' for x in m['matches']) and any(x['engine']=='BattleEngine' for x in m['matches'])})
        gm=model_game(str(p)); tests.append({'name':'model game exposes candidate systems','ok':'ShopEngine' in gm['candidate_systems'] or 'ShopEngine' in gm['confirmed_systems']})
        t=engine_template('ShopEngine'); tests.append({'name':'engine template contains buy verification','ok':any('verify' in s['step'] for s in t['test_steps'])})
    res={'tool':'ROMancer','version':VERSION,'feature':'v18 self-test','ok':all(t['ok'] for t in tests),'tests':tests}
    if out: write_json(out,res)
    return res

def dispatch_v18(args):
    c=getattr(args,'cmd','')
    if c=='architecture-match': return True,architecture_match(args.observations,args.out)
    if c=='model-game': return True,model_game(args.observations,args.out)
    if c=='engine-template': return True,engine_template(args.engine,args.out)
    if c=='v18-self-test': return True,v18_self_test(args.out)
    return False,None
