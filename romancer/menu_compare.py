"""Bounded captured-pixel comparison; no menu or transaction semantics."""
import hashlib
import io
import json
import struct
import warnings
import zlib

from . import ROMANCER_VERSION, capture_store
from .script_schema import canonical_bytes


MAX_PNG = 16 * 1024 * 1024
MAX_RGB = 8 * 1024 * 1024
MAX_PIXELS = 1048576
MAX_REPORT = 8 * 1024 * 1024
IDENTITIES = ('source_sha256', 'source_size', 'schema_sha256', 'document_id',
              'menu_document_id', 'profile_sha256', 'glyph_map_sha256', 'font_sha256',
              'font_size', 'font_schema_sha256', 'metrics_id', 'cases_sha256', 'preview_id')


def _base_result():
    result = dict(schema_version=1, comparison_version=1, tool_version=ROMANCER_VERSION,
                  operation='menu-compare', scope='captured_region_pixels', ok=False,
                  status='BLOCKED', written=False, cancelled=False, preview_status='NOT_RUN',
                  comparison_status='NOT_RUN', transaction_status='NOT_RUN',
                  actual_transaction_verified=False, native_capture_verified=False,
                  native_render_verified=False, state_semantics_verified=False,
                  build_currentness='NOT_CHECKED', outside_region_compared=False,
                  comparison_id=None, request_sha256=None, request=None, preview=None,
                  comparisons=[], case_coverage=[], capture_records={},
                  requested_scope={}, exercised_scope={}, warnings=[])
    result.update(dict.fromkeys(IDENTITIES))
    return result


def _error(exc, phase):
    return dict(phase=str(getattr(exc, 'phase', phase))[:128],
                code=str(getattr(exc, 'code', type(exc).__name__))[:128],
                message='Operation cancelled' if isinstance(exc, KeyboardInterrupt) else str(exc)[:2048])


def _status(statuses):
    for value in ('BLOCKED', 'FAIL', 'PASS'):
        if value in statuses:
            return value
    return 'NOT_RUN'


def _check_report(result):
    canonical_bytes(result, max_bytes=MAX_REPORT)
    size = 1  # The CLI's final newline is part of the wire-size bound.
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2)
    for piece in encoder.iterencode(result):
        size += len(piece)
        if size > MAX_REPORT:
            raise ValueError('comparison report exceeds 8 MiB pretty JSON bound')


def _record_evidence(result, record):
    digest = hashlib.sha256(canonical_bytes(record, max_bytes=64 * 1024)).hexdigest()
    capture_id = record['capture_id']
    previous = result['capture_records'].get(capture_id)
    if previous is not None and previous['record_sha256'] != digest:
        raise ValueError('capture immutable record changed during comparison')
    result['capture_records'][capture_id] = dict(record_sha256=digest, record=record)


def _compare_pair(project, pair, result):
    row = dict(id=pair['id'], case_id=pair['case_id'], region=pair['region'],
               relation=pair['relation'], target=pair['target']['capture_id'],
               reference=pair['reference']['capture_id'], scope='captured_region_pixels',
               status='NOT_RUN', total_pixels=0, different_pixels=None, difference_bounds=None,
               context_differences=[], native_capture_verified=False, native_render_verified=False,
               state_semantics_verified=False, transaction_status='NOT_RUN',
               actual_transaction_verified=False, outside_region_compared=False,
               build_currentness='NOT_CHECKED')
    result['comparisons'].append(row)
    phase = 'capture_retrieval'
    try:
        target, a = _read_native_capture(project, pair['target'])
        _record_evidence(result, target)
        reference, b = _read_native_capture(project, pair['reference'])
        _record_evidence(result, reference)
        row['native_capture_verified'] = True
        phase = 'capture_context'
        row['context_differences'] = _check_pair_context(target, reference)
        _check_membership(target, pair['target'],
                          (result['source_sha256'], result['source_size']),
                          (result['font_sha256'], result['font_size']))
        phase = 'pixel_comparison'
        pixels = compare_rgb_region(a, b, target['image']['width'], target['image']['height'],
                                    pair['region'])
        row.update(pixels)
        matched = (pixels['different_pixels'] == 0) == (pair['relation'] == 'equal')
        row['status'] = 'PASS' if matched else 'FAIL'
    except (ValueError, OSError) as exc:
        row.update(status='BLOCKED', error=_error(exc, phase))


