"""Verified no-clobber publication for declared standalone fixed-slot resources."""

from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import tempfile

from . import script as model
from .cd_patch import check_output_paths
from .script_schema import validate_schema


def _owns(path, info):
    if info is None:
        return False
    try:
        return os.path.samestat(path.lstat(), info)
    except FileNotFoundError:
        return False


def _check_temporary(path, info):
    if model._identity(path.lstat()) != model._identity(info):
        raise model.ScriptError('OUTPUT_CHANGED', 'temporary output identity changed')


def _write_all(stream, data):
    view = memoryview(data)
    while view:
        count = stream.write(view)
        if not count:
            raise OSError('output write made no progress')
        view = view[count:]


def _copy_output(source, output, size, hunks):
    source.seek(0)
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        before = source.read(min(model.CHUNK_SIZE, size - offset))
        if not before:
            raise model.ScriptError('SOURCE_CHANGED', 'source truncated during copying')
        digest.update(before)
        after = bytearray(before)
        for hunk in hunks:
            replacement = bytes.fromhex(hunk['after_hex'])
            left = max(offset, hunk['offset'])
            right = min(offset + len(before), hunk['offset'] + len(replacement))
            if left < right:
                after[left - offset:right - offset] = replacement[left - hunk['offset']:right - hunk['offset']]
        _write_all(output, after)
        offset += len(before)
    if source.read(1):
        raise model.ScriptError('SOURCE_CHANGED', 'source grew during copying')
    return digest.hexdigest()


def _verify_output(source, temporary, size, hunks, schema, document):
    """Compare every byte independently of the producer's copy/serialization code."""
    source.seek(0)
    source_digest, output_digest = hashlib.sha256(), hashlib.sha256()
    with temporary.open('rb', buffering=0) as output:
        offset = 0
        while offset < size:
            length = min(model.CHUNK_SIZE, size - offset)
            before, after = source.read(length), output.read(length)
            if len(before) != length or len(after) != length:
                raise model.ScriptError('OUTPUT_SIZE', 'source/output truncated during verification')
            cursor = 0
            for hunk in hunks:
                replacement = bytes.fromhex(hunk['after_hex'])
                left = max(offset, hunk['offset']) - offset
                right = min(offset + length, hunk['offset'] + len(replacement)) - offset
                if left < right:
                    if before[cursor:left] != after[cursor:left]:
                        raise model.ScriptError('NEIGHBOR_CHANGED', 'bytes outside approved slots changed')
                    start = offset + left - hunk['offset']
                    if after[left:right] != replacement[start:start + right - left]:
                        raise model.ScriptError('REPLACEMENT_MISMATCH', 'written slot differs from approved bytes')
                    cursor = right
            if before[cursor:] != after[cursor:]:
                raise model.ScriptError('NEIGHBOR_CHANGED', 'bytes outside approved slots changed')
            source_digest.update(before)
            output_digest.update(after)
            offset += length
        if source.read(1) or output.read(1):
            raise model.ScriptError('OUTPUT_SIZE', 'source/output grew during verification')
        if source_digest.hexdigest() != document['source_sha256']:
            raise model.ScriptError('SOURCE_CHANGED', 'source changed during output verification')
        rules = {row['resource']: row for row in schema['profile']['rules']}
        original = {row['id']: row for row in document['records']}
        final_records = []
        for record in schema['format']['records']:
            descriptor = model._record_spec(record, rules)
            output.seek(descriptor['offset'])
            row = model.parse_slot(output.read(descriptor['capacity']), descriptor, schema['format'])
            if row['read_only_reasons']:
                raise model.ScriptError('INVALID_OUTPUT_SCRIPT', 'written script no longer parses')
            old_controls = [item['raw_hex'] for item in original[row['id']]['tokens'] if item['kind'] == 'control']
            new_controls = [item['raw_hex'] for item in row['tokens'] if item['kind'] == 'control']
            if old_controls != new_controls:
                raise model.ScriptError('CONTROL_CHANGED', 'control bytes or their order changed')
            final_records.append(row)
        pointer_bytes = {}
        for pointer in schema['format']['pointers']:
            rule = rules[pointer['rule']]
            output.seek(rule['offset'])
            pointer_bytes[pointer['rule']] = output.read(rule['length'])
        model._pointers(schema, pointer_bytes)
    return output_digest.hexdigest(), final_records


