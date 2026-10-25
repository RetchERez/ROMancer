"""Bounded newline JSON for the local emulator worker."""
import json
import math

VERSION = 1
REQUEST_LIMIT = 16 * 1024 * 1024
RESPONSE_LIMIT = 16 * 1024 * 1024
STARTUP_LIMIT = 65536


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate protocol key')
        result[key] = value
    return result


def _float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError('nonfinite protocol number')
    return value


def _constant(text):
    raise ValueError('nonfinite protocol constant')


def decode(data, limit):
    if not data or len(data) > limit or not data.endswith(b'\n'):
        raise ValueError('missing, truncated or oversized protocol message')
    result = json.loads(data.decode('utf-8'), object_pairs_hook=_pairs,
                        parse_float=_float, parse_constant=_constant)
    if type(result) is not dict:
        raise ValueError('protocol message must be an object')
    return result


def encode(value, limit):
    data = (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('ascii')
    if len(data) > limit:
        raise ValueError('protocol message exceeds byte budget')
    return data
