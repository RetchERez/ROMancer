"""Bounded saved observation ranges and explicit before/after byte comparisons."""
import hashlib
import json
import re
from .asset_schema import fields,label,number
from .script_schema import canonical_bytes


def validate_watches(watches):
    watches=json.loads(canonical_bytes(watches,max_bytes=16384))
    if type(watches) is not list or len(watches)>32:raise ValueError('save at most 32 memory watches')
    names=set()
    for watch in watches:
        fields(watch,'name region offset length');label(watch['name'],64)
        if watch['name'].casefold() in names:raise ValueError('watch names must be unique')
        names.add(watch['name'].casefold());number(watch['region'],0,3);number(watch['offset'],0,64*1024**2);number(watch['length'],1,256)
    return watches


def compare_watch(before,after):
    before=json.loads(canonical_bytes(before,max_bytes=32768));after=json.loads(canonical_bytes(after,max_bytes=32768))
    binding=('worker_session_id','epoch','region','region_size','offset','length','game_sha256','core_sha256','core_options')
    if any(key not in before or key not in after or before[key]!=after[key] for key in binding):raise ValueError('memory snapshots belong to different sessions or ranges')
    if type(before.get('sequence')) is not int or type(after.get('sequence')) is not int or after['sequence']<=before['sequence']:raise ValueError('capture a newer observation for comparison')
    arrays=[]
    for row in (before,after):
        number(row['length'],1,256);number(row['offset'],0,64*1024**2)
        if type(row.get('raw_hex')) is not str or not re.fullmatch('[0-9a-f]{'+str(row['length']*2)+'}',row['raw_hex']):raise ValueError('invalid memory bytes')
        raw=bytes.fromhex(row['raw_hex'])
        if hashlib.sha256(raw).hexdigest()!=row.get('data_sha256'):raise ValueError('memory snapshot hash differs')
        arrays.append(raw)
    return {'ok':True,'status':'COMPARED','changes':[{'offset':before['offset']+i,'before':a,'after':b} for i,(a,b) in enumerate(zip(*arrays)) if a!=b],
            'write_event_observed':False,'note':'Byte differences between observations; no instruction or write event is inferred.'}
