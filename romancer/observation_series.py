"""Bounded format hypotheses from owned observations, without game profiles.

Matching an observed number is correlation. It establishes neither a meaning,
the CPU bus address of an exposed buffer, nor which instruction wrote it.
"""
import hashlib
from bisect import bisect_right
from .asset_schema import label,number
from .script_schema import canonical_bytes
from .value_search import _snapshot,BINDING

RELATIONS=frozenset(('initial','changed','unchanged','increased','decreased','delta'))


def validate_observations(observations,minimum=2):
    if type(observations) is not list or not minimum<=len(observations)<=32:
        raise ValueError('record between '+str(minimum)+' and 32 observations')
    rows=[];first=None;previous=0
    for index,row in enumerate(observations):
        if type(row) is not dict or set(row)!={'snapshot','label','value','relation','delta'}:
            raise ValueError('invalid investigation observation')
        label(row['label'],120)
        if row['value'] is not None:number(row['value'],-2**31,2**32-1)
        if row['delta'] is not None:number(row['delta'],-2**32,2**32)
        if row['relation'] not in RELATIONS or (index==0)!=(row['relation']=='initial'):
            raise ValueError('choose a valid observation relation')
        if (row['relation']=='delta')!=(row['delta'] is not None):
            raise ValueError('supply an integer change only for the delta relation')
        packet,raw=_snapshot(row['snapshot'])
        if first is not None and any(first[k]!=packet[k] for k in BINDING):
            raise ValueError('source, session, state, core or memory range changed; start a new investigation')
        if packet['sequence']<=previous:raise ValueError('capture a newer memory observation')
        first=first or packet;previous=packet['sequence'];rows.append((row,packet,raw))
    return rows


def _read(raw,width,endian,signed,encoding):
    if encoding=='binary':return int.from_bytes(raw,endian,signed=signed)
    value=0
    for byte in (raw if endian=='big' else reversed(raw)):
        high,low=byte>>4,byte&15
        if high>9 or low>9:return None
        value=value*100+high*10+low
    return value


def analyze_series(observations,*,max_results=200,cancelled=lambda:False):
    number(max_results,1,500);rows=validate_observations(observations)
    if cancelled():raise KeyboardInterrupt
    first=rows[0][1];known=[row['value'] for row,_,_ in rows if row['value'] is not None]
    controls=sum(row['relation']=='unchanged' for row,_,_ in rows[1:])
    result={'ok':True,'status':'ANALYZED','source_sha256':first['game_sha256'],
        'region':first['region'],'offset':first['offset'],'length':first['length'],
        'observation_count':len(rows),'unchanged_controls':controls,'total':0,
        'candidates':[],'truncated':False,'rom_location_known':False,
        'causation_proven':False,'write_authorized':False,
        'coverage':{'alignment':1,'bytes_per_observation':first['length'],
            'observations':len(rows),'positions_tested':0,'result_limit':max_results},
        'interpretation':'Offsets are relative to the exposed memory region, not CPU addresses. Numeric agreement is a hypothesis, not a named game property.'}
    variation=len(set(known))>1 or any(row['relation'] in ('changed','increased','decreased') or row['relation']=='delta' and row['delta']!=0 for row,_,_ in rows[1:])
    if not variation:
        return {**result,'status':'NEEDS_VARIATION','next_experiment':'Record the target changing, then record a control where it stays unchanged.'}
    candidates=[];keys=[];total=0
    for width in (1,2,3,4):
        for endian in (('little','big') if width>1 else ('little',)):
            for encoding,signed in (('binary',False),('binary',True),('packed_bcd',False)):
                for position in range(first['length']-width+1):
                    if position%128==0 and cancelled():raise KeyboardInterrupt
                    result['coverage']['positions_tested']+=1
                    values=[_read(raw[position:position+width],width,endian,signed,encoding) for _,_,raw in rows]
                    if any(v is None for v in values) or signed and all(v>=0 for v in values):continue
                    keep=True
                    for i in range(1,len(rows)):
                        relation=rows[i][0]['relation'];a,b=values[i-1:i+1]
                        if not {'changed':b!=a,'unchanged':b==a,'increased':b>a,'decreased':b<a,'delta':b-a==rows[i][0]['delta']}[relation]:
                            keep=False;break
                    if not keep:continue
                    biases=[values[i]-row['value'] for i,(row,_,_) in enumerate(rows) if row['value'] is not None]
                    if biases and (len(set(biases))!=1 or abs(biases[0])>65535):continue
                    bias=biases[0] if biases else None
                    model='relation' if bias is None else 'exact' if bias==0 else 'constant_offset'
                    offset=first['offset']+position
                    total+=1
                    key=({'exact':0,'constant_offset':1,'relation':2}[model],width,offset,encoding,signed,endian)
                    if len(keys)>=max_results and key>=keys[-1]:continue
                    signature={'source_sha256':first['game_sha256'],'observations':[[r['sequence'],r['data_sha256']] for _,r,_ in rows],
                        'offset':offset,'width':width,'endian':endian,'signed':signed,'encoding':encoding,'model':model,'bias':bias}
                    index=bisect_right(keys,key);keys.insert(index,key)
                    candidates.insert(index,{'candidate_id':hashlib.sha256(canonical_bytes(signature,max_bytes=8192)).hexdigest(),
                        'offset':offset,'width':width,'endian':endian,'signed':signed,'encoding':encoding,
                        'model':model,'bias':bias,'values':values,'confidence':'CORRELATED',
                        'reason':'All recorded numeric and change/control constraints agree; writer and ROM location are not yet established.'})
                    if len(candidates)>max_results:candidates.pop();keys.pop()
    result.update(total=total,candidates=candidates,truncated=total>max_results,
        next_experiment='Probe a surviving candidate for actual memory accesses.' if controls else 'Record an unchanged control while unrelated gameplay continues to eliminate background counters.')
    if not candidates:result.update(status='NO_MATCH',next_experiment='Check the observed number and memory range, or capture another controlled change. A different encoding or an unexposed region may be involved.')
    return result
