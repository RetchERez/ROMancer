"""Reviewed BPS/IPS imports. Patch targets retain the author's exact bytes."""
import hashlib
from pathlib import Path
import re
import uuid
import zlib
from . import workbench_projects as p
from .assets import checked_path,digest
from .asset_schema import label
from .binary_tools import compare_files
from .script_schema import load_script_json
from .workbench_files import input_file,register_completed_build,read_bounded

MAX_IPS_IMAGE=64*1024**2


def decode_ips(original,patch,*,cancelled=lambda:False):
    if type(original) is not bytes or type(patch) is not bytes or max(len(original),len(patch))>MAX_IPS_IMAGE:
        raise ValueError('IPS inputs must fit the 64 MiB limit.')
    if not patch.startswith(b'PATCH'):raise ValueError('Not an IPS patch.')
    output=bytearray(original);position=5;records=0
    while True:
        if cancelled():raise KeyboardInterrupt
        if position+3>len(patch):raise ValueError('Truncated IPS record or missing EOF.')
        token=patch[position:position+3];position+=3
        if token==b'EOF':
            remaining=len(patch)-position
            if remaining not in (0,3):raise ValueError('Unexpected bytes after IPS EOF.')
            if remaining:
                size=int.from_bytes(patch[position:],'big')
                if size<len(output):del output[size:]
                else:output.extend(b'\0'*(size-len(output)))
            return bytes(output)
        records+=1
        if records>65536 or position+2>len(patch):raise ValueError('IPS record budget exceeded or record truncated.')
        offset=int.from_bytes(token,'big');length=int.from_bytes(patch[position:position+2],'big');position+=2
        if length:
            if position+length>len(patch):raise ValueError('Truncated IPS literal.')
            raw=patch[position:position+length];position+=length
        else:
            if position+3>len(patch):raise ValueError('Truncated IPS run.')
            length=int.from_bytes(patch[position:position+2],'big');value=patch[position+2];position+=3
            if not length:raise ValueError('An IPS run cannot be empty.')
            raw=bytes([value])*length
        if offset+length>MAX_IPS_IMAGE:raise ValueError('IPS output exceeds 64 MiB.')
        if offset+length>len(output):output.extend(b'\0'*(offset+length-len(output)))
        output[offset:offset+length]=raw


def _reference(path,reference,required,cancelled):
    if type(reference) is not str or len(reference)>80:raise ValueError('Enter a CRC32 or SHA256 reference for the original file.')
    reference=reference.strip().lower()
    if not reference:
        if required:raise ValueError('IPS cannot identify its original. Enter the patch author’s expected CRC32 or SHA256 first.')
        return 'embedded BPS checksums'
    reference=re.sub(r'^(crc32|sha256):','',reference)
    if not re.fullmatch('[0-9a-f]{8}|[0-9a-f]{64}',reference):raise ValueError('Use 8 hexadecimal CRC32 digits or 64 SHA256 digits for the full original file.')
    sha=hashlib.sha256();crc=0
    with path.open('rb') as stream:
        while raw:=stream.read(65536):
            if cancelled():raise KeyboardInterrupt
            sha.update(raw);crc=zlib.crc32(raw,crc)
    measured=f'{crc:08x}' if len(reference)==8 else sha.hexdigest()
    if reference!=measured:raise ValueError('Original checksum mismatch. Choose the revision named by the patch author.')
    return 'CRC32 reference' if len(reference)==8 else 'SHA256 reference'


