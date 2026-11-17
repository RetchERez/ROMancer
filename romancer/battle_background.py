"""Phantasy Star II Rev A battle artwork and plane map."""

import re
import struct

from . import workbench_projects as projects

ORIGINAL_SHA = 'a0bd97f5aaa67301923ccc367511606bd3471ea9542919165311d4a23a2b696b'
ROM_SIZE = 786432
WIDTH, HEIGHT = 320, 128
ART_OFFSET = 0x7567A
MAP_OFFSET = 0x75BD8
MAP_BYTES = WIDTH * HEIGHT // 32
PALETTE_OFFSET = 0x11D44
ART_CAPACITY = MAP_OFFSET - ART_OFFSET
FIRST_TILE = 0x781
MAX_TILES = 104

# These game instructions select the verified art, map size and palette.
LOADER_OFFSET = 0x8544
LOADER = bytes.fromhex(
    '23fc7020000300c0000441f90007567a6100d93843f900075bd8'
    '203c660000037227740f6100d900702f6100e5e8'
)
PALETTE_POINTER = 0x1197C + 0x2F * 8
PALETTE_RECORD = bytes.fromhex('00011d44fb00001f')


class BackgroundCapacityError(ValueError):
    """A valid image exceeds the game's verified graphics allocation."""


def decode_art(data):
    cursor = 0
    tiles = []
    while cursor < len(data):
        definitions = data[cursor]
        cursor += 1
        if definitions & 0x80:
            return tiles
        if len(tiles) == MAX_TILES or definitions > 32:
            raise ValueError('The battle graphics exceed the original tile allocation.')
        tile = bytearray(32)
        covered = 0
        for _ in range(definitions):
            if cursor + 5 > len(data):
                raise ValueError('A battle graphics byte mask is truncated.')
            value, mask = struct.unpack_from('>BI', data, cursor)
            cursor += 5
            if covered & mask:
                raise ValueError('The battle graphics contain overlapping byte masks.')
            covered |= mask
            for position in range(32):
                if mask & (1 << (31 - position)):
                    tile[position] = value
        for position in range(32):
            if not covered & (1 << (31 - position)):
                if cursor == len(data):
                    raise ValueError('A battle graphics tile is truncated.')
                tile[position] = data[cursor]
                cursor += 1
        tiles.append(bytes(tile))
    raise ValueError('The battle graphics are missing their terminator.')