def _rehash_source(stream, size):
    return model._hash_stream(stream, size)


def _hash_temporary(path, size):
    with path.open('rb', buffering=0) as stream:
        return model._hash_stream(stream, size)


def _final_result(result):
    code = 'REPORT_LIMIT'
    try:
        return model._bounded_result(result)
    except KeyboardInterrupt:
        code = 'CANCELLED'
        result.update(cancelled=True, error_code=code, error='Cancelled during final report checking',
                      phase='reporting')
    except model.ScriptError as exc:
        if exc.code != 'REPORT_LIMIT':
            raise
    # Cleanup diagnostics arrive after the publication budget check. Preserve
    # outcome/identity/recovery facts while dropping only the verbose plan data.
    for key in ('records', 'final_records', 'hunks', 'text_deltas', 'normalized_changes', 'pointers'):
        result.pop(key, None)
    reason = 'exceeds 8 MiB' if code == 'REPORT_LIMIT' else 'was cancelled'
    message = f'Final private report {reason}; verbose plan data omitted, publication outcome unchanged.'
    result.update(ok=False, report_status='FAIL', report_error_code=code, report_error=message)
    if 'error_code' not in result:
        result.update(error_code=code, error=message, phase='reporting')
    return model._bounded_result(result)


def apply_script(source: Path, destination: Path, schema: dict, edits: dict,
                 *, expected_plan_id: str, protected_inputs: tuple[Path, ...] = ()) -> dict:
    """Replan on held original bytes; publish once, never overwrite an artifact."""
    result = {**model._result('apply'), 'written': False, 'cancelled': False,
              'validation_status': 'NOT_RUN', 'output_verification_status': 'NOT_RUN',
              'publication_status': 'NOT_RUN', 'out_sha256': None, 'out_path': None}
    temporary = owned = descriptor = None
    phase = 'validation'
    publication_attempted = False
    try:
        normalized = validate_schema(schema)['normalized_schema']
        edits = model._snapshot_edits(edits)
        if type(expected_plan_id) is not str or re.fullmatch(r'[0-9a-f]{64}', expected_plan_id) is None:
            raise model.ScriptError('APPROVAL_REQUIRED', 'expected_plan_id must be a full lowercase SHA-256')
        source, destination = Path(source).absolute(), Path(destination).absolute()
        check_output_paths(source, [destination])
        for path in protected_inputs:
            check_output_paths(Path(path), [destination])
        model._no_links(destination)
        if not destination.parent.is_dir():
            raise model.ScriptError('OUTPUT_PARENT', 'destination parent must already be an ordinary directory')
        parent_info = destination.parent.stat()
        initial = model._source_info(source)
        with source.open('rb', buffering=0) as original:
            model._assert_source(source, original, initial)
            document = model.inspect_stream(original, normalized)
            result.update({key: document[key] for key in ('source_sha256', 'schema_sha256', 'source_size')})
            plan = model.compile_changes(document, normalized, edits)
            model._assert_source(source, original, initial)
            if plan['plan_id'] != expected_plan_id:
                raise model.ScriptError('STALE_APPROVAL', 'recomputed plan differs from the reviewed plan ID')
            result.update(plan)
            result.update(operation='apply', ok=False, status='VALIDATED', validation_status='PASS')
            phase = 'construction'
            descriptor, name = tempfile.mkstemp(prefix='.romancer-script-', suffix='.tmp', dir=destination.parent)
            temporary = Path(name)
            owned = os.fstat(descriptor)
            stream = os.fdopen(descriptor, 'wb')
            descriptor = None
            with closing(stream):
                copied = _copy_output(original, stream, initial.st_size, plan['hunks'])
                stream.flush()
                os.fsync(stream.fileno())
                output_info = os.fstat(stream.fileno())
            if copied != document['source_sha256']:
                raise model.ScriptError('SOURCE_CHANGED', 'copied source no longer matches the approved revision')
            model._assert_source(source, original, initial)
            phase = 'verification'
            _check_temporary(temporary, output_info)
            output_hash, final_records = _verify_output(original, temporary, initial.st_size,
                                                         plan['hunks'], normalized, document)
            _check_temporary(temporary, output_info)
            final_document = {'parser_version': 1, 'schema_sha256': plan['schema_sha256'],
                              'source_sha256': output_hash, 'source_size': initial.st_size,
                              'parent_document_id': plan['document_id'], 'plan_id': plan['plan_id'],
                              'provenance': 'verified_derived_output'}
            final_document['document_id'] = model._digest({key: final_document[key] for key in
                ('parser_version', 'schema_sha256', 'source_sha256', 'source_size')})
            result.update(output_verification_status='PASS', out_sha256=output_hash,
                          final_records=final_records, final_document=final_document)
            # Reserve space for bounded failure/cleanup diagnostics after commit.
            published_result = {**result, 'ok': True, 'written': True, 'status': 'PUBLISHED',
                                'publication_status': 'PUBLISHED', 'out_path': str(destination)}
            if model._report_size(published_result) > model.MAX_REPORT - 8192:
                raise model.ScriptError('REPORT_LIMIT', 'private result exceeds its publication budget')
            phase = 'validation'
            if _rehash_source(original, initial.st_size) != document['source_sha256']:
                raise model.ScriptError('SOURCE_CHANGED', 'source changed after verification')
            model._assert_source(source, original, initial)
            phase = 'verification'
            _check_temporary(temporary, output_info)
            if _hash_temporary(temporary, initial.st_size) != output_hash:
                raise model.ScriptError('OUTPUT_CHANGED', 'temporary bytes changed after verification')
            _check_temporary(temporary, output_info)
            phase = 'validation'
            model._assert_source(source, original, initial)
            model._no_links(destination)
            if not os.path.samestat(destination.parent.stat(), parent_info):
                raise model.ScriptError('OUTPUT_PARENT_CHANGED', 'destination directory was replaced')
            phase = 'publication'
            publication_attempted = True
            os.link(temporary, destination)
            result.update(ok=True, written=True, status='PUBLISHED', publication_status='PUBLISHED',
                          out_path=str(destination))
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        failure = model._failure('apply', exc, phase=phase)
        for key in ('source_sha256', 'schema_sha256', 'source_size'):
            if failure[key] is not None:
                result[key] = failure[key]
        for key in ('ok', 'status', 'cancelled', 'phase', 'error_code', 'error'):
            result[key] = failure[key]
        failed_status = 'CANCELLED' if result['cancelled'] else 'FAIL'
        if phase == 'validation':
            result['validation_status'] = failed_status
        elif phase == 'verification':
            result.update(output_verification_status=failed_status, out_sha256=None)
        if publication_attempted:
            try:
                committed = _owns(destination, owned)
            except OSError as reconcile_error:
                result.update(written=None, publication_status='UNKNOWN', status='UNKNOWN')
                result['warnings'].append(f'Publication outcome requires explicit recovery: {reconcile_error}'[:2048])
            else:
                result.update(written=committed,
                              publication_status='PUBLISHED' if committed else 'FAILED',
                              status='PUBLISHED' if committed else failure['status'],
                              out_path=str(destination) if committed else None)
                if committed:
                    result['warnings'].append('Verified output was committed before the error; it remains published.')
        else:
            result['publication_status'] = 'CANCELLED' if result['cancelled'] else 'NOT_PUBLISHED'
        if result['error_code'] == 'REPORT_LIMIT':
            for key in ('records', 'final_records', 'hunks', 'text_deltas', 'normalized_changes', 'pointers'):
                result.pop(key, None)
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as exc:
                result['warnings'].append(f'Raw descriptor cleanup failed: {exc}'[:2048])
            except KeyboardInterrupt:
                result.update(ok=False, cancelled=True, error_code='CANCELLED',
                              error='Cancelled during raw descriptor cleanup', phase='cleanup')
        if temporary is not None:
            for attempt in range(2):
                try:
                    if _owns(temporary, owned):
                        temporary.unlink()
                    elif os.path.lexists(temporary):
                        result['warnings'].append('Unowned temporary path left untouched.')
                    break
                except KeyboardInterrupt:
                    result.update(ok=False, cancelled=True, error_code='CANCELLED',
                                  error='Cancelled during temporary cleanup', phase='cleanup')
                except OSError as exc:
                    result['warnings'].append(f'Owned temporary cleanup failed: {exc}'[:2048])
                    result['temporary_path'] = str(temporary)
                    break
            else:
                result['warnings'].append('Temporary cleanup interrupted twice; explicit cleanup may be needed.')
                result['temporary_path'] = str(temporary)
    return _final_result(result)
