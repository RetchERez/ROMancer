"""Declared fixed-capacity level data. No inferred game semantics or allocation."""
import hashlib
from .asset_schema import fields,number,label
from .script_schema import canonical_bytes
from .level_semantics import collision_types,validate_hitbox,validate_changed_hitboxes,validate_sprite
from .scene_schema import normalize_scene,validate_scene
from .level_palette import storage_length,decode_palette
from .level_tiles import decode_tiles


def _identity(raw,definition,source_sha256):
    if type(definition) is not dict:raise ValueError('level definition must be a JSON object')
    if type(raw) is not bytes or not 1<=len(raw)<=64*1024**2:raise ValueError('level source exceeds byte budget')
    if hashlib.sha256(raw).hexdigest()!=source_sha256 or definition.get('source_sha256')!=source_sha256:raise ValueError('level definition source differs')


def object_maximum(field,room,room_count):
    return min(field['maximum'],room['width']-1 if field['name']=='x' else room['height']-1 if field['name']=='y' else room_count-1 if field['name']=='exit_room' else field['maximum'])


def _connections(rooms,definitions,tile_count,color_count):
    """Explicit editor annotations describe references, never runtime behavior."""
    room_ids={room['id'] for room in rooms};connections=[]
    for room,definition in zip(rooms,definitions):
        metadata=definition.get('object_metadata',[]);storage=definition['objects'];seen=set()
        if type(metadata) is not list or len(metadata)>256:raise ValueError('declare at most 256 object metadata entries per room')
        for entry in metadata:
            fields(entry,'index name role reference'+''.join(' '+key for key in ('hitbox','sprite') if type(entry) is dict and key in entry));number(entry['index'],0,len(room['objects'])-1);label(entry['name'])
            if entry['index'] in seen:raise ValueError('duplicate object metadata slot')
            seen.add(entry['index'])
            validate_hitbox(entry,storage,room['objects'][entry['index']])
            validate_sprite(entry,tile_count,color_count)
            if entry['role'] not in ('object','actor','start','exit','trigger'):raise ValueError('unknown declared object role')
            reference=entry['reference']
            if entry['role']!='exit':
                if reference is not None:raise ValueError('only declared exits have room references')
                continue
            fields(reference,'field targets');label(reference['field'])
            field=next((field for field in storage['fields'] if field['name']==reference['field']),None)
            if field is None or field['name'] in ('x','y'):raise ValueError('exit reference needs a declared destination integer field')
            targets=reference['targets']
            if type(targets) is not list or not 1<=len(targets)<=32:raise ValueError('exit reference needs 1 to 32 declared destinations')
            by_value={}
            for target in targets:
                fields(target,'value room_id');number(target['value'],0,object_maximum(field,room,len(rooms)));label(target['room_id'])
                if target['value'] in by_value:raise ValueError('duplicate exit destination value')
                if target['room_id'] not in room_ids:raise ValueError('exit destination room is not declared')
                by_value[target['value']]=target['room_id']
            value=room['objects'][entry['index']][field['name']]
            if value not in by_value:raise ValueError('current exit destination is not mapped')
            connections.append({'room_id':room['id'],'index':entry['index'],'name':entry['name'],
              'field':field['name'],'value':value,'target_room_id':by_value[value]})
        room['object_metadata']=metadata
    return connections


