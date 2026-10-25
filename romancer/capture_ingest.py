"""Explicit PNG and annotation imports. No OCR or semantic inference is performed."""
from datetime import datetime, timezone
import io
from pathlib import Path
import struct
import uuid
import warnings
import zlib

from . import ROMANCER_VERSION
from .history import get_build
from . import capture_store as store


def _now():
    return datetime.now(timezone.utc).isoformat()


def _locate(path, base):
    value = Path(path)
    if value.drive and not value.root:
        raise ValueError('drive-relative path is ambiguous')
    return store._path(value if value.is_absolute() else Path(base) / value)


def _check_png_chunks(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('PNG input required')
    offset, size = 8, len(raw)
    view = memoryview(raw)
    while offset < size:
        if size - offset < 12:
            raise ValueError('truncated PNG chunk framing')
        length = struct.unpack_from('>I', raw, offset)[0]
        end = offset + 12 + length
        if end > size:
            raise ValueError('PNG chunk exceeds available bytes')
        kind = raw[offset+4:offset+8]
        expected = struct.unpack_from('>I', raw, end-4)[0]
        if zlib.crc32(view[offset+4:end-4]) != expected:
            raise ValueError('PNG chunk CRC mismatch')
        if kind == b'IEND':
            if length != 0 or end != size:
                raise ValueError('PNG requires an empty terminal IEND')
            return
        offset = end
    raise ValueError('PNG is missing terminal IEND')


def _decode_png(raw):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError('Pillow is required for PNG import; no image was ingested') from exc
    # Pillow's verification stops at IEND without validating its terminal CRC.
    _check_png_chunks(raw)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=['PNG']) as image:
                width, height = image.size
                store._int(width, 1, 4096)
                store._int(height, 1, 4096)
                if width*height*3 > store.MAX_RGB or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('PNG dimensions/animation exceed capture scope')
                image.verify()
            with Image.open(io.BytesIO(raw), formats=['PNG']) as image:
                image.load()
                with image.convert('RGB') as rgb:
                    data = rgb.tobytes()
        return width, height, store._sha(data)
    except (OSError, SyntaxError, Warning, Image.DecompressionBombError) as exc:
        raise ValueError('invalid/bounded PNG decode: '+str(exc)) from exc


def _context(context):
    store._fields(context, 'captured_utc game_sha256 core_sha256 run_mode state_derived source_note')
    for key in ('game_sha256', 'core_sha256'):
        if context[key] is not None:
            store._hex(context[key])
    for key in ('captured_utc', 'run_mode', 'source_note'):
        if context[key] is not None:
            store._text(context[key], 4096 if key == 'source_note' else 256)
    if context['state_derived'] is not None and type(context['state_derived']) is not bool:
        raise ValueError('state ancestry is boolean or unknown')


def _annotations(capture, entries, source):
    if type(entries) is not list or len(entries) > 64:
        raise ValueError('at most 64 annotations per batch')
    result = []
    for entry in entries:
        record = dict(schema_version=1, annotation_id=uuid.uuid4().hex,
                      capture_id=capture['capture_id'], created_utc=_now(),
                      origin='imported_annotation', entry=entry, source=source)
        store._validate_annotation(record, capture)
        result.append(record)
    return result


def import_capture(project, image, manifest, base, *, manifest_source=None):
    canonical = store._json(manifest, store.MAX_SOURCE).encode()
    manifest = store._parse(canonical, store.MAX_SOURCE)
    store._fields(manifest, 'build_id declared_context annotations')
    _context(manifest['declared_context'])
    image = _locate(image, base)
    source_path = _locate(manifest_source, base) if manifest_source is not None else None
    store._protect_sources(project, [image, *([source_path] if source_path else [])])
    if source_path:
        source_bytes = store._read_file(source_path, store.MAX_SOURCE)
        if store._json(store._parse(source_bytes, store.MAX_SOURCE), store.MAX_SOURCE).encode() != canonical:
            raise ValueError('manifest source differs from parsed manifest')
        manifest_kind = 'original_file'
    else:
        source_bytes, manifest_kind = canonical, 'canonical_api_input'
    manifest_hash = store._sha(source_bytes)
    raw = store._read_file(image, store.MAX_PNG)
    width, height, rgb_hash = _decode_png(raw)
    digest = store._sha(raw)
    build = None
    if manifest['build_id'] is not None:
        known = get_build(project, manifest['build_id'])
        build = dict(build_id=known['build_id'], identity=known['identity'], locations=known['locations'], association='imported_claim')
        claimed = manifest['declared_context']['game_sha256']
        if claimed is not None and claimed != build['identity']['output']['sha256']:
            raise ValueError('declared game does not match associated build')
    capture = dict(schema_version=1, canonical_version=1, capture_id=uuid.uuid4().hex,
                   created_utc=_now(), tool_version=ROMANCER_VERSION, origin='imported_image',
                   image=dict(blob_sha256=digest, byte_size=len(raw), width=width, height=height,
                              rgb_sha256=rgb_hash, media_type='image/png', normalization='rgb24'),
                   build=build, run=None, natural_progress_verified=False,
                   import_source=dict(path_hint=str(image), image_sha256=digest,
                                      manifest_sha256=manifest_hash, manifest_kind=manifest_kind,
                                      manifest_path_hint=str(source_path) if source_path else None,
                                      declared_context=manifest['declared_context']))
    source = dict(sha256=manifest_hash, path_hint=str(source_path)) if source_path else None
    annotations = _annotations(capture, manifest['annotations'], source)
    blobs = {digest: dict(media_type='image/png', content=raw),
             manifest_hash: dict(media_type='application/json', content=source_bytes)}
    return store._insert_capture(project, capture, blobs, annotations)


def add_annotations(project, capture_id, entries, source_path=None):
    entries = store._parse(store._json(entries, store.MAX_SOURCE), store.MAX_SOURCE)
    if type(entries) is not list or not entries:
        raise ValueError('nonempty annotation list required')
    capture = store.get_capture(project, capture_id)['record']
    blobs, source = {}, None
    if source_path is not None:
        source_path = store._path(source_path)
        store._protect_sources(project, [source_path])
        raw = store._read_file(source_path, store.MAX_SOURCE)
        digest = store._sha(raw)
        source = dict(sha256=digest, path_hint=str(source_path))
        blobs[digest] = dict(media_type='application/octet-stream', content=raw)
    records = _annotations(capture, entries, source)
    return store._insert_annotations(project, capture_id, records, blobs)