def decode_map(data, tiles):
    if len(data) != MAP_BYTES:
        raise ValueError('The battle tilemap must be 40 × 16 tiles.')
    pixels = bytearray(WIDTH * HEIGHT)
    for index, (entry,) in enumerate(struct.iter_unpack('>H', data)):
        if entry == 0:
            continue
        tile_id = (entry & 0x7FF) - FIRST_TILE
        if entry & 0xE000 or not 0 <= tile_id < len(tiles):
            raise ValueError('The battle map refers to an unavailable tile or palette.')
        flip_x, flip_y = entry & 0x0800, entry & 0x1000
        row, column = divmod(index, WIDTH // 8)
        for y in range(8):
            packed = tiles[tile_id][(7 - y if flip_y else y) * 4:][:4]
            expanded = bytes(pixel for pair in packed for pixel in (pair >> 4, pair & 15))
            start = (row * 8 + y) * WIDTH + column * 8
            pixels[start:start + 8] = expanded[::-1] if flip_x else expanded
    return bytes(pixels)


def encode_tile(tile):
    masks = {}
    counts = {}
    for index, byte in enumerate(tile):
        masks[byte] = masks.get(byte, 0) | (1 << (31 - index))
        counts[byte] = counts.get(byte, 0) + 1
    definitions = {byte: mask for byte, mask in masks.items() if counts[byte] > 5}
    return (
        bytes([len(definitions)])
        + b''.join(struct.pack('>BI', byte, mask) for byte, mask in definitions.items())
        + bytes(byte for byte in tile if byte not in definitions)
    )


def encode_scene(pixels):
    if len(pixels) != WIDTH * HEIGHT or any(pixel > 15 for pixel in pixels):
        raise ValueError('Use a 320 × 128 image with colors from the 16-color battle palette.')
    tiles = []
    by_pixels = {bytes(64): 0}
    tilemap = bytearray()
    for row in range(0, HEIGHT, 8):
        for column in range(0, WIDTH, 8):
            tile_rows = tuple(pixels[y * WIDTH + column:y * WIDTH + column + 8] for y in range(row, row + 8))
            flat = b''.join(tile_rows)
            if flat not in by_pixels:
                if len(tiles) == MAX_TILES:
                    raise BackgroundCapacityError('This image needs more than 104 unique tiles. Try reusing shapes or removing fine details.')
                tile_id = FIRST_TILE + len(tiles)
                tiles.append(encode_tile(bytes(a << 4 | b for a, b in zip(flat[::2], flat[1::2]))))
                for flip in (0, 0x0800, 0x1000, 0x1800):
                    rows = tile_rows[::-1] if flip & 0x1000 else tile_rows
                    view = b''.join(line[::-1] for line in rows) if flip & 0x0800 else b''.join(rows)
                    by_pixels.setdefault(view, tile_id | flip)
            tilemap.extend(struct.pack('>H', by_pixels[flat]))
    art = b''.join(tiles) + b'\xff'
    if len(art) > ART_CAPACITY:
        raise BackgroundCapacityError(f'This image takes {len(art):,} graphics bytes. There is room for {ART_CAPACITY:,}. Try simplifying textures.')
    return art, bytes(tilemap), len(tiles)


def matches(project, row):
    if row.get('size') != ROM_SIZE or row.get('layout_changed'):
        return False
    value = projects.read_project(project)
    artifacts = {item['artifact_id']: item for item in value['sources'] + value['builds']}
    seen = set()
    while row and row['artifact_id'] not in seen:
        if row['kind'] == 'source':
            return row['sha256'] == ORIGINAL_SHA
        seen.add(row['artifact_id'])
        row = artifacts.get(row.get('source_id'))
    return False


def read_scene(path):
    data = path.read_bytes()
    if (
        len(data) != ROM_SIZE
        or data[LOADER_OFFSET:LOADER_OFFSET + len(LOADER)] != LOADER
        or data[PALETTE_POINTER:PALETTE_POINTER + len(PALETTE_RECORD)] != PALETTE_RECORD
    ):
        raise ValueError('This build changed the battle loader or palette layout. Open the supported original revision.')
    tiles = decode_art(data[ART_OFFSET:MAP_OFFSET])
    pixels = decode_map(data[MAP_OFFSET:MAP_OFFSET + MAP_BYTES], tiles)
    colors = [
        [(word >> shift & 7) * 255 // 7 for shift in (1, 5, 9)]
        for (word,) in struct.iter_unpack('>H', data[PALETTE_OFFSET:PALETTE_OFFSET + 32])
    ]
    return data, pixels, colors, len(tiles)


def inspect(path):
    _, pixels, palette, count = read_scene(path)
    return {
        'available': True, 'width': WIDTH, 'height': HEIGHT,
        'pixels': ''.join(format(pixel, 'x') for pixel in pixels),
        'palette': palette, 'tiles_used': count, 'tiles_limit': MAX_TILES,
    }


def prepare_edit(path, pixel_text):
    if not isinstance(pixel_text, str) or not re.fullmatch(r'[0-9a-f]{40960}', pixel_text):
        raise ValueError('The draft must contain one palette index for each pixel.')
    data, original, _, _ = read_scene(path)
    edited = bytes(int(value, 16) for value in pixel_text)
    if original == edited:
        raise ValueError('Change the backdrop before reviewing ROM bytes.')
    art, tilemap, count = encode_scene(edited)
    edits = [
        {'offset': offset, 'before': data[offset:offset + len(new)].hex(), 'after': new.hex()}
        for offset, new in ((ART_OFFSET, art), (MAP_OFFSET, tilemap))
        if data[offset:offset + len(new)] != new
    ]
    return edits, count, len(art)
