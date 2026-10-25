"""Explain explicit source declarations; unknown byte purposes stay unknown."""
import hashlib
from .asset_schema import number


def explain_bytes(raw,descriptors,source_sha256,offset):
    if type(raw) is not bytes or len(raw)>64*1024**2 or hashlib.sha256(raw).hexdigest()!=source_sha256:raise ValueError('byte explanation source differs')
    number(offset,0,len(raw)-1);rows=[]
    table=descriptors.get('tables')
    if table and table.get('source_sha256')==source_sha256:
        from .data_tables import validate_definition,TYPES
        d=validate_definition(table['definition'],len(raw));index=(offset-d['offset'])//d['stride']
        if 0<=index<d['count']:
            for field in d['fields']:
                width,signed=TYPES[field['type']];at=d['offset']+index*d['stride']+field['offset']
                if at<=offset<at+width:
                    value=int.from_bytes(raw[at:at+width],field['endian'],signed=signed)
                    rows.append({'name':d['name']+' / row '+str(index)+' / '+field['name'],'offset':at,'length':width,
                      'raw_hex':raw[at:at+width].hex(),'type':field['type'],'endian':field['endian'],'value':value,
                      'minimum':-(1<<(width*8-1)) if signed else 0,'maximum':(1<<(width*8-int(signed)))-1,
                      'confidence':'DECLARED','pointer_target':value-field['pointer_base'] if field['pointer_base'] is not None else None})
    for kind in ('levels','sound'):
        if not descriptors.get(kind):continue
        if kind=='levels':
            from .level_design import inspect_level
            doc=inspect_level(raw,descriptors[kind],source_sha256)
        else:
            from .sound_studio import inspect_sound
            doc=inspect_sound(raw,descriptors[kind],source_sha256)
        for r in doc['ranges']:
            if r['offset']<=offset<r['offset']+r['length']:rows.append({**r,'kind':kind,'confidence':'DECLARED'})
    return {'ok':True,'source_sha256':source_sha256,'offset':offset,'raw_hex':raw[offset:offset+16].hex(),
      'interpretations':rows[:64],'game_semantics_verified':False,'write_authorized':False,
      'note':'Declared ranges and numeric encodings only. An empty interpretation list means the byte purpose is unknown.'}
