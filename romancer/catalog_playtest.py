"""Exact-ROM observations from the bundled Windows cores."""

from functools import lru_cache
import json
from pathlib import Path

from .core_pins import CORE_PINS, WINDOWS_CORE_PINS
from .rom_sample_db import HASH, _fields, _hash, _int
from .script_schema import _nonfinite, _unique_object

REPORT_PATH = Path(__file__).resolve().parents[1] / 'knowledge/catalog_playtest.json'
CHECKPOINTS = (120, 360, 600)
FAMILIES = {'gbc': 'gb', 'sms': 'genesis'}
INPUT = ('not_checked', 'changed_frame', 'no_frame_change', 'inconclusive')
STATE = ('not_checked', 'save_refused', 'load_refused', 'matched', 'different')
STAGES = ('preflight', 'load', 'boot', 'save_state', 'input_control', 'load_state', 'input', 'replay', 'close')


def engine_for(system):
    return CORE_PINS.get(FAMILIES.get(system, system))


def validate(report):
    extra = ' confirmed_routes' if isinstance(report, dict) and 'confirmed_routes' in report else ''
    _fields(report, 'schema_version procedure runtime_version records'+extra)
    if (type(report['schema_version']) is not int or report['schema_version'] != 1
            or report['procedure'] != 'boot-input-replay-v1'
            or report['runtime_version'] != '1.0.57'
            or type(report['records']) is not list or len(report['records']) > 20000):
        raise ValueError('Unsupported catalog playtest report.')
    result = {}
    for row in report['records']:
        extra = ' failure_stage' if isinstance(row, dict) and 'failure_stage' in row else ''
        _fields(row, 'sha256 system_id size core_sha256 loaded frames input state clean_close'+extra)
        _hash(row['sha256'])
        _int(row['size'], 1, 64 * 1024**2)
        system = row['system_id']
        engine = engine_for(system) if type(system) is str else None
        if (engine is None or row['core_sha256'] != engine['sha256'] or row['sha256'] in result
                or type(row['loaded']) is not bool or type(row['clean_close']) is not bool
                or row['input'] not in INPUT or row['state'] not in STATE
                or row.get('failure_stage') not in (None, *STAGES)
                or type(row['frames']) is not list or len(row['frames']) > len(CHECKPOINTS)):
            raise ValueError('Invalid catalog playtest observation.')
        previous = 0
        for frame in row['frames']:
            if (type(frame) is not list or len(frame) != 5 or type(frame[0]) is not int
                    or frame[0] not in CHECKPOINTS or frame[0] <= previous or type(frame[1]) is not bool):
                raise ValueError('Invalid catalog playtest frame.')
            _int(frame[2], 1, 4096)
            _int(frame[3], 1, 4096)
            _hash(frame[4])
            previous = frame[0]
        if (not row['loaded'] and (row['frames'] or row['clean_close'] or row['state'] != 'not_checked'
                                   or row['input'] != 'not_checked')
                or row['input'] in ('changed_frame', 'no_frame_change') and row['state'] != 'matched'
                or row['input'] == 'inconclusive' and row['state'] != 'different'
                or row['clean_close'] == ('failure_stage' in row)):
            raise ValueError('Catalog playtest checks contradict each other.')
        result[row['sha256']] = row
    confirmed = report.get('confirmed_routes', [])
    if type(confirmed) is not list or len(confirmed) > 20_000:
        raise ValueError('Invalid confirmed route inventory.')
    from .bundled_cores import cartridge_engine
    from .libretro_frontend import BUTTON_IDS
    for proof in confirmed:
        _fields(proof, 'sha256 core_sha256 title_frame title_sha256 gameplay_frame gameplay_sha256 idle_sha256 buttons state')
        for key in ('sha256','core_sha256','title_sha256','gameplay_sha256','idle_sha256'):
            _hash(proof[key])
        original = result.get(proof['sha256'])
        if original is None or original['loaded'] or 'confirmed' in original:
            raise ValueError('Confirmed route does not match an original load refusal.')
        engine_id, compatibility = cartridge_engine(original['system_id'], proof['sha256'])
        if not compatibility or WINDOWS_CORE_PINS[engine_id]['sha256'] != proof['core_sha256']:
            raise ValueError('Confirmed route has a different engine identity.')
        _int(proof['title_frame'], 1, 36_000)
        _int(proof['gameplay_frame'], proof['title_frame']+1, 36_000)
        buttons = proof['buttons']
        if (type(buttons) is not list or not 1 <= len(buttons) <= 16
                or any(type(button) is not str or button not in BUTTON_IDS for button in buttons)
                or len(set(buttons)) != len(buttons) or proof['state'] not in STATE
                or proof['gameplay_sha256'] == proof['idle_sha256']):
            raise ValueError('Confirmed route lacks a controlled input comparison.')
        result[proof['sha256']] = {**original, 'confirmed': proof}
    return result


@lru_cache(maxsize=1)
def _load(path, size, stamp):
    if size > 8 * 1024**2:
        raise ValueError('Catalog playtest report exceeds its byte budget.')
    with path.open('rb') as stream:
        raw = stream.read(8 * 1024**2 + 1)
    if len(raw) != size:
        raise ValueError('Catalog playtest report size changed.')
    return validate(json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite))


def records():
    try:
        stat = REPORT_PATH.stat()
    except FileNotFoundError:
        return {}
    return _load(REPORT_PATH, stat.st_size, stat.st_mtime_ns)


def lookup(sha256, size, system):
    if not isinstance(sha256, str) or HASH.fullmatch(sha256) is None:
        raise ValueError('Invalid playtest source identity.')
    record = records().get(sha256)
    if record is None or (record['size'], record['system_id']) != (size, system):
        return {'status': 'not_recorded'}
    if proof := record.get('confirmed'):
        from .bundled_cores import cartridge_engine
        engine_id, _ = cartridge_engine(system, sha256)
        return {
            'status': 'recorded', 'engine': CORE_PINS[engine_id]['name'],
            'core_sha256': proof['core_sha256'], 'loaded': True, 'first_varied_frame': None,
            'frames_sampled': [proof['title_frame'], proof['gameplay_frame']],
            'input': 'changed_frame', 'state': proof['state'], 'clean_close': True,
            'failure_stage': None, 'title_confirmed': True, 'gameplay_confirmed': True,
        }
    frames = record['frames']
    return {
        'status': 'recorded', 'engine': engine_for(system)['name'],
        'core_sha256': record['core_sha256'], 'loaded': record['loaded'],
        'first_varied_frame': next((frame[0] for frame in frames if frame[1]), None),
        'frames_sampled': [frame[0] for frame in frames],
        'input': record['input'], 'state': record['state'], 'clean_close': record['clean_close'],
        'failure_stage': record.get('failure_stage'), 'title_confirmed': False,
    }
