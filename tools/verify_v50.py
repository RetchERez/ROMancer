"""Run the published synthetic workflow matrix; never infer private compatibility."""
import argparse
import json
from pathlib import Path
import sys
import uuid

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romancer import ROMANCER_VERSION
from romancer.workbench_projects import create_project,register_source,plan_byte_edits,apply_build,inspect_resource
from romancer.release import prepare_patch,verify_patch


def fixtures():
    from romancer.system_demo import make_system_fixtures
    labels={'nes':'NES','snes':'SNES','genesis':'Genesis','gb':'Game Boy','gba':'GBA'}
    return {labels[k]:v for k,v in make_system_fixtures().items()}



def verify_v50(workspace:Path)->dict:
    from romancer.system_identify import identify_system
    root=Path(workspace)/('verification-'+uuid.uuid4().hex);root.mkdir(parents=True)
    expected={'NES':'nes','SNES':'snes','Genesis':'genesis','Game Boy':'gb','GBA':'gba'}
    results={}
    for family,raw in fixtures().items():
        source=root/(family.replace(' ','-')+'.fixture');source.write_bytes(raw)
        detected=identify_system(source)
        project=Path(create_project(root/'projects',family+' synthetic matrix')['path']);registered=register_source(project,source,None)
        inspect_resource(project,registered['artifact_id'],0,min(256,len(raw)))
        offset=len(raw)-1;before=f'{raw[offset]:02x}';after=f'{raw[offset]^1:02x}'
        plan=plan_byte_edits(project,registered['artifact_id'],[{'offset':offset,'before':before,'after':after}]);build=apply_build(project,plan['plan_id'])
        patch=root/(family.replace(' ','-')+'.bps');prepared=prepare_patch(source,Path(build['path']),patch,{'title':family+' synthetic patch','description':'One explicit fixed byte change'})
        verified=verify_patch(source,patch,build['sha256'])
        # These names identify bounded detector behavior, not bootable commercial games.
        identification=detected.get('system_id')==expected[family]
        results[family]={'identification':'PASS' if identification else 'FAIL','detected':detected.get('system_id'),
            'generic_workflow':'PASS' if identification and source.read_bytes()==raw and prepared['ok'] and verified['ok'] else 'FAIL',
            'source_sha256':registered['sha256'],'target_sha256':build['sha256'],'patch_sha256':prepared['sha256'],
            'console_integrity_repaired':False,'structured_game_adapter':'NOT_CLAIMED','private_game_runtime':'NOT_RUN',
            'fixture_origin':'original_synthetic_header_and_bytes'}
    return {'schema_version':1,'operation':'verify-v50-published-matrix','tool_version':ROMANCER_VERSION,
        'ok':all(r['generic_workflow']=='PASS' for r in results.values()),'status':'MEASURED',
        'families':results,'full_game_compatibility_claimed':False,'release_status':'DEVELOPMENT',
        'credit':'By RetchEWretched','scope':'Synthetic identification, bounded inspection, fixed byte build, independent BPS application.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=verify_v50(args.workspace)
    text=json.dumps(result,indent=2,ensure_ascii=True)+'\n'
    if args.out:
        from romancer.release import publish_bytes
        publish_bytes(args.out,text.encode())
    print(text);return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
