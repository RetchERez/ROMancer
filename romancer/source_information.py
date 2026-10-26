"""Explain explicit source declarations; unknown byte purposes stay unknown."""
import hashlib
from .asset_schema import number


def _level_details(raw,doc,offset):
    d=doc['definition'];rows=[]
    def value(name,kind,at,width,endian,maximum,**metadata):
        rows.append({'name':name,'kind':kind,'offset':at,'length':width,'raw_hex':raw[at:at+width].hex(),
                     'type':'u'+str(width*8),'endian':endian,'value':int.from_bytes(raw[at:at+width],endian),
                     'minimum':0,'maximum':maximum,'confidence':'DECLARED',**metadata})
    for room in d['rooms']:
        for key in ('terrain','collision'):
            g=room[key]
            if g is None:continue
            width=g['entry_bytes'];index=(offset-g['offset'])//width
            if 0<=index<room['width']*room['height']:
                x,y=index%room['width'],index//room['width']
                value(room['name']+' / '+key+' ('+str(x)+', '+str(y)+')',key+'-cell',g['offset']+index*width,width,g['endian'],
                      len(doc['metatiles'])-1 if key=='terrain' else (1<<(8*width))-1,
                      room_id=room['id'],x=x,y=y,
                      description='Metatile index in the declared room.' if key=='terrain' else 'Raw collision value; behavior labels require an explicit game definition.')
        o=room['objects']
        if o is None:continue
        index=(offset-o['offset'])//o['stride']
        if not 0<=index<o['count']:continue
        metadata=next((m for m in room.get('object_metadata',[]) if m['index']==index),None)
        name=metadata['name'] if metadata else 'Object slot '+str(index)
        for field in o['fields']:
            at=o['offset']+index*o['stride']+field['offset'];width=field['bytes']
            if not at<=offset<at+width:continue
            bounds={'x':room['width']-1,'y':room['height']-1,'exit_room':len(d['rooms'])-1}
            target=next((c['target_room_id'] for c in doc.get('connections',[]) if c['room_id']==room['id'] and c['index']==index and c['field']==field['name']),None)
            value(room['name']+' / '+name+' / '+field['name'],'object-field',at,width,field['endian'],min(field['maximum'],bounds.get(field['name'],field['maximum'])),
                  room_id=room['id'],object_index=index,field=field['name'],target_room_id=target,
                  description=('Declared '+metadata['role']+' slot.' if metadata else 'Declared integer field; gameplay meaning is unknown.')+(' Destination room: '+target+'.' if target else ''))
    m=d['metatiles'];width=m['entry_bytes'];flat=(offset-m['offset'])//width;parts=m['width']*m['height']
    if 0<=flat<m['count']*parts:
        value('Metatile '+str(flat//parts)+' / part '+str(flat%parts),'metatile-part',m['offset']+flat*width,width,m['endian'],len(doc['tiles'])-1,
              metatile_index=flat//parts,part=flat%parts,description='Tile index shared by every room cell using this metatile.')
    return rows


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
        if kind=='levels':rows.extend(_level_details(raw,doc,offset))
        else:
            for sample in doc['samples']:
                if sample['offset']<=offset<sample['offset']+sample['length']:
                    rows.append({'name':sample['name'],'kind':'sound-sample','offset':sample['offset'],'length':sample['length'],
                                 'confidence':'DECLARED','description':sample['codec']+' mono sample at '+str(sample['sample_rate'])+' Hz. Driver mixing, envelopes and playback use remain separate.'})
            for song in doc['songs']:
                index=(offset-song['offset'])//song['stride']
                if not 0<=index<song['count']:continue
                within=(offset-song['offset'])%song['stride']
                for name,at,width in (('note',0,1),('duration',1,2),('volume',3,1),('channel',4,1),('instrument',5,1)):
                    if at<=within<at+width:
                        start=song['offset']+index*song['stride']+at
                        rows.append({'name':song['name']+' / event '+str(index)+' / '+name,'kind':'song-field','offset':start,'length':width,
                                     'raw_hex':raw[start:start+width].hex(),'value':song['events'][index][name],'confidence':'DECLARED',
                                     'description':'Field in the identified '+song['driver']+' sequence; no commercial music-driver layout is inferred.'})
    return {'ok':True,'source_sha256':source_sha256,'offset':offset,'raw_hex':raw[offset:offset+16].hex(),
      'interpretations':rows[:64],'game_semantics_verified':False,'write_authorized':False,
      'note':'Declared ranges and numeric encodings only. An empty interpretation list means the byte purpose is unknown.'}
