"""Whole-product checks on two original fixture variants per focus system."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from romancer import ROMANCER_VERSION
from romancer.boot_fixtures import make_boot_fixture
from romancer.workbench_api import WorkbenchAPI
from romancer.resource_compression import encode_stream,decode_stream
from romancer.streaming_bps import apply_patch


def checksum(raw,system):
    raw=bytearray(raw)
    if system=='snes':
        raw[0x7fdc:0x7fe0]=b'\xff\xff\0\0';value=sum(raw)&65535;raw[0x7fdc:0x7fe0]=(value^65535).to_bytes(2,'little')+value.to_bytes(2,'little')
    if system=='genesis':raw[0x18e:0x190]=(sum(int.from_bytes(raw[i:i+2],'big') for i in range(0x200,len(raw),2))&65535).to_bytes(2,'big')
    if system=='gb':
        raw[0x14d]=(-sum(raw[0x134:0x14d])-25)&255;raw[0x14e:0x150]=b'\0\0';raw[0x14e:0x150]=(sum(raw)&65535).to_bytes(2,'big')
    if system=='gba':raw[0xbd]=(-sum(raw[0xa0:0xbd])-0x19)&255
    return bytes(raw)


def verify(root,cores=None,restore=True):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);results=[]
    def call(api,operation,params):
        result=api.dispatch(operation,params)
        if not result.get('ok'):raise ValueError(operation+': '+str(result))
        return result
    for system in ('nes','snes','genesis','gb','gba'):
        for variant in (0,1):
            folder=root/(system+'-'+str(variant));folder.mkdir();fixture=make_boot_fixture(system);raw=bytearray(fixture['data'])
            raw[0x3000:0x3010]=(b'HELLO' if not variant else b'WORLD!')+b'\0'+b'\xff'*(10 if not variant else 9)
            value=100+variant*50;raw[0x3020:0x3024]=value.to_bytes(2,'little')+(value+10).to_bytes(2,'little')
            codec='gba-lz10' if not variant else 'gba-rle';decoded=b'PACKED\0'+b'\xff'*9;stream=encode_stream(decoded,codec);raw[0x3040:0x3080]=stream+b'\0'*(64-len(stream))
            original=checksum(raw,system);source=folder/('original'+fixture['suffix']);source.write_bytes(original);expected=bytearray(original)
            api=WorkbenchAPI(folder/'workspace')
            try:
                project=call(api,'project.create',{'name':system+' variant '+str(variant)});p={'project_id':project['project_id']}
                owned=call(api,'source.import',{**p,'path':str(source),'system':None});params={**p,'artifact_id':owned['artifact_id']}
                if owned['system_id']!=system:raise ValueError('variant recognition failed')
                scan=call(api,'resources.discover',{**params,'config':{'system_id':system,'start':0x3000,'length':128,'kinds':['text','compression'],'target':None}})
                if not scan['candidates']:raise ValueError('discovery found no original resources')
                table={'schema_version':1,'name':'Original values','offset':0x3020,'count':2,'stride':2,'fields':[{'name':'Value','offset':0,'type':'u16','endian':'little','pointer_base':None}]}
                call(api,'tables.save_definition',{**params,'definition':table})
                declared=call(api,'resources.declare_script',{**params,'config':{'system_id':system,'offset':0x3000,'capacity':16,'count':1}});doc=declared['inspection']
                request={'schema_version':1,**{k:doc[k] for k in ('document_id','source_sha256','schema_sha256')},'changes':[{'record_id':'line-0','segment':0,'text':'ROMANCER'}]}
                plan=call(api,'script.plan',{**params,'schema':declared['schema'],'edits':request});built=call(api,'structured.apply',{**p,'plan_id':plan['workbench_plan_id']});params['artifact_id']=built['artifact_id']
                expected[0x3000:0x3010]=b'ROMANCER\0'+b'\xff'*7
                if Path(built['path']).read_bytes()!=checksum(expected,system):raise ValueError('complete text output oracle differs')
                call(api,'resources.reuse_definitions',params);doc=call(api,'tables.inspect',{**params,'definition':table,'page':0,'limit':50})
                plan=call(api,'tables.plan',{**params,'definition':table,'document_id':doc['document_id'],'changes':[{'row':1,'field':'Value','before':value+10,'after':value+17}]})
                recipe=call(api,'recipes.from_plan',{**params,'plan_id':plan['plan_id'],'name':'Add seven'})['recipe'];a=call(api,'recipes.preview',{**params,'recipe':recipe});b=call(api,'recipes.preview',{**params,'recipe':recipe})
                if a['plan_id']!=b['plan_id']:raise ValueError('recipe replay is not deterministic')
                built=call(api,'build.apply',{**p,'plan_id':a['plan_id']});params['artifact_id']=built['artifact_id'];expected[0x3022:0x3024]=(value+17).to_bytes(2,'little')
                if Path(built['path']).read_bytes()!=checksum(expected,system):raise ValueError('complete table output oracle differs')
                call(api,'resources.reuse_definitions',params)
                definition=call(api,'definitions.export',{**params,'kind':'tables'});file,_=api.download(p['project_id'],definition['export']['export_id']);call(api,'definitions.import',{**params,'document':json.loads(file.read_bytes())})
                extracted=call(api,'compression.extract',{**params,'offset':0x3040,'allocation':64,'codec':codec})['artifact'];changed=b'EDITED\0'+b'\xff'*9
                edit=call(api,'bytes.plan',{**p,'artifact_id':extracted['artifact_id'],'edits':[{'offset':0,'before':decoded.hex(),'after':changed.hex()}]});edited=call(api,'build.apply',{**p,'plan_id':edit['plan_id']})
                plan=call(api,'compression.plan_reinsert',{**p,'parent_id':params['artifact_id'],'decoded_id':extracted['artifact_id'],'edited_id':edited['artifact_id'],'offset':0x3040,'allocation':64,'codec':codec});final=call(api,'build.apply',{**p,'plan_id':plan['plan_id']})
                finalraw=Path(final['path']).read_bytes();decoded_result=decode_stream(finalraw[0x3040:0x3080],codec)['data']
                if decoded_result!=changed:raise ValueError('compressed result decoded bytes differ')
                expected[0x3040:0x3080]=finalraw[0x3040:0x3080]
                if finalraw!=checksum(expected,system) or source.read_bytes()!=original:raise ValueError('complete final output or original preservation differs')
                patch=call(api,'release.prepare',{**p,'source_id':owned['artifact_id'],'target_id':final['artifact_id'],'title':'Original '+system,'description':'1.0 complete workflow'})
                export=next(row for row in api.exports(api.project(p)) if row['role']=='patch');call(api,'release.verify',{**p,'export_id':export['export_id'],'source_id':owned['artifact_id']})
                patchfile,_=api.download(p['project_id'],export['export_id']);rebuilt=folder/('reconstructed'+fixture['suffix']);apply_patch(Path(owned['path']),patchfile,rebuilt)
                if rebuilt.read_bytes()!=finalraw:raise ValueError('independent BPS reconstruction differs')
                native=None
                if cores:
                    core=cores[system];call(api,'runtime.load',{**p,'artifact_id':final['artifact_id'],'core':core['core'],'options':core.get('options',{})})
                    packet=None
                    for _ in range(40):packet=call(api,'runtime.step',{**p,'frames':3,'buttons':[],'port':0})
                    rgb=base64.b64decode(packet['frame']['rgb24_base64'],validate=True)
                    if hashlib.sha256(rgb).hexdigest()!=packet['frame']['sha256']:raise ValueError('live frame identity differs')
                    samples=base64.b64decode(packet['audio']['pcm_s16le_base64'],validate=True)
                    if len(samples)!=packet['audio']['captured_frames']*4 or not packet['audio']['complete']:raise ValueError('live PCM packet incomplete')
                    state=call(api,'runtime.save_state',p);call(api,'runtime.load_state',{**p,'snapshot_id':state['snapshot_id']});closed=call(api,'runtime.close',p)
                    native={'width':packet['frame']['width'],'height':packet['frame']['height'],'fps':packet['timing']['fps'],'sample_rate':packet['audio']['sample_rate'],'last_packet_samples':packet['audio']['captured_frames'],'sample_bytes_nonzero':any(samples),'state_restored':True,'worker_exit_code':closed['worker_exit_code']}
                backup=folder/'project-backup.zip';call(api,'project.backup',{**p,'destination':str(backup),'roles':['sources','builds','reports','sessions','captures']})
                restored=False
                if restore:
                    other=WorkbenchAPI(folder/'restored-workspace')
                    try:
                        result=call(other,'project.restore',{'archive':str(backup)});opened=call(other,'project.open',{'project_id':result['project_id']});restored=bool(opened['builds'])
                        row=next(r for r in opened['builds'] if r['artifact_id']==final['artifact_id'])
                        if Path(row['path']).read_bytes()!=finalraw:raise ValueError('restored final build differs')
                    finally:other.close()
                results.append({'system_id':system,'variant':variant,'source_sha256':owned['sha256'],'target_sha256':final['sha256'],'text_table_compression_complete_oracle':True,'recipe_replay':True,'definition_roundtrip':True,'bps_reconstructed':True,'backup_restored':restored,'native':native})
            finally:api.close()
    return {'ok':True,'version':ROMANCER_VERSION,'credit':'By RetchEWretched','workflows':results,'scope':'Two original minimal fixture variants per focus system; no universal game compatibility claim.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cores',type=Path);parser.add_argument('--work-dir',type=Path);parser.add_argument('--skip-restore',action='store_true');args=parser.parse_args()
    directory=args.work_dir or Path(tempfile.mkdtemp(prefix='romancer-v1-'));directory.mkdir(parents=True,exist_ok=True)
    result=verify(directory,json.loads(args.cores.read_text(encoding='utf-8')) if args.cores else None,not args.skip_restore)
    args.output.write_bytes((json.dumps(result,indent=2)+'\n').encode('utf-8'));print(json.dumps({'ok':True,'workflows':len(result['workflows'])}))