def compare_menu_captures(project, source, script_schema: dict, profile: dict,
                          cases: dict, font_schema: dict, font, request: dict) -> dict:
    """Recompute a held preview, then compare exact retrieved native capture pixels."""
    from . import menu, menu_schema

    result, phase = _base_result(), 'comparison_request'
    try:
        validated = menu_schema.validate_menu_comparison(request)
        request = validated['normalized']
        result.update(request=request, request_sha256=validated['sha256'])
        pairs = request['pairs']
        total = sum(pair['region'][2] * pair['region'][3] for pair in pairs)
        unique = {pair[side]['capture_id'] for pair in pairs for side in ('target', 'reference')}
        if not 1 <= len(pairs) <= 16 or len(unique) > 32 or total > MAX_PIXELS:
            raise ValueError('capture pair/unique capture/aggregate pixel budget exceeded')
        result['requested_scope'] = dict(pair_ids=[pair['id'] for pair in pairs],
                                         case_ids=sorted({pair['case_id'] for pair in pairs}),
                                         total_pixels=total, unique_captures=len(unique))
        phase = 'menu_preview'
        with menu._preview_inputs(source, script_schema, profile, cases, font_schema, font) as preview:
            result['preview'] = preview
            result.update({key: preview.get(key) for key in IDENTITIES})
            result['preview_status'] = preview['status']
            result['case_coverage'] = [dict(case_id=case['id'], comparison_status='NOT_RUN', pair_ids=[])
                                       for case in preview.get('cases', [])]
            if preview.get('ok') is not True or preview['status'] != 'PASS':
                result['status'] = preview['status'] if preview['status'] in ('FAIL', 'BLOCKED') else 'BLOCKED'
                if preview.get('error'):
                    result['error'] = preview['error']
            else:
                phase = 'preview_binding'
                if preview['preview_id'] != request['expected_preview_id']:
                    raise ValueError('expected preview_id does not match fresh preview')
                coverage = {row['case_id']: row for row in result['case_coverage']}
                if any(pair['case_id'] not in coverage for pair in pairs):
                    raise ValueError('comparison case_id is not in fresh preview cases')
                for pair in pairs:
                    coverage[pair['case_id']]['pair_ids'].append(pair['id'])
                phase = 'capture_comparison'
                # Only this pair's two RGB buffers survive decoding; records remain bounded metadata.
                for pair in pairs:
                    _compare_pair(project, pair, result)
                for row in result['case_coverage']:
                    row['comparison_status'] = _status([item['status'] for item in result['comparisons']
                                                       if item['case_id'] == row['case_id']])
                result['comparison_status'] = _status([row['status'] for row in result['comparisons']])
                result['status'] = result['comparison_status']
                result['ok'] = result['status'] == 'PASS'
                result['native_capture_verified'] = all(row['native_capture_verified']
                                                        for row in result['comparisons'])
                result['exercised_scope'] = dict(
                    pair_ids=[row['id'] for row in result['comparisons'] if row['status'] in ('PASS', 'FAIL')],
                    total_pixels=sum(row['total_pixels'] for row in result['comparisons']))
                if result['comparison_status'] in ('PASS', 'FAIL'):
                    identity = dict(comparison_version=1, tool_version=ROMANCER_VERSION,
                                    preview_id=result['preview_id'], request_sha256=result['request_sha256'],
                                    capture_record_hashes={key: value['record_sha256']
                                                          for key, value in result['capture_records'].items()})
                    result['comparison_id'] = hashlib.sha256(canonical_bytes(identity, max_bytes=MAX_REPORT)).hexdigest()
            phase = 'response_encoding'
            _check_report(result)
            phase = 'final_identity'
        return result
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        cancelled = isinstance(exc, KeyboardInterrupt) or getattr(exc, 'status', None) == 'CANCELLED'
        status = 'CANCELLED' if cancelled else 'BLOCKED'
        if phase == 'menu_preview':
            if not cancelled and getattr(exc, 'status', None) == 'FAIL':
                status = 'FAIL'
            result['preview_status'] = status
        result.update(ok=False, status=status, cancelled=cancelled,
                      comparison_status='BLOCKED', comparison_id=None, native_capture_verified=False,
                      error=_error(exc, phase))
        if phase == 'menu_preview':
            result['comparison_status'] = 'NOT_RUN'
        if phase == 'response_encoding':
            small = _base_result()
            small.update({key: result[key] for key in (*IDENTITIES, 'status', 'cancelled', 'preview_status',
                          'comparison_status', 'error', 'request_sha256', 'requested_scope')})
            return small
        try:
            _check_report(result)
        except (ValueError, RecursionError):
            small = _base_result()
            small.update(status=result['status'], cancelled=cancelled, comparison_status='BLOCKED',
                         error=result['error'])
            return small
        return result


def _check_membership(record, selector, source_identity, font_identity):
    build = record['build']['identity']
    for key, expected in (('source_role', source_identity), ('font_role', font_identity)):
        role = selector[key]
        matches = [row for row in build['inputs'] if row['role'] == role]
        if role == 'output':
            matches.append(build['output'])
        if len(matches) != 1:
            raise ValueError('missing or ambiguous build artifact role: ' + role)
        artifact = matches[0]
        if (artifact['sha256'], artifact['size']) != expected:
            raise ValueError('fresh source/font does not match build artifact role: ' + role)


def _check_pair_context(target, reference):
    if target['capture_id'] == reference['capture_id']:
        raise ValueError('same capture cannot be both comparison operands')
    for key in ('width', 'height'):
        if target['image'][key] != reference['image'][key]:
            raise ValueError('capture dimensions mismatch: ' + key)
    for key in ('core_sha256', 'core_options', 'run_mode'):
        if target['run'][key] != reference['run'][key]:
            raise ValueError('capture run context mismatch: ' + key)
    differences = ['run.' + key for key in sorted(target['run'])
                   if target['run'][key] != reference['run'][key]]
    if target['build']['build_id'] != reference['build']['build_id']:
        differences.insert(0, 'build_id')
    return differences


