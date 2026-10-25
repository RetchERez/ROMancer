"""Verified fixed-size asset publication; unselected bytes stay exact."""
import hashlib
import os
from pathlib import Path
import tempfile
from . import assets
from .cd_patch import check_output_paths


def apply_assets(source: Path, destination: Path, schema: dict, edits: dict,
                 *, expected_plan_id: str, protected_inputs: tuple[Path,...]=()) -> dict:
    result={'schema_version':1,'operation':'asset-apply','ok':False,'status':'BLOCKED','written':False,'publication_status':'NOT_PUBLISHED'}
    temporary=None;temporary_info=None
    try:
        destination=assets.checked_path(destination)
        check_output_paths(source,[destination])
        for path in protected_inputs:check_output_paths(path,[destination])
        if not destination.parent.is_dir() or destination.exists():raise ValueError('destination parent must exist and output must be new')
        parent_info=destination.parent.stat()
        with assets._asset_source(source,schema) as held:
            plan=assets._compile_assets(held.document,held.checked_schema,edits)
            result.update(source_sha256=held.document['source_sha256'],document_id=held.document['document_id'],plan_id=plan['plan_id'])
            if not plan['ok']:raise ValueError(plan.get('error','asset plan blocked'))
            if expected_plan_id!=plan['plan_id']:raise ValueError('reviewed asset plan is stale')
            if not plan['hunks']:return {**result,'ok':True,'status':'NO_CHANGES'}
            assets._bounded({**plan,'diagnostic_reserve':' '*8192})
            descriptor,name=tempfile.mkstemp(prefix='.romancer-assets-',dir=destination.parent)
            temporary=Path(name);temporary_info=temporary.stat()
            with os.fdopen(descriptor,'wb') as output:
                held.stream.seek(0);offset=0
                while data:=held.stream.read(65536):
                    edited=bytearray(data)
                    for hunk in plan['hunks']:
                        replacement=bytes.fromhex(hunk['after_hex']);left=max(offset,hunk['offset']);right=min(offset+len(data),hunk['offset']+len(replacement))
                        if left<right:edited[left-offset:right-offset]=replacement[left-hunk['offset']:right-hunk['offset']]
                    output.write(edited);offset+=len(data)
                output.flush();os.fsync(output.fileno())
            # Verify every byte using an independent cursor over approved hunks.
            held.stream.seek(0);hasher=hashlib.sha256();position=0
            allowed={h['offset']+index:(before,after,mask) for h in plan['hunks']
                     for index,(before,after,mask) in enumerate(zip(bytes.fromhex(h['before_hex']),bytes.fromhex(h['after_hex']),bytes.fromhex(h['writable_mask_hex'])))}
            with temporary.open('rb') as output:
                while before:=held.stream.read(65536):
                    after=output.read(len(before))
                    if len(after)!=len(before):raise ValueError('output length mismatch')
                    for index,(old,new) in enumerate(zip(before,after)):
                        authority=allowed.get(position+index)
                        if authority is None:
                            if old!=new:raise ValueError('unselected asset data changed')
                        elif old!=authority[0] or new!=authority[1] or (old^new)&~authority[2]:
                            raise ValueError('output differs from approved asset bits')
                    hasher.update(after);position+=len(before)
                if output.read(1):raise ValueError('output grew')
                output.seek(0)
                # Decode final graph independently; source binding is retained separately.
                assets._inspect_stream(output,held.checked_schema)
            if position!=held.document['source_size']:raise ValueError('output size changed')
            assets._recheck_asset_source(held)
            if not os.path.samestat(temporary.stat(),temporary_info) or not os.path.samestat(destination.parent.stat(),parent_info):
                raise ValueError('temporary output or parent identity changed')
            with temporary.open('rb') as output:
                if assets.hash_stream(output)!=hasher.hexdigest():raise ValueError('temporary output changed after verification')
            result.update(output_sha256=hasher.hexdigest(),output_path=str(destination),output_verified=True)
            os.link(temporary,destination)
            result.update(ok=True,status='APPLIED',written=True,publication_status='PUBLISHED')
        return result
    except (ValueError,OSError,KeyError,TypeError,KeyboardInterrupt) as exc:
        return {**result,'ok':False,'status':'CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED','error':str(exc)[:2048],'error_code':type(exc).__name__}
    finally:
        if temporary is not None:
            try:
                if os.path.samestat(temporary.stat(),temporary_info):temporary.unlink()
            except OSError:pass
