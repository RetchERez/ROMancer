"""Stored level-palette colors, with exact preservation of unused channel bits."""
from .asset_schema import number

FORMATS={
    'rgb888':(3,'big',(16,8,0),255),
    'rgb555-le':(2,'little',(0,5,10),31),
    'rgb555-be':(2,'big',(0,5,10),31),
    'genesis':(2,'big',(1,5,9),7),
    'sms-rgb222':(1,'little',(0,2,4),3),
}


def _layout(format):
    if type(format) is not str or format not in FORMATS:raise ValueError('unsupported declared level palette')
    return FORMATS[format]


def entry_size(format):return _layout(format)[0]


def storage_length(format,count):
    number(count,1,256)
    if format=='dmg-shades':
        if count!=4:raise ValueError('a Game Boy shade register supplies four colors')
        return 1
    return entry_size(format)*count


def decode_palette(raw,format,count):
    length=storage_length(format,count)
    if type(raw) not in (bytes,bytearray) or len(raw)!=length:raise ValueError('level palette storage length differs')
    if format=='dmg-shades':
        return [[(255,170,85,0)[(raw[0]>>(2*i))&3]]*3 for i in range(4)]
    size,endian,shifts,maximum=_layout(format);number(count,1,256)
    if type(raw) not in (bytes,bytearray) or len(raw)!=size*count:raise ValueError('level palette storage length differs')
    return [[round(((int.from_bytes(raw[i*size:(i+1)*size],endian)>>shift)&maximum)*255/maximum) for shift in shifts] for i in range(count)]


def encode_palette(colors,format,original):
    if format=='dmg-shades':
        if type(colors) is not list or len(colors)!=4 or type(original) not in (bytes,bytearray) or len(original)!=1:
            raise ValueError('a Game Boy shade register supplies four colors')
        value=0
        for index,rgb in enumerate(colors):
            if type(rgb) is not list or len(rgb)!=3:raise ValueError('level palette needs RGB triples')
            for channel in rgb:number(channel,0,255)
            if rgb[0]!=rgb[1] or rgb[0]!=rgb[2] or rgb[0] not in (255,170,85,0):raise ValueError('Game Boy shade registers store only the four monochrome shades')
            value|=(255,170,85,0).index(rgb[0])<<(2*index)
        return bytes([value])
    size,endian,shifts,maximum=_layout(format)
    if type(colors) is not list or not 1<=len(colors)<=256 or type(original) not in (bytes,bytearray) or len(original)!=len(colors)*size:
        raise ValueError('level palette storage length differs')
    mask=sum(maximum<<shift for shift in shifts);result=bytearray()
    for i,rgb in enumerate(colors):
        if type(rgb) is not list or len(rgb)!=3:raise ValueError('level palette needs RGB triples')
        for channel in rgb:number(channel,0,255)
        reserved=int.from_bytes(original[i*size:(i+1)*size],endian)&~mask
        value=reserved|sum(round(channel*maximum/255)<<shift for channel,shift in zip(rgb,shifts))
        result+=value.to_bytes(size,endian)
    return bytes(result)
