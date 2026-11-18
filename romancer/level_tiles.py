"""Explicit stored tile segments and reversible source-index mappings."""
from .asset_schema import fields,number
from .asset_codecs import cell_size,decode_cell,encode_cell,CODECS


def decode_tiles(raw,definition,storage):
    t=definition
    if type(t) is not dict:raise ValueError('tile definition must be an object')
    if 'segments' not in t:
        fields(t,'offset count codec palette_offset palette_format');number(t['count'],1,1024)
        if type(t['codec']) is not str or t['codec'] not in CODECS:raise ValueError('unsupported declared tile codec')
        colors=2**CODECS[t['codec']]
        parts=[{'first':0,'count':t['count'],'offset':t['offset'],'codec':t['codec'],'pixel_map':list(range(colors))}]
    else:
        fields(t,'count color_count segments palette_offset palette_format');number(t['count'],1,1024);number(t['color_count'],2,256)
        colors=t['color_count']
        if colors&(colors-1):raise ValueError('tile palette size must be a power of two')
        parts=t['segments']
        if type(parts) is not list or not 1<=len(parts)<=64:raise ValueError('declare one to 64 tile segments')
    tiles=[None]*t['count'];segments=[]
    for i,part in enumerate(parts):
        fields(part,'first count offset codec pixel_map');number(part['first'],0,t['count']-1);number(part['count'],1,t['count'])
        if part['first']+part['count']>t['count']:raise ValueError('tile segment exceeds the virtual tile collection')
        if type(part['codec']) is not str or part['codec'] not in CODECS:raise ValueError('unsupported declared tile codec')
        mapping=part['pixel_map'];source_colors=2**CODECS[part['codec']]
        if type(mapping) is not list or len(mapping)!=source_colors:raise ValueError('source pixel mapping differs from codec depth')
        for value in mapping:number(value,0,colors-1)
        if len(set(mapping))!=len(mapping):raise ValueError('source pixel mapping must be reversible')
        unit=cell_size(part['codec'],8,8);storage(part['offset'],part['count']*unit,'tiles' if 'segments' not in t else 'tiles segment'+str(i))
        for j in range(part['count']):
            at=part['offset']+j*unit;index=part['first']+j
            if tiles[index] is not None:raise ValueError('tile segments overlap in virtual placement')
            pixels=decode_cell(raw[at:at+unit],codec=part['codec'],width=8,height=8)
            tiles[index]=[mapping[value] for value in pixels]
        segments.append(dict(part))
    if any(tile is None for tile in tiles):raise ValueError('tile segments leave an unresolved virtual tile')
    return tiles,colors,segments


def encode_tiles(tiles,segments):
    writes=[]
    for segment in segments:
        reverse={value:index for index,value in enumerate(segment['pixel_map'])};encoded=bytearray()
        for pixels in tiles[segment['first']:segment['first']+segment['count']]:
            if any(value not in reverse for value in pixels):raise ValueError('pixel cannot be represented by its stored tile segment')
            encoded+=encode_cell([reverse[value] for value in pixels],codec=segment['codec'],width=8,height=8)
        writes.append((segment['offset'],bytes(encoded)))
    return writes
