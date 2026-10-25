"""Execute the scoped system-foundation workflow with original structural fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romancer import ROMANCER_VERSION
from romancer.system_demo import make_system_fixtures
from romancer.workbench_api import WorkbenchAPI
from romancer.release import apply_bps,publish_bytes


def verify_v51(workspace:Path)->dict:
    root=Path(workspace)/('system-foundation-'+uuid.uuid4().hex);root.mkdir(parents=True)
    api=WorkbenchAPI(root/'workspace');families={};sources={};fixtures=make_system_fixtures()
    try:
        project=api.dispatch('project.create',{'name':'Original system foundation verification'})
        p={'project_id':project['project_id']}
        for family,raw in fixtures.items():
            path=root/(family+'.fixture');path.write_bytes(raw)
            row=api.dispatch('source.import',{**p,'path':str(path),'system':None})
            if row.get('ok') is not True:raise ValueError(str(row))
            assessment=api.dispatch('systems.identify',{**p,'artifact_id':row['artifact_id']})
            passed=assessment.get('system_id')==family and path.read_bytes()==raw and not assessment['write_authorized'] and not assessment['runtime_verified']
            families[family]={'status':'PASS' if passed else 'FAIL','source_sha256':row['sha256'],
                'format':assessment.get('container'),'scope':'original structural identification fixture','native':'NOT_RUN'}
            sources[family]=row
        source=sources['nes'];params={**p,'artifact_id':source['artifact_id']}
        described=api.dispatch('systems.nes_chr',{**params,'first_tile':16,'count':16})
        if not described.get('ok'):raise ValueError(str(described))
        schema=described['schema'];doc=api.dispatch('assets.inspect',{**params,'schema':schema})
        if not doc.get('ok'):raise ValueError(str(doc))
        before=doc['bitmaps'][0]['cells'][0]['pixels'];after=list(before);after[0]^=2
        edits={'schema_version':1,'document_id':doc['document_id'],'changes':[{'kind':'cell','bitmap_id':'nes-chr-page',
            'cell_index':0,'before_pixels':before,'after_pixels':after}],'acknowledged_consumers':[]}
        plan=api.dispatch('assets.plan',{**params,'schema':schema,'edits':edits})
        if not plan.get('ok'):raise ValueError(str(plan))
        build=api.dispatch('structured.apply',{**p,'plan_id':plan['workbench_plan_id']})
        if not build.get('ok'):raise ValueError(str(build))
        expected=bytearray(fixtures['nes']);expected[16+16384+16*16+8]^=0x80
        independent=Path(build['path']).read_bytes()==expected and Path(source['path']).read_bytes()==fixtures['nes']
        patch=api.dispatch('release.prepare',{**p,'source_id':source['artifact_id'],'target_id':build['artifact_id'],
            'title':'Original system fixture patch','description':'One literal NES CHR bit-plane change'})
        if not patch.get('ok'):raise ValueError(str(patch))
        patch_path,_=api.download(p['project_id'],patch['export']['export_id'])
        patch_ok=apply_bps(fixtures['nes'],patch_path.read_bytes())==expected
        report={'schema_version':1,'operation':'verify-v51-foundation','tool_version':ROMANCER_VERSION,'registry_version':'1',
            'ok':all(v['status']=='PASS' for v in families.values()) and independent and patch_ok,'status':'MEASURED',
            'families':families,'nes_edit':{'independent_bytes':'PASS' if independent else 'FAIL',
                'independent_patch':'PASS' if patch_ok else 'FAIL','source_sha256':source['sha256'],'target_sha256':hashlib.sha256(expected).hexdigest()},
            'runtime_verified':False,'full_game_compatibility_claimed':False,'release_status':'DEVELOPMENT',
            'credit':'By RetchEWretched','scope':'Five structural recognizers and one original NES CHR edit/build/patch; no native boot claim.'}
        return report
    finally:api.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--out',type=Path)
    args=parser.parse_args();report=verify_v51(args.workspace);encoded=(json.dumps(report,indent=2)+'\n').encode('utf-8')
    if args.out:publish_bytes(args.out,encoded)
    print(encoded.decode());return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
