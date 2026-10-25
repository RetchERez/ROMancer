"""CLI access to content-bound history; identity checks are not playtests."""
import json
import math
from pathlib import Path
import sqlite3

from . import ROMANCER_VERSION


def add_commands(subparsers):
    for command, help_text in (
        ('history-init', 'Create private history and preserve legacy metadata; stop legacy writers first.'),
        ('build-register', 'Record artifact hashes and explicit build configuration.'),
        ('build-check', 'Measure whether registered artifact identities still match.'),
        ('build-status', 'Evaluate matching measured identity evidence; not gameplay approval.'),
    ):
        parser = subparsers.add_parser(command, help=help_text)
        parser.add_argument('project', type=Path)
        if command == 'build-register':
            parser.add_argument('config', type=Path)
        if command in {'build-check', 'build-status'}:
            parser.add_argument('build_id')
        if command == 'build-status':
            parser.add_argument('--evidence', action='append', default=[], metavar='ID')
        parser.add_argument('--json', action='store_true')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f'nonfinite JSON value: {value}')


def _float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f'nonfinite JSON number: {value}')
    return parsed


def load_config(path):
    with path.open('rb') as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('build config exceeds 8 MiB')
    result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                        parse_constant=_constant, parse_float=_float)
    if not isinstance(result, dict):
        raise ValueError('build config must be an object')
    return result


def dispatch(args):
    if args.cmd not in {'history-init', 'build-register', 'build-check', 'build-status'}:
        return None
    try:
        # Decode untrusted configuration before opening the private store.
        config = load_config(args.config) if args.cmd == 'build-register' else None
        from .history import init_history, register_build, check_build, evaluate_build
        if args.cmd == 'history-init':
            result = init_history(args.project)
        elif args.cmd == 'build-register':
            result = register_build(args.project, config, args.config.resolve().parent)
        elif args.cmd == 'build-check':
            result = check_build(args.project, args.build_id)
        else:
            result = evaluate_build(args.project, args.build_id, args.evidence)
    except (ValueError, OSError, sqlite3.Error, RecursionError) as exc:
        result = {'ok': False, 'status': 'BLOCKED', 'error': str(exc),
                  'error_code': type(exc).__name__, 'scope': 'artifact_identity'}
    return {'schema_version': 1, 'tool': 'ROMancer', 'version': ROMANCER_VERSION,
            'operation': args.cmd, **result}
