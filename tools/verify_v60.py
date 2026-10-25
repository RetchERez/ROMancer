"""Independent five-system edit/export checks, with optional real native cores."""
import argparse
import base64
import hashlib
import json
import platform
from pathlib import Path
import sys
import tempfile
import uuid

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from romancer import ROMANCER_VERSION
from romancer.boot_fixtures import make_boot_fixture
from romancer.system_identify import identify_system
from romancer.system_integrity import integrity_edits
from romancer.streaming_bps import create_patch,apply_patch


def verify(root,cores=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);results=[]
    for system in ('nes','snes','genesis','gb','gba'):
        fixture=make_boot_fixture(system);original=fixture['data'];source=root/(system+fixture['suffix']);source.write_bytes(original)
        sha=hashlib.sha256(original).hexdigest();assessment=identify_system(source,expected_sha256=sha)
        if assessment['system_id']!=system or assessment['status']!='IDENTIFIED':raise ValueError('fixture recognition failed: '+system)
        edit={k:fixture[k] for k in ('offset','before','after')};hunks=integrity_edits(source,sha,system,[edit]);changed=bytearray(original)
        for h in hunks:changed[h['offset']:h['offset']+len(bytes.fromhex(h['after']))]=bytes.fromhex(h['after'])
        from romancer.workbench_api import WorkbenchAPI
        with_api=WorkbenchAPI(root/(system+'-workspace'))
        try:
            demo=with_api.dispatch('project.demo_system',{'system_id':system})
            if not demo['ok']:raise ValueError(demo)
            owned=demo['sources'][0];params={'project_id':demo['project_id'],'artifact_id':owned['artifact_id']};schema=owned['descriptors']['assets']
            model=with_api.dispatch('assets.inspect',{**params,'schema':schema})
            if not model['ok']:raise ValueError(model)
            if system in ('nes','gb'):
                before=model['bitmaps'][0]['cells'][0]['pixels'];after=before.copy();after[1]=1
                changes=[{'kind':'cell','bitmap_id':'tiles','cell_index':0,'before_pixels':before,'after_pixels':after}]
            else:
                palette=model['palettes'][0];entry=palette['entries'][0]
                changes=[{'kind':'palette','palette_id':palette['id'],'bank':0,'index':0,'before':entry['components'],'after':{'r':7 if system=='genesis' else 31,'g':0,'b':0}}]
            request={'schema_version':1,'document_id':model['document_id'],'changes':changes,'acknowledged_consumers':[]}
            plan=with_api.dispatch('assets.plan',{**params,'schema':schema,'edits':request})
            if not plan['ok'] and plan.get('required_consumers'):
                request['acknowledged_consumers']=plan['required_consumers'];plan=with_api.dispatch('assets.plan',{**params,'schema':schema,'edits':request})
            if not plan['ok']:raise ValueError(plan)
            built=with_api.dispatch('structured.apply',{'project_id':demo['project_id'],'plan_id':plan['workbench_plan_id']})
            if not built['ok']:raise ValueError(built)
            target=Path(built['path'])
            if target.read_bytes()!=bytes(changed):raise ValueError('structured complete output differs from independent resource/checksum oracle: '+system)
            indexed=with_api.dispatch('catalog.index',params)
            if not indexed['ok']:raise ValueError(indexed)
        finally:with_api.close()
        # Oracle: all bytes outside the one intended resource and specified integrity fields stay exact.
        allowed=set(range(edit['offset'],edit['offset']+len(bytes.fromhex(edit['after']))))
        if system=='snes':allowed.update(range(0x7fdc,0x7fe0))
        if system=='genesis':allowed.update(range(0x18e,0x190))
        if system=='gb':allowed.update(range(0x14d,0x150))
        if system=='gba':allowed.add(0xbd)
        differences=[i for i,(a,b) in enumerate(zip(original,changed)) if a!=b]
        if not differences or not set(differences)<=allowed:raise ValueError('unexpected complete output difference')
        patch=root/(system+'.bps');created=create_patch(source,target,patch,{'title':'Original '+system+' test'})
        rebuilt=root/(system+'-rebuilt'+fixture['suffix']);apply_patch(source,patch,rebuilt)
        if rebuilt.read_bytes()!=bytes(changed) or source.read_bytes()!=original:raise ValueError('independent reconstruction/original preservation failed')
        row={'system_id':system,'source_sha256':sha,'target_sha256':created['target_sha256'],'changed_offsets':differences,'patch_verified':True,'declared_graphics_roundtrip':True,'structured_build_matches_oracle':True,'native':None}
        if cores:
            from romancer.runtime_session import OwnedRuntime,preflight_load
            core=Path(cores[system]['core']).resolve();captures=[];measurements=[]
            for label,game in [('source',source),('target',target)]:
                load={'core':str(core),'game':str(game.resolve()),'session_dir':str((root/(system+'-'+label+'-'+uuid.uuid4().hex)).resolve()),
                    'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(game.read_bytes()).hexdigest(),
                    'core_options':cores[system].get('options',{})}
                with OwnedRuntime(preflight_load(load,root.resolve()),45) as runtime:
                    runtime.request('advance',frames=120,buttons=[],port=0);frame=runtime.request('capture');rgb=base64.b64decode(frame['rgb24_base64'],validate=True)
                    if len(rgb)!=frame['width']*frame['height']*3:raise ValueError('native frame dimensions mismatch')
                    colors=set(zip(rgb[0::3],rgb[1::3],rgb[2::3]))
                    if label=='source':
                        if system in ('nes','gb') and len(colors)<2:raise ValueError('native pattern program did not draw')
                        if system in ('snes','genesis','gba') and not all(g>r+100 and g>b+100 for r,g,b in colors):raise ValueError('native program did not draw green backdrop')
                    audio=runtime.request('audio');state=runtime.request('save_state');runtime.request('advance',frames=1,buttons=['a'],port=0)
                    runtime.request('load_state',snapshot=state);runtime.request('advance',frames=1,buttons=[],port=0);restored=runtime.request('capture')
                    if restored['sha256']!=frame['sha256']:raise ValueError('state restore did not reproduce the program frame')
                    runtime.close_verified();captures.append(frame['sha256'])
                    measurements.append({'revision':label,'width':frame['width'],'height':frame['height'],'frame_sha256':frame['sha256'],
                        'audio_samples_observed':audio['observed'],'state_restore_verified':True,'input_acknowledged':True,'worker_exit_code':runtime.exit_code})
            if captures[0]==captures[1]:raise ValueError('native render did not change after resource edit: '+system)
            row['native']={'core_sha256':load['expected_core_sha256'],'options':load['core_options'],'render_changed':True,'measurements':measurements,
                'scope':'original minimal test program; no commercial game or Color-only compatibility claim'}
        results.append(row)
    return {'ok':True,'status':'VERIFIED','tool_version':ROMANCER_VERSION,'environment':{'python':platform.python_version(),'platform':platform.platform()},'systems':results,'credit':'By RetchEWretched','native_cores_exercised':bool(cores)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cores',type=Path);parser.add_argument('--work-dir',type=Path);args=parser.parse_args()
    if args.cores:
        directory=args.work_dir or Path(tempfile.mkdtemp(prefix='romancer-v60-native-'))
        if args.work_dir:directory.mkdir(parents=True,exist_ok=False)
        result=verify(directory,json.loads(args.cores.read_text()))
    else:
        with tempfile.TemporaryDirectory(prefix='romancer-v60-') as directory:result=verify(directory)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'ok':True,'systems':len(result['systems']),'native':result['native_cores_exercised']}))