def inspect_level(raw,definition,source_sha256):
    _identity(raw,definition,source_sha256)
    from .studio_runtime import validate_studio_data
    validate_studio_data(raw)
    d=__import__('json').loads(canonical_bytes(definition,max_bytes=256*1024))
    fields(d,'schema_version source_sha256 name tiles metatiles rooms'+(' scene' if 'scene' in d else ''));number(d['schema_version'],1,1);label(d['name'])
    ranges=[]
    def storage(offset,length,name):
        number(offset,0,len(raw)-1);number(length,1,len(raw))
        if offset+length>len(raw):raise ValueError('declared level storage exceeds source')
        if any(offset<b and offset+length>a for a,b,_ in ranges):raise ValueError('declared level storage overlaps')
        ranges.append((offset,offset+length,name))
    def format_grid(g,count,name):
        fields(g,'offset entry_bytes endian');number(g['entry_bytes'],1,2)
        if g['endian'] not in ('little','big'):raise ValueError('invalid integer byte order')
        storage(g['offset'],count*g['entry_bytes'],name)
        return [int.from_bytes(raw[g['offset']+i*g['entry_bytes']:g['offset']+(i+1)*g['entry_bytes']],g['endian']) for i in range(count)]
    t=d['tiles'];tiles,colors,segments=decode_tiles(raw,t,storage)
    length=storage_length(t['palette_format'],colors);storage(t['palette_offset'],length,'palette')
    palette=decode_palette(raw[t['palette_offset']:t['palette_offset']+length],t['palette_format'],colors)
    m=d['metatiles']
    if type(m) is not dict:raise ValueError('metatile definition must be an object')
    stored=m.get('kind')!='identity'
    if not stored:
        fields(m,'kind');block_width=block_height=parts=1;blocks=[[i] for i in range(len(tiles))]
    else:
        fields(m,'offset count width height entry_bytes endian');number(m['count'],1,1024);number(m['width'],1,8);number(m['height'],1,8)
        block_width=m['width'];block_height=m['height'];parts=block_width*block_height
        flat=format_grid({k:m[k] for k in ('offset','entry_bytes','endian')},m['count']*parts,'metatiles')
        if any(v>=len(tiles) for v in flat):raise ValueError('metatile references an undeclared tile')
        blocks=[flat[i*parts:(i+1)*parts] for i in range(m['count'])]
    if type(d['rooms']) is not list or not 1<=len(d['rooms'])<=32:raise ValueError('declare 1 to 32 rooms')
    rooms=[];ids=set();uses={str(i):[] for i in range(len(blocks))};total=0
    for r in d['rooms']:
        fields(r,'id name width height terrain collision objects'+''.join(' '+key for key in ('object_metadata','collision_types','elevation') if type(r) is dict and key in r));label(r['id']);label(r['name'])
        if r['id'] in ids:raise ValueError('duplicate room ID')
        ids.add(r['id']);number(r['width'],1,128);number(r['height'],1,128);count=r['width']*r['height'];total+=count
        if total>32768 or count*parts*64>4*1024**2:raise ValueError('level preview exceeds pixel budget')
        terrain=format_grid(r['terrain'],count,r['id']+' terrain')
        if any(v>=len(blocks) for v in terrain):raise ValueError('room references an undeclared metatile')
        collision=format_grid(r['collision'],count,r['id']+' collision') if r['collision'] is not None else None
        elevation=format_grid(r['elevation'],count,r['id']+' elevation') if r.get('elevation') is not None else None
        objects=[];o=r['objects']
        if o is not None:
            fields(o,'offset count stride fields');number(o['count'],1,256);number(o['stride'],1,128);storage(o['offset'],o['count']*o['stride'],r['id']+' objects')
            if type(o['fields']) is not list or not 1<=len(o['fields'])<=16:raise ValueError('invalid object fields')
            used=set();names=set()
            for f in o['fields']:
                fields(f,'name offset bytes endian maximum'+(' minimum' if type(f) is dict and 'minimum' in f else ''));label(f['name']);number(f['offset'],0,o['stride']-1);number(f['bytes'],1,2);number(f['maximum'],0,(1<<(8*f['bytes']))-1);number(f.get('minimum',0),0,f['maximum'])
                if f['endian'] not in ('little','big') or f['offset']+f['bytes']>o['stride']:raise ValueError('object field exceeds record')
                span=set(range(f['offset'],f['offset']+f['bytes']))
                if span&used or f['name'] in names:raise ValueError('object fields overlap or duplicate')
                used|=span;names.add(f['name'])
            for index in range(o['count']):
                obj={}
                for f in o['fields']:
                    at=o['offset']+index*o['stride']+f['offset'];value=int.from_bytes(raw[at:at+f['bytes']],f['endian'])
                    maximum=object_maximum(f,r,len(d['rooms']))
                    number(value,f.get('minimum',0),maximum);obj[f['name']]=value
                objects.append(obj)
        for i,value in enumerate(terrain):uses[str(value)].append({'room_id':r['id'],'cell':i})
        rooms.append({'id':r['id'],'name':r['name'],'width':r['width'],'height':r['height'],'terrain':terrain,'collision':collision,'elevation':elevation,'collision_types':collision_types(r),'objects':objects})
    scene=normalize_scene(d.get('scene'),block_width*8,block_height*8)
    if 'scene' in d or any(r['elevation'] is not None for r in rooms):validate_scene(scene,rooms,d['rooms'])
    connections=_connections(rooms,d['rooms'],len(tiles),colors)
    document_id=hashlib.sha256(canonical_bytes(d,max_bytes=256*1024)).hexdigest()
    result={'ok':True,'document_id':document_id,'source_sha256':source_sha256,'definition':d,'scene':scene,'tiles':tiles,'tile_segments':segments,'palette':palette,'metatiles':blocks,'metatiles_stored':stored,'block_width':block_width,'block_height':block_height,'rooms':rooms,'connections':connections,'uses':uses,'ranges':[{'offset':a,'length':b-a,'name':name} for a,b,name in ranges],'game_semantics_verified':False}
    try:canonical_bytes(result,max_bytes=2*1024**2)
    except ValueError as exc:raise ValueError('combined level preview budget exceeded; declare fewer rooms, cells or tiles') from exc
    return result


