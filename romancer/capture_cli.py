"""CLI for private captures and attributed annotations, not gameplay certification."""
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

from . import ROMANCER_VERSION
from .history import strict_json_loads

JSON_LIMIT = 1024 * 1024
COMMANDS = {'capture-init', 'capture-import', 'capture-annotate',
            'capture-run', 'capture-search', 'capture-show'}


def add_commands(subparsers):
    for command in sorted(COMMANDS):
        parser = subparsers.add_parser(command, help='Private capture storage, retrieval and annotations.')
        parser.add_argument('project', type=Path)
        if command == 'capture-import':
            parser.add_argument('image', type=Path)
            parser.add_argument('manifest', type=Path)
        elif command == 'capture-run':
            parser.add_argument('build_id')
            parser.add_argument('config', type=Path)
        elif command == 'capture-annotate':
            parser.add_argument('capture_id')
            parser.add_argument('annotations', type=Path)
            parser.add_argument('--source', type=Path, help='Explicit source file for imported annotations.')
        elif command == 'capture-show':
            parser.add_argument('capture_id')
            parser.add_argument('--image-out', type=Path)
            parser.add_argument('--after-annotation-id')
            parser.add_argument('--limit', type=int, default=16)
        elif command == 'capture-search':
            for name in ('text', 'scene', 'build-id', 'resource-id', 'origin', 'run-mode', 'after-id'):
                parser.add_argument('--' + name)
            parser.add_argument('--include-superseded', action='store_true')
            parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--json', action='store_true')


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def load_document(path, expected_type=dict):
    if os.name == 'nt' and (os.path.isreserved(path)
                           or str(path).replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\'))):
        raise ValueError('Windows reserved or ambiguous capture input path')
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError('linked capture input paths are not supported')
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('capture input must be a regular file')
    raw = bytearray()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if _identity(opened) != _identity(before):
            raise ValueError('capture input changed before reading')
        while chunk := stream.read(min(65536, JSON_LIMIT + 1 - len(raw))):
            raw.extend(chunk)
            if len(raw) > JSON_LIMIT:
                raise ValueError('capture JSON input exceeds 1 MiB')
        if (_identity(opened) != _identity(os.fstat(stream.fileno()))
                or _identity(opened) != _identity(path.stat())):
            raise ValueError('capture input changed while reading')
    result = strict_json_loads(bytes(raw), max_bytes=JSON_LIMIT)
    if type(result) is not expected_type:
        raise ValueError('capture JSON has an invalid root type')
    pending = [(result, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 32 or nodes > 10000:
            raise ValueError('capture JSON exceeds depth or node budget')
        if type(value) is dict:
            pending.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            pending.extend((item, depth + 1) for item in value)
    return result


def encode_result(result, *, limit=JSON_LIMIT):
    encoded = (json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    if len(encoded) > limit:
        raise ValueError('capture response exceeds 1 MiB; request a smaller page')
    return encoded


def emit_result(result):
    sys.stdout.buffer.write(encode_result(result))
    sys.stdout.buffer.flush()


def dispatch(args):
    if args.cmd not in COMMANDS:
        return None
    scope = {'capture-init': 'capture_ingestion', 'capture-run': 'capture_ingestion',
             'capture-import': 'capture_ingestion', 'capture-annotate': 'capture_annotations',
             'capture-search': 'capture_search', 'capture-show': 'capture_integrity'}[args.cmd]
    envelope = {'schema_version': 1, 'tool': 'ROMancer', 'version': ROMANCER_VERSION,
                'operation': args.cmd, 'scope': scope}
    written = False
    committed_id = None
    try:
        if args.cmd == 'capture-run':
            config = load_document(args.config)
            from .capture_runtime import capture_run
            result = capture_run(args.project, args.build_id, config, args.config.resolve().parent)
        elif args.cmd == 'capture-import':
            manifest = load_document(args.manifest)
            from .capture_ingest import import_capture
            result = import_capture(args.project, args.image, manifest, args.manifest.resolve().parent,
                                    manifest_source=args.manifest)
        elif args.cmd == 'capture-annotate':
            entries = load_document(args.annotations, list)
            from .capture_ingest import add_annotations
            result = add_annotations(args.project, args.capture_id, entries, source_path=args.source)
        elif args.cmd == 'capture-init':
            from .capture_store import init_capture_store
            result = init_capture_store(args.project)
        elif args.cmd == 'capture-search':
            from .capture_store import search_captures
            fields = ('text', 'scene', 'build_id', 'resource_id', 'origin', 'run_mode', 'after_id')
            query = {key: getattr(args, key) for key in fields if getattr(args, key) is not None}
            query.update(limit=args.limit, include_superseded=args.include_superseded)
            result = search_captures(args.project, query)
        else:
            from .capture_store import get_capture, export_capture
            result = dict(get_capture(args.project, args.capture_id,
                                      after_annotation_id=args.after_annotation_id, limit=args.limit))
            result.pop('png_bytes', None)
            if args.image_out is not None:
                if len(str(args.image_out)) > 4096:
                    raise ValueError('export path exceeds 4096 characters')
                encode_result({**envelope, **result}, limit=JSON_LIMIT - 65536)
                result['export'] = export_capture(args.project, args.capture_id, args.image_out)
                written = result['export'].get('ok') is True
                if result['export'].get('ok') is not True:
                    result['ok'] = False
        if args.cmd in {'capture-init', 'capture-import', 'capture-annotate', 'capture-run'}:
            written = result.get('ok') is True
            committed_id = result.get('capture_id')
        result = {**envelope, **result}
        encode_result(result)
        return result
    except (ValueError, OSError, sqlite3.Error, RecursionError, ImportError) as exc:
        result = {**envelope, 'ok': False, 'status': 'BLOCKED', 'written': written,
                  'error': str(exc)[:4096], 'error_code': type(exc).__name__}
        if written and args.cmd == 'capture-show':
            result['export_path'] = str(args.image_out)
        elif written and type(committed_id) is str and len(committed_id) <= 64:
            result['capture_id'] = committed_id
        return result
