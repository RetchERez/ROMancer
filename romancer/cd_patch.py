"""Non-destructive fixed-size payload edits for validated Mode 1 tracks."""
import hashlib
import os
from pathlib import Path
import re
import tempfile

from .cdrom import PAYLOAD_SIZE, SECTOR_SIZE, payload_spans, repair_mode1, validate_mode1

MAX_REPLACEMENT = 16 * 1024 * 1024


def _hash_file(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _identity(stat):
    # Windows path/handle ctime can differ on a just-created unchanged file.
    # Content is independently rehashed; do not compare that ambiguous field.
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _owns_path(path, owned_stat):
    try:
        current = path.lstat()
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == (owned_stat.st_dev, owned_stat.st_ino)


def check_output_paths(source: Path, outputs: list[Path]) -> None:
    # Check spelling before resolve() can normalize aliases. In particular, an
    # exclusive report write to source.bin:report still modifies the source's ADS.
    if os.name == 'nt':
        for path in outputs:
            if (os.path.isreserved(path)
                    or str(path).replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\'))):
                raise ValueError(f'Windows reserved or ambiguous output path; choose a regular filename: {path}')
    resolved = [source.resolve()] + [path.resolve() for path in outputs]
    if len(set(resolved)) != len(resolved):
        raise ValueError('source, destination and report paths must be distinct')
    for index, path in enumerate(resolved):
        for other in resolved[index + 1:]:
            if path in other.parents or other in path.parents:
                raise ValueError('source, destination and reports cannot be parents of one another')
    for path in outputs:
        if os.path.lexists(path):
            raise ValueError(f'output already exists; choose a new path: {path}')
        for parent in path.resolve().parents:
            if os.path.lexists(parent) and not parent.is_dir():
                raise ValueError(f'output parent is not a directory: {parent}')


def _scan_source(stream, spans):
    stream.seek(0)
    digest = hashlib.sha256()
    originals = []
    by_sector = {span['sector']: span for span in spans}
    count = 0
    while raw := stream.read(SECTOR_SIZE):
        try:
            validate_mode1(raw)
        except ValueError as exc:
            raise ValueError(f'source integrity failed at sector {count}: {exc}') from exc
        digest.update(raw)
        if count in by_sector:
            span = by_sector[count]
            start = 16 + span['payload_offset']
            originals.append(raw[start:start + span['length']])
        count += 1
    if count == 0 or spans[-1]['sector'] >= count:
        raise ValueError('payload exceeds the track bounds')
    return digest.hexdigest(), b''.join(originals), count


def _edited_sector(raw, span, replacement):
    if span is None:
        return raw
    edited = bytearray(raw)
    start = 16 + span['payload_offset']
    index = span['data_offset']
    edited[start:start + span['length']] = replacement[index:index + span['length']]
    return repair_mode1(edited)


def _write_output(source, output, spans, replacement):
    source.seek(0)
    count = 0
    digest = hashlib.sha256()
    by_sector = {span['sector']: span for span in spans}
    while raw := source.read(SECTOR_SIZE):
        digest.update(raw)
        output.write(_edited_sector(raw, by_sector.get(count), replacement))
        count += 1
    output.flush()
    os.fsync(output.fileno())
    return digest.hexdigest()


def _verify_output(source, output_path, spans, replacement):
    source.seek(0)
    digest = hashlib.sha256()
    by_sector = {span['sector']: span for span in spans}
    count = 0
    with output_path.open('rb') as output:
        while before := source.read(SECTOR_SIZE):
            after = output.read(SECTOR_SIZE)
            if len(after) != SECTOR_SIZE:
                raise ValueError('output size changed')
            span = by_sector.get(count)
            if span is None:
                if before != after:
                    raise ValueError(f'untouched sector {count} changed')
            else:
                validate_mode1(after)
                start = 16 + span['payload_offset']
                end = start + span['length']
                index = span['data_offset']
                if (after[:start] != before[:start] or after[end:2064] != before[end:2064]
                        or after[start:end] != replacement[index:index + span['length']]):
                    raise ValueError(f'output payload or header mismatch at sector {count}')
            digest.update(after)
            count += 1
        if output.read(1):
            raise ValueError('output is longer than source')
    return digest.hexdigest()


def patch_mode1(source: Path, destination: Path, extent: int, offset: int,
                replacement: bytes, *, expected_sha256: str = '',
                expected_before: bytes | None = None, dry_run: bool = False,
                resource_size: int | None = None) -> dict:
    """Validate source/preconditions, verify output, then atomically publish.

    Cancellation before commit writes no destination. After commit it reports
    PUBLISHED with written=True and cancelled=True; the destination is never
    removed. Identity/hash rechecks detect ordinary concurrent changes, not an
    adversary racing the final check and filesystem operation.
    """
    source, destination = Path(source), Path(destination)
    result = {'schema_version': 1, 'tool': 'ROMancer', 'feature': 'safe Mode1/2352 patch',
              'ok': False, 'written': False, 'dry_run': dry_run,
              'source': str(source), 'out_bin': '', 'source_sha256': None,
              'expected_source_sha256': expected_sha256, 'out_sha256': None,
              'layout': 'MODE1/2352', 'resource_bounds_verified': resource_size is not None,
              'warnings': [] if resource_size is not None else
                  ['Expert payload edit: ISO file ownership/bounds have not been verified.'],
              'validation_status': 'NOT_RUN', 'output_verification_status': 'NOT_RUN',
              'output_integrity': 'NOT_RUN', 'publication_status': 'NOT_RUN',
              'cancelled': False}
    temporary = None
    owned_stat = None
    phase = 'validation'
    publication_attempted = False
    try:
        check_output_paths(source, [destination])
        if not source.is_file():
            raise ValueError('source must be an existing regular file')
        if type(replacement) is not bytes or not 0 < len(replacement) <= MAX_REPLACEMENT:
            raise ValueError('replacement must contain 1 to 16777216 bytes')
        if expected_before is not None and type(expected_before) is not bytes:
            raise ValueError('expected original payload must be bytes')
        if not isinstance(expected_sha256, str):
            raise ValueError('expected SHA-256 must be a hexadecimal string')
        if expected_sha256 and re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256) is None:
            raise ValueError('expected SHA-256 must contain exactly 64 hexadecimal digits')
        if not dry_run and (not expected_sha256 or expected_before is None):
            raise ValueError('writing requires expected SHA-256 and the full expected original payload')
        if expected_before is not None and len(expected_before) != len(replacement):
            raise ValueError('expected original payload must match the complete replacement length')
        spans = payload_spans(extent, offset, len(replacement))
        if resource_size is not None:
            if type(resource_size) is not int or resource_size < 0 or offset + len(replacement) > resource_size:
                raise ValueError('payload exceeds resource bounds or resource size is invalid')
        result.update({'extent': extent, 'file_offset': offset, 'length': len(replacement),
                       'spans': spans, 'touched_sectors': [span['sector'] for span in spans],
                       'raw_track_offset': spans[0]['raw_offset'],
                       'raw_track_offset_hex': hex(spans[0]['raw_offset']),
                       'after_hex': replacement.hex(), 'resource_size': resource_size})
        with source.open('rb') as original:
            initial_stat = os.fstat(original.fileno())
            if initial_stat.st_size == 0 or initial_stat.st_size % SECTOR_SIZE:
                raise ValueError('source is not an aligned nonempty Mode1/2352 track')
            if spans[-1]['sector'] >= initial_stat.st_size // SECTOR_SIZE:
                raise ValueError('payload exceeds track bounds')
            observed_hash, before, count = _scan_source(original, spans)
            result.update({'source_sha256': observed_hash, 'before_hex': before.hex(),
                           'before_expected_hex': None if expected_before is None else expected_before.hex(),
                           'sector_count': count, 'source_integrity': 'PASS'})
            if expected_sha256 and observed_hash.lower() != expected_sha256.lower():
                raise ValueError('source SHA-256 mismatch; use the exact original build')
            if expected_before is not None and before != expected_before:
                raise ValueError('expected original payload mismatch')
            if _identity(os.fstat(original.fileno())) != _identity(initial_stat):
                raise ValueError('source changed during inspection')
            result.update({'before_ok': True, 'validation_status': 'PASS'})
            if dry_run:
                if (_identity(source.stat()) != _identity(initial_stat)
                        or _hash_file(source) != observed_hash):
                    raise ValueError('source changed during dry-run')
                result.update({'ok': True, 'publication_status': 'NOT_APPLICABLE'})
                return result
            phase = 'construction'
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.romancer-', suffix='.tmp', dir=destination.parent)
            temporary = Path(name)
            with os.fdopen(fd, 'wb') as output:
                owned_stat = os.fstat(output.fileno())
                copied_hash = _write_output(original, output, spans, replacement)
                output_stat = os.fstat(output.fileno())
            phase = 'validation'
            if copied_hash != observed_hash:
                raise ValueError('source changed during output construction')
            phase = 'verification'
            if _identity(temporary.lstat()) != _identity(output_stat):
                raise ValueError('temporary output identity changed before verification')
            output_hash = _verify_output(original, temporary, spans, replacement)
            if _identity(temporary.lstat()) != _identity(output_stat):
                raise ValueError('temporary output changed during verification')
            result.update({'output_verification_status': 'PASS', 'output_integrity': 'PASS',
                           'out_sha256': output_hash})
            # Unchanged output sectors are byte-identical to the validated source;
            # changed sectors are validated individually and checked for exact scope.
            phase = 'validation'
            if (_identity(source.stat()) != _identity(initial_stat)
                    or _identity(os.fstat(original.fileno())) != _identity(initial_stat)
                    or _hash_file(source) != observed_hash):
                raise ValueError('source changed after planning; output was not published')
            phase = 'verification'
            # Bind the name and bytes again after the potentially long source hash.
            if (_identity(temporary.lstat()) != _identity(output_stat)
                    or _hash_file(temporary) != output_hash
                    or _identity(temporary.lstat()) != _identity(output_stat)):
                raise ValueError('temporary output changed after verification; output was not published')
            phase = 'validation'
            if (_identity(source.stat()) != _identity(initial_stat)
                    or _identity(os.fstat(original.fileno())) != _identity(initial_stat)):
                raise ValueError('source changed during final output hash; output was not published')
            phase = 'publication'
            publication_attempted = True
            os.link(temporary, destination)
            result.update({'ok': True, 'written': True, 'out_bin': str(destination),
                           'out_sha256': output_hash, 'output_integrity': 'PASS',
                           'publication_status': 'PUBLISHED'})
        return result
    except (ValueError, OSError, KeyboardInterrupt) as exc:
        cancelled = isinstance(exc, KeyboardInterrupt)
        result.update({'ok': False, 'cancelled': cancelled,
                       'error': 'Operation cancelled' if cancelled else str(exc),
                       'error_code': 'CANCELLED' if cancelled else type(exc).__name__})
        failed_status = 'CANCELLED' if cancelled else 'FAIL'
        if phase == 'validation':
            result['validation_status'] = failed_status
        elif phase == 'verification':
            result.update({'output_verification_status': failed_status,
                           'output_integrity': failed_status, 'out_sha256': None})
        if publication_attempted:
            # A signal can arrive after link() commits but before Python records it.
            # Reconcile by file identity, never by destination existence alone.
            try:
                committed = _owns_path(destination, owned_stat)
            except OSError as reconcile_error:
                result.update({'written': None, 'publication_status': 'UNKNOWN'})
                result['warnings'].append(f'Could not determine publication outcome: {reconcile_error}')
            else:
                result.update({'written': committed,
                               'out_bin': str(destination) if committed else '',
                               'publication_status': 'PUBLISHED' if committed else
                                   ('CANCELLED' if cancelled else 'FAILED')})
                if committed and cancelled:
                    result['error'] = 'Operation cancelled after commit; verified output remains published'
        return result
    finally:
        if temporary is not None and owned_stat is not None:
            # A single cleanup interrupt must not discard an already-known commit.
            # Retry with a fresh ownership check; repeated interrupts retain a path.
            for attempt in range(2):
                try:
                    if _owns_path(temporary, owned_stat):
                        temporary.unlink(missing_ok=True)
                    elif os.path.lexists(temporary):
                        result['warnings'].append('Temporary pathname was replaced; replacement left untouched')
                    break
                except KeyboardInterrupt:
                    result.update({'ok': False, 'cancelled': True, 'error_code': 'CANCELLED',
                                   'error': 'Operation cancelled during temporary cleanup'})
                except OSError as exc:
                    result['warnings'].append(f'Could not remove owned temporary file: {exc}')
                    result['temporary_path'] = str(temporary)
                    break
            else:
                result['warnings'].append('Temporary cleanup interrupted repeatedly; inspect temporary path')
                result['temporary_path'] = str(temporary)