def plan_level(raw,definition,document_id,changes,source_sha256):
    doc=inspect_level(raw,definition,source_sha256)
    if doc['document_id']!=document_id:raise ValueError('level review document is stale')
    if type(changes) is not list or not 1<=len(changes)<=8192:raise ValueError('review 1 to 8192 level changes')
    d=doc['definition'];writes={};seen=set();affected=set()
    for change in changes:
        if type(change) is not dict:raise ValueError('level changes must be JSON objects')
        kind=change.get('kind')
        if kind=='metatile':
            if not doc['metatiles_stored']:raise ValueError('identity tile blocks are derived, not a stored metatile table')
            fields(change,'kind index part value');m=d['metatiles'];number(change['index'],0,m['count']-1);number(change['part'],0,m['width']*m['height']-1);number(change['value'],0,len(doc['tiles'])-1)
            offset=m['offset']+(change['index']*m['width']*m['height']+change['part'])*m['entry_bytes'];width=m['entry_bytes'];endian=m['endian']
            affected.update(use['room_id'] for use in doc['uses'][str(change['index'])])
        elif kind in ('terrain','collision','elevation','object'):
            r=next((r for r in d['rooms'] if r['id']==change.get('room_id')),None)
            if r is None:raise ValueError('unknown room')
            affected.add(r['id'])
            if kind=='object':
                fields(change,'kind room_id index field value');o=r['objects']
                if o is None:raise ValueError('objects are not declared')
                number(change['index'],0,o['count']-1);f=next((f for f in o['fields'] if f['name']==change['field']),None)
                if f is None:raise ValueError('unknown object field')
                maximum=object_maximum(f,r,len(d['rooms']))
                metadata=next((entry for entry in r.get('object_metadata',[]) if entry['index']==change['index']),None)
                if metadata and metadata['role']=='exit' and metadata['reference']['field']==f['name'] and change['value'] not in [target['value'] for target in metadata['reference']['targets']]:raise ValueError('exit destination is not mapped')
                number(change['value'],f.get('minimum',0),maximum);offset=o['offset']+change['index']*o['stride']+f['offset'];width=f['bytes'];endian=f['endian']
            else:
                fields(change,'kind room_id index value');number(change['index'],0,r['width']*r['height']-1);g=r.get(kind)
                if g is None:raise ValueError('requested room layer is not declared')
                width=g['entry_bytes'];endian=g['endian'];maximum=len(doc['metatiles'])-1 if kind=='terrain' else min(1024,(1<<(8*width))-1) if kind=='elevation' else (1<<(8*width))-1
                number(change['value'],0,maximum);offset=g['offset']+change['index']*width
        else:raise ValueError('unknown level change')
        key=(offset,width)
        if key in seen:raise ValueError('duplicate level edit')
        seen.add(key);after=change['value'].to_bytes(width,endian);before=raw[offset:offset+width]
        if before!=after:writes[offset]={'offset':offset,'before':before.hex(),'after':after.hex()}
    if not writes:raise ValueError('no changed level bytes')
    shadow=bytearray(raw)
    for change in writes.values():shadow[change['offset']:change['offset']+len(bytes.fromhex(change['after']))]=bytes.fromhex(change['after'])
    validate_changed_hitboxes(shadow,d['rooms'])
    from .studio_runtime import validate_studio_data
    validate_studio_data(bytes(shadow))
    if 'scene' in d or any(r.get('elevation') is not None for r in d['rooms']):
        shadow_definition=__import__('copy').deepcopy(d);shadow_sha=hashlib.sha256(shadow).hexdigest();shadow_definition['source_sha256']=shadow_sha
        inspect_level(bytes(shadow),shadow_definition,shadow_sha)
    return {'ok':True,'edits':[writes[k] for k in sorted(writes)],'affected_rooms':sorted(affected),'document_id':document_id,'source_sha256':source_sha256}
