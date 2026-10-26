from __future__ import annotations
from pathlib import Path
from typing import Any
import json, time
from .util import read_bytes, sha1, write_json
from .ips import create_ips
from .diffing import byte_diff


def patch_workspace(project:str, name:str)->dict[str,Any]:
    root=Path(project)/'patches'/name
    for sub in ['source','build','reports']:(root/sub).mkdir(parents=True,exist_ok=True)
    manifest={'tool':'ROMancer','feature':'v0.8 patch-workspace','name':name,'created':time.time(),'status':'draft','validation_status':'unverified'}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (root/'README.txt').write_text('ROMancer patch workspace. Add source/patch.asm or byte patch notes, then build/validate manually or with ROMancer helpers.\n',encoding='utf-8')
    return {'workspace':str(root),'manifest':manifest}

def patch_build(workspace:str, original:str|None=None, modified:str|None=None, ips_out:str|None=None)->dict[str,Any]:
    root=Path(workspace); (root/'build').mkdir(parents=True,exist_ok=True); (root/'reports').mkdir(exist_ok=True)
    result={'tool':'ROMancer','feature':'v0.8 patch-build','workspace':str(root),'status':'structural'}
    if original and modified:
        ips_path=ips_out or str(root/'build'/(root.name+'.ips'))
        result['ips']=create_ips(original,modified,ips_path)
        result['diff']=byte_diff(original,modified)
        result['original_sha1']=sha1(read_bytes(original)); result['modified_sha1']=sha1(read_bytes(modified))
    else:
        result['warnings']=['No original/modified ROM supplied. Workspace initialized but no patch was built.']
    write_json(root/'reports'/'patch_build.json',result)
    return result

def patch_rebuild(manifest:str)->dict[str,Any]:
    obj=json.loads(Path(manifest).read_text(encoding='utf-8'))
    return {'tool':'ROMancer','feature':'v0.8 patch-rebuild','manifest':manifest,'status':'manifest_loaded','note':'Rebuild requires original/modified ROM or ASM build instructions in manifest.','manifest_data':obj}

def regression_plan(system:str, patch:str|None=None, out:str|None=None)->str:
    common=['Boot ROM and confirm title screen/menu appears.','Load or reach a reproducible test state.','Trigger the edited behavior.','Confirm expected behavior changed.','Confirm nearby unrelated behaviors still work.','Run for several minutes without crash/hang.','Record emulator, ROM hash, patch hash, and test date.']
    extras={'snes':['Confirm mapping/header state matches patch manifest.','Open affected menus after the edited event.'], 'nes':['Confirm mapper/bank behavior on hardware-accurate emulator.'], 'genesis':['Confirm 68K and VDP behavior if graphics/text were edited.']}.get(system.lower(),[])
    text='ROMancer Regression Plan\n\nSystem: '+system+'\nPatch: '+str(patch or 'unspecified')+'\n\n'+'\n'.join(f'- {x}' for x in common+extras)+'\n'
    if out: Path(out).parent.mkdir(parents=True,exist_ok=True); Path(out).write_text(text,encoding='utf-8')
    return text

def patch_compare(a:str,b:str)->dict[str,Any]:
    da=read_bytes(a); db=read_bytes(b)
    return {'tool':'ROMancer','feature':'v0.8 patch-compare','a':{'file':a,'size':len(da),'sha1':sha1(da)},'b':{'file':b,'size':len(db),'sha1':sha1(db)},'same':da==db,'size_delta':len(db)-len(da),'note':'Binary patch semantic comparison is limited; use manifests for detailed hunk-level comparison.'}
