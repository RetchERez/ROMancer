"""Strict revision-bound descriptors for declared uncompressed assets."""
import hashlib
import json
import re
from .asset_codecs import CODECS, cell_size
from .script_schema import canonical_bytes


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError('missing or unknown descriptor fields')


def number(value, minimum=0, maximum=64*1024*1024):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('integer outside supported bounds')
    return value


def label(value, maximum=128, blank=False):
    if (type(value) is not str or len(value)>maximum or (not blank and not value.strip())
            or any(ord(c)<32 or 127<=ord(c)<160 for c in value)):
        raise ValueError('invalid bounded label')
    return value


def provenance(value):
    fields(value,'origin note reference')
    if value['origin'] not in ('profile_assertion','synthetic_fixture'):
        raise ValueError('unsupported provenance')
    label(value['note'],512,blank=True)
    if value['reference'] is not None:label(value['reference'],256)


def mask_info(mask, entry_bytes):
    number(mask,1,(1<<(entry_bytes*8))-1)
    shift=(mask&-mask).bit_length()-1
    maximum=mask>>shift
    if maximum & (maximum+1):raise ValueError('mask must be contiguous')
    return shift,maximum


def validate_asset_schema(schema: dict) -> dict:
    normalized=json.loads(canonical_bytes(schema,max_bytes=1024*1024))
    fields(normalized,'schema_version id version source bitmaps palettes tilemaps fonts provenance')
    number(normalized['schema_version'],1,1)
    label(normalized['id']);label(normalized['version']);provenance(normalized['provenance'])
    fields(normalized['source'],'sha256 size')
    size=number(normalized['source']['size'],1)
    if type(normalized['source']['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',normalized['source']['sha256']):raise ValueError('invalid source SHA-256')
    groups={};identifiers=set();ranges=[];reasons=[]
    for collection in ('bitmaps','palettes','tilemaps','fonts'):
        rows=normalized[collection]
        if type(rows) is not list or len(rows)>16 or (collection=='bitmaps' and not rows):
            raise ValueError('invalid asset group count')
        groups[collection]={}
        for row in rows:
            if type(row) is not dict:raise ValueError('asset group must be an object')
            identifier=label(row.get('id'))
            if identifier in identifiers:raise ValueError('duplicate asset ID')
            identifiers.add(identifier);groups[collection][identifier]=row
            provenance(row.get('provenance'))
    def physical(row):
        offset=number(row['offset'],0,size);length=number(row['length'],1,256*1024)
        if length>size-offset:raise ValueError('asset range exceeds source')
        ranges.append((offset,offset+length));return length
    total_cells=total_pixels=0
    for row in normalized['bitmaps']:
        fields(row,'id offset length codec width height count palette_id provenance')
        count=number(row['count'],1,1024)
        width=number(row['width'],1,32);height=number(row['height'],1,32)
        length=physical(row);label(row['codec'])
        if row['codec'] in CODECS:
            if length!=count*cell_size(row['codec'],width,height):raise ValueError('bitmap length mismatch')
        else:reasons.append('unsupported codec: '+row['codec'])
        if row['palette_id'] is not None and row['palette_id'] not in groups['palettes']:
            raise ValueError('missing bitmap palette')
        total_cells+=count;total_pixels+=count*width*height
    if total_cells>1024 or total_pixels>65536:raise ValueError('bitmap aggregate budget exceeded')
    entries=0
    for row in normalized['palettes']:
        fields(row,'id offset length entry_bytes byte_order banks colors_per_bank channels provenance')
        length=physical(row);entry=number(row['entry_bytes'],1,2)
        if row['byte_order'] not in ('little','big'):raise ValueError('explicit palette byte order required')
        banks=number(row['banks'],1,4096);colors=number(row['colors_per_bank'],1,256)
        if length!=entry*banks*colors:raise ValueError('palette storage length mismatch')
        fields(row['channels'],'r g b');claimed=0
        for mask in row['channels'].values():
            _,maximum=mask_info(mask,entry)
            if maximum>255 or mask&claimed:raise ValueError('invalid palette channel masks')
            claimed|=mask
        entries+=banks*colors
    if entries>4096:raise ValueError('palette entry budget exceeded')
    for row in normalized['bitmaps']:
        if row['palette_id'] is not None and row['codec'] in CODECS:
            if groups['palettes'][row['palette_id']]['colors_per_bank'] != 1<<CODECS[row['codec']]:
                raise ValueError('palette/index depth mismatch')
    entries=0
    for row in normalized['tilemaps']:
        fields(row,'id offset length entry_bytes byte_order width height bitmap_id palette_id fields provenance')
        length=physical(row);entry=number(row['entry_bytes'],1,2)
        width=number(row['width'],1,4096);height=number(row['height'],1,4096)
        if row['byte_order'] not in ('little','big') or length!=entry*width*height:raise ValueError('invalid tilemap storage')
        bitmap=groups['bitmaps'].get(row['bitmap_id']);palette=groups['palettes'].get(row['palette_id'])
        if (bitmap is None or palette is None or (bitmap['width'],bitmap['height'])!=(8,8)
                or bitmap['palette_id']!=row['palette_id']):raise ValueError('invalid tilemap references')
        fields(row['fields'],'tile_index palette_bank flip_x flip_y');claimed=0
        for name,field in row['fields'].items():
            if type(field) is not dict:raise ValueError('invalid tilemap field')
            if field.get('kind')=='bits':
                fields(field,'kind mask');mask=field['mask'];_,maximum=mask_info(mask,entry)
                if mask&claimed or (name.startswith('flip_') and maximum!=1):raise ValueError('overlapping or invalid map masks')
                claimed|=mask
            elif field.get('kind')=='constant':
                fields(field,'kind value');maximum=1 if name.startswith('flip_') else (bitmap['count']-1 if name=='tile_index' else palette['banks']-1)
                number(field['value'],0,maximum)
            else:raise ValueError('unknown map field kind')
        entries+=width*height
    if entries>4096:raise ValueError('tilemap budget exceeded')
    cells=set();advances=set();glyph_count=0
    for font in normalized['fonts']:
        fields(font,'id glyphs provenance')
        if type(font['glyphs']) is not list or len(font['glyphs'])>256:raise ValueError('invalid glyph array')
        ids=set()
        for glyph in font['glyphs']:
            fields(glyph,'id bitmap_id cell_index bearing advance provenance')
            name=label(glyph['id']);provenance(glyph['provenance'])
            if name in ids:raise ValueError('duplicate glyph ID')
            ids.add(name);bitmap=groups['bitmaps'].get(glyph['bitmap_id'])
            if bitmap is None or bitmap['codec']!='mono-row-msb-v1':raise ValueError('font requires a mono bitmap')
            number(glyph['cell_index'],0,bitmap['count']-1)
            key=(glyph['bitmap_id'],glyph['cell_index'])
            if key in cells:raise ValueError('aliased font cell')
            cells.add(key);fields(glyph['bearing'],'x y')
            for value in glyph['bearing'].values():number(value,-64,64)
            advance=glyph['advance']
            if type(advance) is not dict:raise ValueError('invalid advance')
            if advance.get('kind')=='u8':
                fields(advance,'kind offset');offset=number(advance['offset'],0,size-1)
                if offset in advances:raise ValueError('aliased advance')
                advances.add(offset);ranges.append((offset,offset+1))
            elif advance.get('kind')=='declared':
                fields(advance,'kind pixels provenance');number(advance['pixels'],0,128);provenance(advance['provenance'])
            else:raise ValueError('unknown advance kind')
            glyph_count+=1
    if glyph_count>256:raise ValueError('font aggregate budget exceeded')
    ranges.sort()
    if any(a[1]>b[0] for a,b in zip(ranges,ranges[1:])):raise ValueError('physical asset ranges overlap')
    if sum(end-start for start,end in ranges)>256*1024:raise ValueError('asset physical budget exceeded')
    return {'normalized_schema':normalized,'schema_sha256':hashlib.sha256(canonical_bytes(normalized,max_bytes=1024*1024)).hexdigest(),
            'write_supported':not reasons,'read_only_reasons':reasons}
