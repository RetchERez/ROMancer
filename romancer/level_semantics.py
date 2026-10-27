"""Validated editor labels and actor rectangles; declarations are not gameplay proof."""
from .asset_schema import fields,number,label

KINDS=('walkable','solid','hazard','water','ladder','other')

def collision_types(room):
    rows=room.get('collision_types',[])
    if type(rows) is not list or len(rows)>256:raise ValueError('declare at most256 collision types')
    if rows and room['collision'] is None:raise ValueError('collision labels need a declared collision grid')
    seen=set();limit=(1<<(8*room['collision']['entry_bytes']))-1 if room['collision'] else 255
    for row in rows:
        fields(row,'value name kind color');number(row['value'],0,limit);label(row['name'])
        if row['value'] in seen:raise ValueError('duplicate collision value')
        seen.add(row['value'])
        if row['kind'] not in KINDS:raise ValueError('unsupported declared collision kind')
        if type(row['color']) is not list or len(row['color'])!=3:raise ValueError('collision color needs three RGB values')
        for value in row['color']:number(value,0,255)
    return rows

def validate_hitbox(metadata,storage,values):
    box=metadata.get('hitbox')
    if box is None:return
    fields(box,'offset_x offset_y width height')
    declared={f['name']:f for f in storage['fields']}
    for component,name in box.items():
        label(name)
        if name not in declared:raise ValueError('hitbox refers to an undeclared object field')
        number(values[name],1 if component in ('width','height') else 0,1024)

def validate_sprite(metadata,tile_count,color_count):
    sprite=metadata.get('sprite')
    if sprite is None:return
    fields(sprite,'tiles width height transparent_index');number(sprite['width'],1,8);number(sprite['height'],1,8);number(sprite['transparent_index'],0,color_count-1)
    if type(sprite['tiles']) is not list or len(sprite['tiles'])!=sprite['width']*sprite['height']:raise ValueError('starting sprite tile count differs from its dimensions')
    for tile in sprite['tiles']:number(tile,0,tile_count-1)

def validate_changed_hitboxes(raw,rooms):
    for room in rooms:
        storage=room['objects']
        for metadata in room.get('object_metadata',[]):
            if 'hitbox' not in metadata:continue
            at=storage['offset']+metadata['index']*storage['stride']
            values={f['name']:int.from_bytes(raw[at+f['offset']:at+f['offset']+f['bytes']],f['endian']) for f in storage['fields']}
            validate_hitbox(metadata,storage,values)
