"""Raw Mode 1/2352 payload mapping and ECMA-130 sector integrity.

Only unscrambled single-format Mode 1 sectors are writable. See
docs/CD_INTEGRITY_REFERENCE.md for the independent verification procedure.
"""

SECTOR_SIZE = 2352
PAYLOAD_OFFSET = 16
PAYLOAD_SIZE = 2048
SYNC = b'\x00' + b'\xff' * 10 + b'\x00'


def payload_spans(extent: int, offset: int, length: int) -> list[dict]:
    if any(type(v) is not int for v in (extent, offset, length)):
        raise ValueError('extent, offset and length must be integers')
    if extent < 0 or offset < 0 or length <= 0:
        raise ValueError('extent/offset must be nonnegative and length positive')
    spans = []
    consumed = 0
    while consumed < length:
        relative, intra = divmod(offset + consumed, PAYLOAD_SIZE)
        count = min(PAYLOAD_SIZE - intra, length - consumed)
        index = extent + relative
        spans.append({'sector': index, 'payload_offset': intra,
                      'data_offset': consumed, 'length': count,
                      'raw_offset': index * SECTOR_SIZE + PAYLOAD_OFFSET + intra})
        consumed += count
    return spans


def _edc_table() -> tuple[int, ...]:
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0xD8018001 if value & 1 else 0)
        table.append(value)
    return tuple(table)


_EDC = _edc_table()
_DOUBLE = tuple(((v << 1) ^ (0x11D if v & 128 else 0)) for v in range(256))
_DIVIDE_THREE = [0] * 256
for _value in range(256):
    _DIVIDE_THREE[_value ^ _DOUBLE[_value]] = _value


def _edc(data: bytes) -> bytes:
    remainder = 0
    for value in data:
        remainder = (remainder >> 8) ^ _EDC[(remainder ^ value) & 255]
    return remainder.to_bytes(4, 'little')


def _parity(data: bytes, words: int, symbols: int, stride: int, step: int) -> bytes:
    result = bytearray(words * 2)
    size = words * symbols
    for word in range(words):
        position = (word // 2) * stride + (word % 2)
        weighted = total = 0
        for _ in range(symbols):
            value = data[position]
            total ^= value
            weighted = _DOUBLE[weighted ^ value]
            position = (position + step) % size
        first = _DIVIDE_THREE[_DOUBLE[weighted] ^ total]
        result[word] = first
        result[word + words] = first ^ total
    return bytes(result)


def _check_header(sector: bytes) -> None:
    if len(sector) != SECTOR_SIZE:
        raise ValueError('expected exactly 2352 bytes per raw sector')
    if sector[:12] != SYNC or sector[15] != 1:
        raise ValueError('unsupported or corrupt sector: expected raw Mode 1')
    for value, maximum in zip(sector[12:15], (99, 59, 74)):
        high, low = divmod(value, 16)
        if high > 9 or low > 9 or high * 10 + low > maximum:
            raise ValueError('invalid BCD sector address')


def repair_mode1(sector: bytes) -> bytes:
    _check_header(sector)
    result = bytearray(sector)
    result[2064:2068] = _edc(result[:2064])
    result[2068:2076] = bytes(8)
    result[2076:2248] = _parity(result[12:2076], 86, 24, 2, 86)
    result[2248:2352] = _parity(result[12:2248], 52, 43, 86, 88)
    return bytes(result)


def validate_mode1(sector: bytes) -> None:
    _check_header(sector)
    expected = repair_mode1(sector)
    for name, start, end in [('EDC', 2064, 2068), ('reserved', 2068, 2076),
                             ('ECC P', 2076, 2248), ('ECC Q', 2248, 2352)]:
        if sector[start:end] != expected[start:end]:
            raise ValueError(f'invalid Mode 1 {name} bytes')
