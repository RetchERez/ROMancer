"""Bounded structural observations and explicit declared resource relationships."""
import hashlib,math
from .asset_schema import number


def scan_structures(raw,system,start,file_size,*,cancelled=lambda:False):
    if type(raw) is not bytes or len(raw)>1024**2:raise ValueError('structural scan window exceeds1MiB')
    number(start,0,64*1024**2);number(file_size,start+len(raw),64*1024**2)
    stride=max(4,math.ceil(len(raw)/65536/4)*4);rows=[];checked=0
    if system in ('gba','genesis'):
        for i in range(0,len(raw)-3,stride):
            if checked%4096==0 and cancelled():raise KeyboardInterrupt
            checked+=1;value=int.from_bytes(raw[i:i+4],'little' if system=='gba' else 'big')
            target=value&0x1ffffff if system=='gba' and 0x08000000<=value<0x0e000000 else value if system=='genesis' and 0x200<=value else None
            if target is not None and target<file_size and len(rows)<64:
                rows.append({'offset':start+i,'stored_value':value,'target_offset':target,'width':4,
                  'endian':'little' if system=='gba' else 'big','confidence':'CANDIDATE','meaning':'Numeric value falls inside a ROM address window; dereference not observed.'})
    return {'candidates':rows,'coverage':{'offset':start,'window_bytes':len(raw),'positions_checked':checked,'stride':stride,'result_limit':64},'write_authorized':False,'dereference_observed':False}


def resource_relationships(raw,descriptors,source_sha256):
    if hashlib.sha256(raw).hexdigest()!=source_sha256:raise ValueError('relationship source differs')
    nodes=[];edges=[]
    if descriptors.get('levels'):
        from .level_design import inspect_level
        doc=inspect_level(raw,descriptors['levels'],source_sha256)
        for r in doc['ranges']:nodes.append({'id':'level:'+r['name'],'name':r['name'],**r,'confidence':'DECLARED'})
        for room in doc['rooms']:edges.append({'from':'level:'+room['id']+' terrain','to':'level:metatiles','relation':'indexes metatiles'})
        edges.extend([{'from':'level:metatiles','to':'level:tiles','relation':'indexes tiles'},
          {'from':'level:tiles','to':'level:palette','relation':'declared preview palette'}])
    if descriptors.get('sound'):
        from .sound_studio import inspect_sound
        doc=inspect_sound(raw,descriptors['sound'],source_sha256)
        for r in doc['ranges']:nodes.append({'id':'sound:'+r['name'],'name':r['name'],**r,'confidence':'DECLARED'})
    if len(nodes)>256 or len(edges)>512:raise ValueError('resource relationship budget exceeded')
    return {'ok':True,'source_sha256':source_sha256,'nodes':nodes,'edges':edges,'game_semantics_verified':False,'write_authorized':False}
