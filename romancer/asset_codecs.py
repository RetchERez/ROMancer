"""Literal uncompressed pixel codecs, without console or color guesses."""

CODECS = {'tile8-rowplanar4-msb-v1': 4, 'tile8-paired2-msb-v1': 2, 'tile8-packed4-low-v1': 4, 'mono-row-msb-v1': 1, 'tile8-planar2-msb-v1': 2,
          'tile8-paired4-msb-v1': 4, 'tile8-packed4-high-v1': 4}


def cell_size(codec: str, width: int, height: int) -> int:
    if codec not in CODECS or any(type(n) is not int or not 1 <= n <= 32 for n in (width, height)):
        raise ValueError('unsupported codec or dimensions')
    if codec == 'mono-row-msb-v1':
        return ((width + 7) // 8) * height
    if (width, height) != (8, 8):
        raise ValueError('tile codecs require exactly 8 by 8 pixels')
    return 16 if CODECS[codec] == 2 else 32


def decode_cell(raw: bytes, *, codec: str, width: int, height: int) -> list[int]:
    size = cell_size(codec, width, height)
    if type(raw) is not bytes or len(raw) != size:
        raise ValueError('pixel storage length does not match the codec')
    if codec == 'mono-row-msb-v1':
        stride = (width + 7) // 8
        mask = (1 << ((8 - width % 8) % 8)) - 1
        if any(raw[(y + 1) * stride - 1] & mask for y in range(height)):
            raise ValueError('unused mono padding bits must be zero')
        return [(raw[y*stride+x//8] >> (7-x%8)) & 1 for y in range(height) for x in range(width)]
    if codec == 'tile8-packed4-high-v1':
        return [(raw[y*4+x//2] >> (4 if x%2 == 0 else 0)) & 15 for y in range(8) for x in range(8)]
    if codec == 'tile8-packed4-low-v1':
        return [(raw[y*4+x//2] >> (0 if x%2 == 0 else 4)) & 15 for y in range(8) for x in range(8)]
    def plane_offset(plane, y):
        return y*4+plane if codec=='tile8-rowplanar4-msb-v1' else y + plane*8 if codec == 'tile8-planar2-msb-v1' else (plane//2)*16 + y*2 + plane%2
    return [sum(((raw[plane_offset(plane,y)] >> (7-x)) & 1) << plane
                for plane in range(CODECS[codec])) for y in range(8) for x in range(8)]


def encode_cell(pixels: list[int], *, codec: str, width: int, height: int) -> bytes:
    size = cell_size(codec, width, height)
    if (type(pixels) is not list or len(pixels) != width*height
            or any(type(p) is not int or not 0 <= p < (1 << CODECS[codec]) for p in pixels)):
        raise ValueError('pixel array has invalid length, type, or index')
    out = bytearray(size)
    for y in range(height):
        for x in range(width):
            value = pixels[y*width+x]
            if codec == 'mono-row-msb-v1':
                out[y*((width+7)//8)+x//8] |= value << (7-x%8)
            elif codec == 'tile8-packed4-high-v1':
                out[y*4+x//2] |= value << (4 if x%2 == 0 else 0)
            elif codec == 'tile8-packed4-low-v1':
                out[y*4+x//2] |= value << (0 if x%2 == 0 else 4)
            else:
                for plane in range(CODECS[codec]):
                    offset = y*4+plane if codec=='tile8-rowplanar4-msb-v1' else y+plane*8 if codec == 'tile8-planar2-msb-v1' else (plane//2)*16+y*2+plane%2
                    out[offset] |= ((value >> plane) & 1) << (7-x)
    return bytes(out)
