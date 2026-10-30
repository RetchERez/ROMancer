"""Pinned, read-only corpus relationships. Similar bytes never authorize edits."""
import copy
import functools
import hashlib
import json
from pathlib import Path
import re
from .asset_schema import fields, label, number
from .script_schema import _unique_object, _nonfinite

DATABASE_PATH=Path(__file__).resolve().parents[1]/'knowledge/corpus_evidence.json'
DATABASE_PIN='f1f65c7f13c372f7bb6bbc5cec92c51bf567bb4cfef6669235454a4451c451d9'
IDENTITY_PIN='0bbda17287ad0d324fc405014d2f0837ffd73c2544b1f73c84ef158c861dd370'
MAX_DATABASE=8*1024**2


def _hash(value,length=64):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{'+str(length)+'}',value):
        raise ValueError('Invalid corpus evidence identity.')


def validate_database(data):
    fields(data,'schema_version source_count source_identity_sha256 provenance records')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or type(data['source_count']) is not int or data['source_count']!=1052:
        raise ValueError('Unsupported corpus evidence inventory.')
    rows=data['records']
    if type(rows) is not list or len(rows)!=1052:raise ValueError('Incomplete corpus evidence inventory.')
    by={}
    for r in rows:
        fields(r,'sha256 size system_id label related samples references driver_candidates')
        _hash(r['sha256']);number(r['size'],1,64*1024**2);label(r['label'],256)
        if r['sha256'] in by:raise ValueError('Duplicate corpus source.')
        if r['system_id'] not in ('nes','snes','genesis','sms','gb','gbc'):raise ValueError('Unsupported corpus system.')
        by[r['sha256']]=r
    identities=sorted([[r['sha256'],r['system_id'],r['size']] for r in rows])
    pin=hashlib.sha256(json.dumps(identities,separators=(',',':')).encode()).hexdigest()
    if pin!=IDENTITY_PIN or data['source_identity_sha256']!=pin:raise ValueError('Corpus source set changed.')
    from .game_coverage import load_manifest
    if identities!=sorted([[r['sha256'],r['system_id'],r['size']] for r in load_manifest()]):
        raise ValueError('Corpus evidence differs from the coverage inventory.')
    for r in rows:
        for name,maximum in (('related',1051),('samples',2048),('references',32),('driver_candidates',20)):
            if type(r[name]) is not list or len(r[name])>maximum:raise ValueError('Corpus evidence exceeds bounds.')
        seen=set()
        for e in r['related']:
            fields(e,'sha256 shared_file_bytes sound_contexts loaded_blocks sample_streams locations')
            other=by.get(e['sha256'])
            if other is None or other is r or e['sha256'] in seen:raise ValueError('Invalid related source.')
            seen.add(e['sha256'])
            # GB and GBC share an instruction set; other systems stay separate.
            if other['system_id']!=r['system_id'] and {other['system_id'],r['system_id']}!={'gb','gbc'}:
                raise ValueError('Cross-architecture corpus relationship.')
            for key in ('shared_file_bytes','sound_contexts','loaded_blocks','sample_streams'):
                number(e[key],0,64*1024**2)
            if e['shared_file_bytes']%128 or e['shared_file_bytes']>min(r['size'],other['size']):raise ValueError('Invalid shared-byte count.')
            if not any(e[key] for key in ('shared_file_bytes','sound_contexts','loaded_blocks','sample_streams')):raise ValueError('Empty relationship.')
            if type(e['locations']) is not list or len(e['locations'])>2:raise ValueError('Too many example locations.')
            for loc in e['locations']:
                fields(loc,'offset other_offset length hash');_hash(loc['hash'],32)
                if type(loc['length']) is not int or loc['length']!=128:raise ValueError('Invalid shared block length.')
                number(loc['offset'],0,r['size']-128);number(loc['other_offset'],0,other['size']-128)
        for sample in r['samples']:
            fields(sample,'offset length sha256');_hash(sample['sha256'])
            number(sample['offset'],0,r['size']-1);number(sample['length'],1,r['size']-sample['offset'])
        for ref in r['references']:
            fields(ref,'id scope dump_status additional_inputs nonlinear board');label(ref['id'],128);label(ref['board'],256,blank=True)
            if ref['scope'] not in ('file','prg_chr') or ref['dump_status'] not in ('good','baddump','nodump','unknown') or type(ref['nonlinear']) is not bool:raise ValueError('Invalid reference scope.')
            if (ref['scope']=='prg_chr')!=(r['system_id']=='nes'):raise ValueError('Reference scope differs from source system.')
            number(ref['additional_inputs'],0,64)
        for name in r['driver_candidates']:label(name,64)
    if type(data['provenance']) is not list or not 1<=len(data['provenance'])<=32:raise ValueError('Missing corpus provenance.')
    for p in data['provenance']:
        fields(p,'file sha256');label(p['file'],128);_hash(p['sha256'])
    return by


def fingerprint():
    if DATABASE_PATH.stat().st_size>MAX_DATABASE:raise ValueError('Corpus evidence database exceeds bounds.')
    return hashlib.sha256(DATABASE_PATH.read_bytes()).hexdigest()


@functools.lru_cache(maxsize=1)
def _load(path,pin):
    if pin!=DATABASE_PIN:raise ValueError('Corpus evidence database changed; use a checked build.')
    raw=Path(path).read_bytes()
    if len(raw)>MAX_DATABASE or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Corpus evidence changed while reading.')
    try:data=json.loads(raw,object_pairs_hook=_unique_object,parse_constant=_nonfinite)
    except (RecursionError,UnicodeError) as error:raise ValueError('Invalid corpus evidence JSON.') from error
    return validate_database(data)


def lookup(source_sha256,size):
    _hash(source_sha256);number(size,1,64*1024**2)
    by=_load(str(DATABASE_PATH),fingerprint())
    source=by.get(source_sha256)
    if source and source['size']!=size:raise ValueError('Corpus evidence size differs from selected source.')
    record=copy.deepcopy(source) if source else None
    total=len(record['related']) if record else 0
    sample_total=len(record['samples']) if record else 0
    if record:
        record['related']=record['related'][:8]
        record['samples']=record['samples'][:8]
        for e in record['related']:e['label']=by[e['sha256']]['label']
    return {'ok':True,'status':'RECORDED_SOURCE_EVIDENCE' if record else 'NO_RECORDED_SOURCE_EVIDENCE',
            'source_sha256':source_sha256,'source_count':len(by),'record':record,
            'related_total':total,'sample_total':sample_total,'related_limit':8,'sample_limit':8,
            'database_sha256':DATABASE_PIN,'write_authorized':False,'full_editing_verified':False,
            'scope':'Exact byte relationships and bounded observations are investigation inputs, not shared game-format or editing proof. Reference matches describe named file inputs; NES comparisons exclude the container header. Additional reference inputs do not establish selected-core firmware requirements.'}
