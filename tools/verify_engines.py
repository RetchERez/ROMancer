"""Fresh-workspace native acceptance for the six automatically bundled engines.

Uses only ROMancer's original drawing programs. This tests startup, input, video,
state loading and worker closure, not compatibility with every commercial game.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romancer import ROMANCER_VERSION
from romancer.workbench_api import WorkbenchAPI


def verify_engines(workspace,output):
    workspace=Path(workspace).absolute();output=Path(output).absolute()
    if workspace.exists() or output.exists():raise ValueError('choose new acceptance workspace and report paths')
    report={'ok':False,'version':ROMANCER_VERSION,'scope':'Original drawing-program startup, input, video, save-state load and worker closure. Not whole-game certification.','systems':[]}
    api=WorkbenchAPI(workspace)
    def call(operation,**parameters):
        result=api.dispatch(operation,parameters)
        if not result.get('ok'):raise ValueError(operation+': '+str(result.get('error')))
        return result
    try:
        for system in ('nes','snes','genesis','gb','gbc','gba'):
            profile=call('profiles.get',system_id=system)
            if profile['status']!='BUNDLED':raise ValueError(system+' did not select a bundled engine automatically')
            demo=call('project.demo_system',system_id=system);p={'project_id':demo['project_id']}
            source=call('project.open',**p)['sources'][0]
            loaded=call('runtime.load_profile',**p,artifact_id=source['artifact_id'],system_id=system)
            call('runtime.advance',**p,frames=120,buttons=[],port=0);frame=call('runtime.capture',**p)
            raw=base64.b64decode(frame['rgb24_base64'],validate=True)
            if len(raw)!=frame['width']*frame['height']*3 or hashlib.sha256(raw).hexdigest()!=frame['sha256']:raise ValueError('native video identity differs')
            if system=='gbc' and not any(raw[i]!=raw[i+1] or raw[i]!=raw[i+2] for i in range(0,len(raw),3)):raise ValueError('Color-only fixture did not produce actual RGB colors')
            snapshot=call('runtime.save_state',**p)
            call('runtime.advance',**p,frames=12,buttons=['a','start'],port=0);one=call('runtime.capture',**p)
            call('runtime.load_state',**p,snapshot_id=snapshot['snapshot_id'])
            call('runtime.advance',**p,frames=12,buttons=['a','start'],port=0);two=call('runtime.capture',**p)
            if one['sha256']!=two['sha256']:raise ValueError('native frame replay differs after state load')
            closed=call('runtime.close',**p)
            if closed['worker_exit_code']!=0:raise ValueError('native worker did not close cleanly')
            report['systems'].append({'system':system,'engine':profile['engine'],'automatic':True,
                'core_sha256':loaded['core_sha256'],'source_sha256':source['sha256'],
                'dimensions':[frame['width'],frame['height']],'frame_sha256':frame['sha256'],
                'input_accepted':True,'state_load_and_frame_replay':True,'worker_exit_code':0})
        report['ok']=True
    except BaseException as error:
        report['error']=str(error);raise
    finally:
        api.close();output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(verify_engines(args.workspace,args.output)))
