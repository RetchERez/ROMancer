"""Frozen revision targets and evidence preflight, not semantic certification.

Imported reports cannot authorize edits or accept a revision. Actual authenticated
native observations, complete adapter inventories and independent acceptance are
separate requirements, not inferred from valid JSON or successful inspection.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
from .asset_schema import fields,label,number
from .script_schema import canonical_bytes,load_script_json

MANIFEST_PATH=Path(__file__).resolve().parents[1]/'knowledge/game_support.json'
TARGET_SET_ID='romancer-v1.0-initial-1039'
TARGET_COUNT=1039
TARGET_PIN='b3504635abb793c1870abaae7c003008688fbbe4385949e87d508cfc85d8ea6c'
SYSTEMS=('nes','snes','genesis','sms','gb','gbc')
OPERATIONS=frozenset(('inspect','noop','edit','undo_redo','reopen','native','patch'))


def _hash(value,length=64):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{'+str(length)+'}',value):
        raise ValueError('invalid coverage identity')


def validate_manifest(value):
    fields(value,'schema_version target_set_id targets')
    if type(value['schema_version']) is not int or value['schema_version']!=1 or value['target_set_id']!=TARGET_SET_ID:
        raise ValueError('unsupported coverage target set')
    rows=value['targets']
    if type(rows) is not list or len(rows)!=TARGET_COUNT:raise ValueError('coverage target set is incomplete')
    identities=[];seen=set();catalog=showcase=0
    for r in rows:
        fields(r,'sha256 system_id size labels origin');_hash(r['sha256'])
        if r['sha256'] in seen:raise ValueError('duplicate coverage target')
        seen.add(r['sha256']);number(r['size'],1,64*1024**2)
        if r['system_id'] not in SYSTEMS:raise ValueError('unsupported coverage system')
        if type(r['labels']) is not list or not 1<=len(r['labels'])<=16:raise ValueError('invalid coverage labels')
        for name in r['labels']:label(name,256)
        if type(r['origin']) is not list or not r['origin'] or any(type(v) is not str for v in r['origin']) or len(set(r['origin']))!=len(r['origin']) or not set(r['origin'])<={'catalog','showcase'}:
            raise ValueError('invalid coverage origin')
        catalog+='catalog' in r['origin'];showcase+='showcase' in r['origin']
        identities.append([r['sha256'],r['system_id'],r['size'],sorted(r['origin'])])
    identities.sort(key=lambda r:r[0])
    pin=hashlib.sha256(json.dumps(identities,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    if pin!=TARGET_PIN or catalog!=1035 or showcase!=6:raise ValueError('coverage target identities changed')
    return copy.deepcopy(rows)


def load_manifest():
    return validate_manifest(load_script_json(MANIFEST_PATH,max_bytes=1024**2))


def status(query='',system_filter='all',page=0,limit=25):
    label(query,128,blank=True);number(page,0,1039);number(limit,1,100)
    if system_filter not in ('all',*SYSTEMS):raise ValueError('unsupported coverage filter')
    rows=load_manifest()
    from .verified_games import PROFILES
    legacy={r['sha256']:r['id'] for r in PROFILES}
    filtered=[r for r in rows if (system_filter=='all' or r['system_id']==system_filter)
              and (query.casefold() in ' '.join(r['labels']).casefold() or query.lower() in r['sha256'])]
    filtered.sort(key=lambda r:(r['labels'][0].casefold(),r['sha256']))
    result=[{**r,'status':'not_verified','full_editing_verified':False,'limited_profile':legacy.get(r['sha256'])}
            for r in filtered[page*limit:(page+1)*limit]]
    return {'ok':True,'target_set_id':TARGET_SET_ID,'target_set_sha256':TARGET_PIN,
            'target_count':TARGET_COUNT,'catalog_count':1035,'additional_showcase_count':4,
            'accepted_count':0,'release_ready':False,'write_authorized':False,
            'total':len(filtered),'page':page,'limit':limit,'revisions':result,
            'scope':'Exact target inventory. Catalog, boot, declared layouts and report preflight do not establish full editing acceptance.',
            'acceptance_stage':'Awaiting complete adapters, authenticated native evidence and independent revision acceptance.'}


def assess_evidence(target,inventory,context,candidate):
    """Check a batch against an independently supplied expected resource inventory.

    This is completeness/currentness preflight only. Matching artifact hashes and
    claimed outcomes must still be authenticated and checked against real artifacts
    by their producing services. A ready batch cannot certify its source revision.
    """
    canonical_bytes([target,inventory,context,candidate],max_bytes=4*1024**2)
    fields(target,'sha256 system_id size labels origin');_hash(target['sha256'])
    fields(context,'romancer_commit adapter_sha256');_hash(context['romancer_commit'],40);_hash(context['adapter_sha256'])
    fields(inventory,'source_sha256 adapter_sha256 resources unresolved')
    fields(candidate,'source_sha256 romancer_commit adapter_sha256 proofs')
    for r in (inventory,candidate):_hash(r['source_sha256']);_hash(r['adapter_sha256'])
    _hash(candidate['romancer_commit'],40)
    if type(inventory['resources']) is not list or not 1<=len(inventory['resources'])<=2048:
        raise ValueError('expected resource batch exceeds bounds')
    if type(inventory['unresolved']) is not list or len(inventory['unresolved'])>2048:raise ValueError('invalid unresolved inventory')
    for reason in inventory['unresolved']:label(reason,512)
    if type(candidate['proofs']) is not list or len(candidate['proofs'])>8192:raise ValueError('proof batch exceeds bounds')
    issues=[];expected=set();resources=set()
    for resource in inventory['resources']:
        fields(resource,'id operations');label(resource['id'],128)
        if resource['id'] in resources:raise ValueError('duplicate expected resource')
        resources.add(resource['id'])
        ops=resource['operations']
        if type(ops) is not list or not ops or len(ops)>len(OPERATIONS) or any(type(op) is not str or op not in OPERATIONS for op in ops) or len(set(ops))!=len(ops):
            raise ValueError('invalid expected operations')
        expected.update((resource['id'],op) for op in ops)
    if len(expected)>8192:raise ValueError('expected proof budget exceeded')
    if inventory['unresolved']:issues.append('Expected inventory still has unresolved resources or consumers.')
    if inventory['source_sha256']!=target['sha256'] or candidate['source_sha256']!=target['sha256']:
        issues.append('Source revision differs from the expected target.')
    if inventory['adapter_sha256']!=context['adapter_sha256'] or candidate['adapter_sha256']!=context['adapter_sha256'] or candidate['romancer_commit']!=context['romancer_commit']:
        issues.append('Adapter or application evidence is stale.')
    seen=set()
    for proof in candidate['proofs']:
        fields(proof,'resource_id operation source_sha256 romancer_commit adapter_sha256 evidence_sha256 result origin')
        label(proof['resource_id'],128);label(proof['operation'],64)
        for name in ('source_sha256','adapter_sha256','evidence_sha256'):_hash(proof[name])
        _hash(proof['romancer_commit'],40)
        label(proof['result'],64);label(proof['origin'],64)
        key=(proof['resource_id'],proof['operation'])
        if key in seen:issues.append('Duplicate proof for a resource operation.')
        seen.add(key)
        if key not in expected:issues.append('Proof does not belong to the expected resource inventory.')
        if proof['source_sha256']!=target['sha256'] or proof['adapter_sha256']!=context['adapter_sha256'] or proof['romancer_commit']!=context['romancer_commit']:
            issues.append('Proof is bound to a different source, adapter or application.')
        if proof['origin']!='commercial' or proof['result']!='pass':
            issues.append('A synthetic, inconclusive, failed or unreviewed N/A claim cannot cover a commercial resource.')
    missing=sorted(expected-seen)
    if missing:issues.append('Expected resource operations have no proof.')
    return {'ok':True,'source_sha256':target['sha256'],'ready_for_review':not issues,
            'accepted':False,'write_authorized':False,'requires_independent_review':True,
            'expected_operations':len(expected),'reported_operations':len(seen),
            'missing_operations':[{'resource_id':r,'operation':op} for r,op in missing],
            'issues':sorted(set(issues)),
            'scope':'Batch metadata preflight only; proof authenticity, artifact contents, game semantics and full inventory completeness are not certified.'}
