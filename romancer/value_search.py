"""Read-only integer narrowing over bounded, identity-bound native observations."""
import hashlib,json,re
from .asset_schema import number
from .script_schema import canonical_bytes

BINDING=('worker_session_id','epoch','region','region_size','offset','length','game_sha256','core_sha256','core_options')


def _snapshot(value):
    value=json.loads(canonical_bytes(value,max_bytes=32768))
    if type(value) is not dict or any(k not in value for k in BINDING):raise ValueError('incomplete memory observation')
    number(value['length'],1,4096);number(value['offset'],0,256*1024**2);number(value['region'],0,3)
    number(value['region_size'],value['offset']+value['length'],256*1024**2)
    number(value['epoch'],0,2**53);number(value.get('sequence'),1,2**53)
    if type(value['worker_session_id']) is not str or not 1<=len(value['worker_session_id'])<=64:raise ValueError('invalid worker identity')
    if any(type(value[k]) is not str or re.fullmatch('[a-f0-9]{64}',value[k]) is None for k in ('game_sha256','core_sha256')):raise ValueError('invalid source/core identity')
    if type(value['core_options']) is not dict:raise ValueError('invalid core options')
    if type(value.get('raw_hex')) is not str or re.fullmatch('[a-f0-9]{'+str(value['length']*2)+'}',value['raw_hex']) is None:raise ValueError('invalid memory bytes')
    raw=bytes.fromhex(value['raw_hex'])
    if hashlib.sha256(raw).hexdigest()!=value.get('data_sha256'):raise ValueError('memory observation hash differs')
    return value,raw


def _format(width,endian,signed,target):
    if type(width) is not int or width not in (1,2,4) or endian not in ('little','big') or type(signed) is not bool:raise ValueError('choose an 8,16 or32-bit integer and byte order')
    low=-(1<<(width*8-1)) if signed else 0;high=(1<<(width*8-int(signed)))-1
    if target is not None:number(target,low,high)


def begin_search(snapshot,width,endian,signed,target):
    _format(width,endian,signed,target);snapshot,raw=_snapshot(snapshot)
    offsets=[snapshot['offset']+i for i in range(0,len(raw)-width+1,width) if target is None or int.from_bytes(raw[i:i+width],endian,signed=signed)==target]
    return {'snapshot':snapshot,'width':width,'endian':endian,'signed':signed,'offsets':offsets,'matches':[],
      'rom_location_known':False,'memory_written':False}


def narrow_search(search,after,relation,target):
    before,old=_snapshot(search['snapshot']);after,new=_snapshot(after)
    if any(before[k]!=after[k] for k in BINDING):raise ValueError('session, state, core or memory range changed; start a new search')
    if after['sequence']<=before['sequence']:raise ValueError('capture a newer memory observation')
    width,endian,signed=(search[k] for k in ('width','endian','signed'));_format(width,endian,signed,target)
    if relation not in ('equal','changed','unchanged','increased','decreased') or relation=='equal' and target is None:raise ValueError('choose a comparison and an exact value when needed')
    offsets=search['offsets']
    if type(offsets) is not list or len(offsets)>4096 or len(set(offsets))!=len(offsets):raise ValueError('invalid bounded search candidates')
    matches=[]
    for offset in offsets:
        number(offset,before['offset'],before['offset']+len(old)-width);index=offset-before['offset']
        if index%width:raise ValueError('candidate alignment differs')
        a=int.from_bytes(old[index:index+width],endian,signed=signed);b=int.from_bytes(new[index:index+width],endian,signed=signed)
        keep={'equal':b==target,'changed':b!=a,'unchanged':b==a,'increased':b>a,'decreased':b<a}[relation]
        if keep:matches.append({'offset':offset,'previous':a,'value':b})
    return {**search,'snapshot':after,'offsets':[r['offset'] for r in matches],'matches':matches}