def _read_native_capture(project, selector):
    stored = capture_store.get_capture(project, selector['capture_id'])
    if stored.get('ok') is not True or stored.get('image_integrity') != 'PASS':
        raise ValueError('capture retrieval did not verify image integrity')
    if stored.get('runtime_trusted') is False:raise ValueError('historical imported capture cannot establish current native authority')
    record = stored['record']
    if (record['origin'] != 'native_worker' or record['build'] is None
            or record['build']['association'] != 'measured_run_output'):
        raise ValueError('native_worker measured_run_output capture required')
    actual = dict(capture_id=record['capture_id'], build_id=record['build']['build_id'],
                  png_sha256=record['image']['blob_sha256'],
                  rgb_sha256=record['image']['rgb_sha256'])
    if any(selector[key] != value for key, value in actual.items()):
        raise ValueError('capture selector does not match stored identity')
    return record, _decode_capture_png(stored['png_bytes'], record['image'])


def _dimensions(width, height):
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= 4096 or not 1 <= height <= 4096
            or width * height * 3 > MAX_RGB):
        raise ValueError('capture dimensions exceed RGB24 bounds')


def _region(region, width, height):
    if (type(region) is not list or len(region) != 4
            or any(type(value) is not int for value in region)):
        raise ValueError('region must be four integers')
    x, y, w, h = region
    if (x < 0 or y < 0 or w < 1 or h < 1 or x + w > width
            or y + h > height or w * h > MAX_PIXELS):
        raise ValueError('region exceeds image or comparison pixel bounds')
    return x, y, w, h


def compare_rgb_region(a: bytes, b: bytes, width: int, height: int,
                       region: list[int]) -> dict:
    """Compare RGB24 pixels in one identical ROI; bounds are absolute half-open."""
    _dimensions(width, height)
    if (type(a) is not bytes or type(b) is not bytes
            or len(a) != width * height * 3 or len(b) != len(a)):
        raise ValueError('complete RGB24 buffers required')
    x, y, w, h = _region(region, width, height)
    different, left, top, right, bottom = 0, width, height, 0, 0
    for row in range(y, y + h):
        for col in range(x, x + w):
            offset = (row * width + col) * 3
            if a[offset:offset + 3] != b[offset:offset + 3]:
                different += 1
                left, top = min(left, col), min(top, row)
                right, bottom = max(right, col + 1), max(bottom, row + 1)
    return dict(total_pixels=w * h, different_pixels=different,
                difference_bounds=[left, top, right, bottom] if different else None)


def _png_framing(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('PNG input required')
    offset, view = 8, memoryview(raw)
    # Pillow.verify does not validate terminal IEND CRC or require EOF after it.
    while offset < len(raw):
        if len(raw) - offset < 12:
            raise ValueError('truncated PNG chunk framing')
        length = struct.unpack_from('>I', raw, offset)[0]
        end = offset + length + 12
        if end > len(raw):
            raise ValueError('PNG chunk exceeds available bytes')
        kind = raw[offset + 4:offset + 8]
        if zlib.crc32(view[offset + 4:end - 4]) != struct.unpack_from('>I', raw, end - 4)[0]:
            raise ValueError('PNG chunk CRC mismatch')
        if kind in (b'acTL', b'fcTL', b'fdAT'):
            raise ValueError('animated PNG is outside capture comparison scope')
        if kind == b'IEND':
            if length or end != len(raw):
                raise ValueError('PNG requires an empty terminal IEND at EOF')
            return
        offset = end
    raise ValueError('PNG is missing terminal IEND')


def _decode_capture_png(raw, metadata):
    """Decode verified stored bytes, independently rechecking file and pixel identity."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PNG:
        raise ValueError('capture PNG exceeds byte bound')
    if (len(raw) != metadata['byte_size']
            or hashlib.sha256(raw).hexdigest() != metadata['blob_sha256']):
        raise ValueError('capture PNG byte identity mismatch')
    _dimensions(metadata['width'], metadata['height'])
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError('Pillow is required for capture pixel comparison') from exc
    _png_framing(raw)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=['PNG']) as image:
                width, height = image.size
                _dimensions(width, height)
                if (width, height) != (metadata['width'], metadata['height']):
                    raise ValueError('decoded PNG dimensions mismatch capture record')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('animated PNG is outside capture comparison scope')
                image.verify()
            with Image.open(io.BytesIO(raw), formats=['PNG']) as image:
                image.load()
                with image.convert('RGB') as rgb:
                    pixels = rgb.tobytes()
        if (len(pixels) != width * height * 3
                or hashlib.sha256(pixels).hexdigest() != metadata['rgb_sha256']):
            raise ValueError('decoded RGB identity mismatch capture record')
        return pixels
    except (OSError, SyntaxError, Warning, Image.DecompressionBombError) as exc:
        raise ValueError('invalid or out-of-bounds PNG decode: ' + str(exc)) from exc
