
from __future__ import annotations
import tempfile
from pathlib import Path
from .util import write_json
from .final_lab_v20 import lab_lifecycle, final_certify, self_certify, publish_report, lab_plan
VERSION='20.0.0'

def add_v20_parsers(sub):
    s=sub.add_parser('lab-lifecycle',help='[v20] Evaluate project lifecycle evidence across research/build/prove/certify/package stages'); s.add_argument('manifest'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('final-certify',help='[v20] Integrate proof invariants and release gates into final certification'); s.add_argument('manifest'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('self-certify',help='[v20] Certify a ROMancer tree for documentation/source/hygiene gates'); s.add_argument('root'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('publish-report',help='[v20] Produce a structured release report from supplied evidence sections'); s.add_argument('manifest'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('lab-plan',help='[v20] Build a full lab plan from a semantic hack request'); s.add_argument('request'); s.add_argument('--out'); s.add_argument('--json',action='store_true')
    s=sub.add_parser('v20-self-test',help='[v20] Test final autonomous lab lifecycle, certification, reporting and self-certification'); s.add_argument('--out'); s.add_argument('--json',action='store_true')

def v20_self_test(out=None):
    tests=[]
    with tempfile.TemporaryDirectory(prefix='romancer_v20_') as td0:
        td=Path(td0)
        life=lab_lifecycle({'project':'Fixture','evidence':['source_hash','baseline_profile','feature_request','patch_plan','runtime_scenario','failure_oracle','repair_bounds','proof_manifest','certification_manifest','hygiene_scan','release_report']})
        tests.append({'name':'complete lifecycle is ready','ok':life['ready']})
        blocked=lab_lifecycle({'project':'Fixture','evidence':['source_hash']})
        tests.append({'name':'incomplete lifecycle blocks','ok':not blocked['ready']})
        cert=final_certify({'invariants':[{'name':'static','status':'PASS','required':True}], 'gates':[{'name':'runtime','ok':True,'required':True}]})
        tests.append({'name':'final certification accepts all gates','ok':cert['release_status']=='CERTIFIED'})
        rep=publish_report({'project':{'name':'Fixture'},'packaging':{'rom_included':False}}); tests.append({'name':'release report has hash','ok':'report_hash' in rep and len(rep['sections'])>=5})
        plan=lab_plan('Add Mockery command'); tests.append({'name':'lab plan integrates feature planning','ok':plan['feature_plan']['task_count']>3 and len(plan['lab_stages'])>=5})
        root=td/'tree'; (root/'romancer').mkdir(parents=True); (root/'romancer'/'x.py').write_text('x=1'); (root/'docs').mkdir(); (root/'docs'/'A.md').write_text('doc')
        sc=self_certify(str(root)); tests.append({'name':'self certification passes clean tree','ok':sc['release_status']=='CERTIFIED'})
    res={'tool':'ROMancer','version':VERSION,'feature':'v20 self-test','ok':all(t['ok'] for t in tests),'tests':tests}
    if out: write_json(out,res)
    return res

def dispatch_v20(args):
    c=getattr(args,'cmd','')
    if c=='lab-lifecycle': return True,lab_lifecycle(args.manifest,args.out)
    if c=='final-certify': return True,final_certify(args.manifest,args.out)
    if c=='self-certify': return True,self_certify(args.root,args.out)
    if c=='publish-report': return True,publish_report(args.manifest,args.out)
    if c=='lab-plan': return True,lab_plan(args.request,args.out)
    if c=='v20-self-test': return True,v20_self_test(args.out)
    return False,None
