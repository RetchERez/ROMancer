
from __future__ import annotations
import tempfile
from pathlib import Path
from .util import write_json
from .creator_studio_v19 import feature_plan, constraint_check, compile_feature_source
VERSION='19.0.0'

def add_v19_parsers(sub):
    s=sub.add_parser('plan-feature',help='[v19] Decompose a creator feature request into evidence-scoped engineering tasks'); s.add_argument('request'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('constraint-check',help='[v19] Check retro design constraints such as length/space/evidence'); s.add_argument('manifest'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('compile-feature',help='[v19] Compile semantic feature source into a plan/proof request, not unsafe bytes'); s.add_argument('source'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('v19-self-test',help='[v19] Test feature planning, constraints and semantic source compile'); s.add_argument('--out'); s.add_argument('--json',action='store_true')

def v19_self_test(out=None):
    tests=[]
    p=feature_plan('Give Kefka a Mockery command with laugh animation and portrait proof')
    tests.append({'name':'feature plan detects command and graphics tasks','ok':any('command' in t['task'].lower() for t in p['tasks']) and any('graphics' in t['task'].lower() for t in p['tasks'])})
    ck=constraint_check({'command_name':'MOCKERY','max_name_length':7,'free_space_bytes':100,'required_space_bytes':80,'required_verified_facts':[{'id':'dispatcher','status':'VERIFIED'}]})
    tests.append({'name':'constraint check accepts fitting feature','ok':ck['ok']})
    bad=constraint_check({'command_name':'TOO_LONG_NAME','max_name_length':7,'free_space_bytes':10,'required_space_bytes':80,'required_verified_facts':[{'id':'x','status':'PLAUSIBLE'}]})
    tests.append({'name':'constraint check blocks length/space/evidence','ok':not bad['ok'] and bad['failure_count']>=3})
    with tempfile.TemporaryDirectory(prefix='romancer_v19_') as td0:
        f=Path(td0)/'feature.txt'; f.write_text('command_name: MOCKERY\nmax_name_length: 7\nfree_space_bytes: 100\nrequired_space_bytes: 80\n')
        comp=compile_feature_source(str(f)); tests.append({'name':'semantic source compiles to plan only','ok':comp['build_status']=='PLAN_ONLY' and comp['parsed_fields']['command_name']=='MOCKERY'})
    res={'tool':'ROMancer','version':VERSION,'feature':'v19 self-test','ok':all(t['ok'] for t in tests),'tests':tests}
    if out: write_json(out,res)
    return res

def dispatch_v19(args):
    c=getattr(args,'cmd','')
    if c=='plan-feature': return True,feature_plan(args.request,args.out)
    if c=='constraint-check': return True,constraint_check(args.manifest,args.out)
    if c=='compile-feature': return True,compile_feature_source(args.source,args.out)
    if c=='v19-self-test': return True,v19_self_test(args.out)
    return False,None