def preview_patch(project,artifact_id,input_id,expected_reference,*,cancelled=lambda:False):
    project=checked_path(Path(project))
    with p.locked(project):
        row=p.artifact(project,artifact_id);source=Path(row['path']);p._measure(source,row,cancelled=cancelled)
        imported,patch=input_file(project,input_id,'patch')
        with patch.open('rb') as stream:magic=stream.read(5)
        format='BPS' if magic[:4]==b'BPS1' else 'IPS' if magic==b'PATCH' else None
        if format is None:raise ValueError('Choose a BPS or IPS patch; the extension alone is not enough.')
        reference=_reference(source,expected_reference,format=='IPS',cancelled)
        folder=checked_path(project/'patch-previews');folder.mkdir(exist_ok=True)
        if len(list(folder.iterdir()))>=64:raise ValueError('This project has 64 patch previews. Apply or archive earlier work before importing more.')
        target=folder/(uuid.uuid4().hex+'.bin');created=False
        try:
            if format=='BPS':
                from .streaming_bps import apply_patch
                apply_patch(source,patch,target,cancelled=cancelled);created=True
            else:
                if row['size']>MAX_IPS_IMAGE:raise ValueError('Use BPS for originals larger than 64 MiB.')
                raw=decode_ips(read_bounded(source,MAX_IPS_IMAGE,row,cancelled=cancelled),
                               read_bounded(patch,MAX_IPS_IMAGE,imported,cancelled=cancelled),cancelled=cancelled)
                with target.open('xb') as out:created=True;out.write(raw)
            measured=p._measure(target,cancelled=cancelled)
            if not measured['size']:raise ValueError('The patch would create an empty file.')
            p._measure(source,row,cancelled=cancelled);p._measure(patch,imported,cancelled=cancelled)
            summary=compare_files(source,target,cancelled=cancelled)
            plan={'kind':'patch-import','source_id':artifact_id,'source_sha256':row['sha256'],
                  'input_id':input_id,'patch_sha256':imported['sha256'],'format':format,'reference':reference,
                  'preview':target.relative_to(project).as_posix(),'target':measured,**summary}
            plan_id=digest(plan);p.write_json(project/'plans'/(plan_id+'.json'),plan)
            return {'ok':True,'status':'READY_TO_APPLY','project_id':project.name,'plan_id':plan_id,'source_id':artifact_id,
                    'source_sha256':row['sha256'],'target_sha256':measured['sha256'],'format':format,
                    'reference':reference,**summary}
        except BaseException:
            if created:target.unlink(missing_ok=True)
            raise


def apply_preview(project,plan_id,name,*,cancelled=lambda:False):
    project=checked_path(Path(project));p.identifier(plan_id);label(name,120)
    plan=load_script_json(project/'plans'/(plan_id+'.json'),max_bytes=1024**2)
    if plan.get('kind')!='patch-import' or digest(plan)!=plan_id:raise ValueError('Patch preview identity changed. Preview the patch again.')
    row=p.artifact(project,plan['source_id']);p._measure(row['path'],row,cancelled=cancelled)
    if row['sha256']!=plan['source_sha256']:raise ValueError('Patch preview belongs to another original.')
    imported,patch=input_file(project,plan['input_id'],'patch')
    if imported['sha256']!=plan['patch_sha256']:raise ValueError('Patch changed after preview.')
    existing=next((r for r in p.read_project(project)['builds'] if r.get('plan_id')==plan_id),None)
    if existing is not None:
        p._measure(existing['path'],plan['target'],cancelled=cancelled)
        return {'ok':True,'status':'BUILT','already_applied':True,'original_preserved':True,**existing}
    preview=checked_path(project/plan['preview'])
    if preview.parent!=project/'patch-previews':raise ValueError('Patch preview escaped project storage.')
    p._measure(preview,plan['target'],cancelled=cancelled)
    if cancelled():raise KeyboardInterrupt
    target=project/'builds'/(uuid.uuid4().hex+Path(row['path']).suffix)
    p._publish_copy(preview,target,plan['target'],cancelled=cancelled)
    result=register_completed_build(project,row['artifact_id'],target,plan_id,'imported-'+plan['format'].lower(),name,
                                    expected_parent_sha256=plan['source_sha256'],expected_output=plan['target'])
    try:
        p._measure(preview,plan['target']);preview.unlink()
    except (ValueError,OSError):result['preview_retained']=True
    return result
