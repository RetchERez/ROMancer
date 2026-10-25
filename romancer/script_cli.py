"""Explicit fixed-slot script inspection, review and publication commands."""
import json
from pathlib import Path
import sys

from . import ROMANCER_VERSION
from .script_schema import (load_script_json, MAX_SCHEMA_JSON_BYTES,
                            MAX_EDITS_JSON_BYTES, MAX_OUTPUT_JSON_BYTES)

COMMANDS = {'script-inspect', 'script-plan', 'script-apply'}


def add_commands(subparsers):
    for command in sorted(COMMANDS):
        parser = subparsers.add_parser(command, help='Revision-bound fixed-slot script editing.')
        parser.add_argument('schema', type=Path)
        parser.add_argument('source', type=Path)
        if command != 'script-inspect':
            parser.add_argument('edits', type=Path)
        if command == 'script-apply':
            parser.add_argument('--expected-plan', required=True)
            parser.add_argument('--out', required=True, type=Path)
        parser.add_argument('--json', action='store_true')


def encode_result(result, *, limit=MAX_OUTPUT_JSON_BYTES):
    encoded = (json.dumps(result, ensure_ascii=True, allow_nan=False,
                          sort_keys=True, indent=2) + '\n').encode('utf-8')
    if len(encoded) > limit:
        raise ValueError('script response exceeds 8 MiB')
    return encoded


def emit_result(result):
    sys.stdout.buffer.write(encode_result(result))
    sys.stdout.buffer.flush()


def dispatch(args):
    if args.cmd not in COMMANDS:
        return None
    result = {'schema_version': 1, 'tool_version': ROMANCER_VERSION,
              'scope': 'structured_script', 'operation': args.cmd,
              'ok': False, 'written': False, 'status': 'BLOCKED',
              'write_supported': False, 'warnings': []}
    phase = 'schema_load'
    try:
        schema = load_script_json(args.schema, max_bytes=MAX_SCHEMA_JSON_BYTES)
        if args.cmd == 'script-inspect':
            from .script import inspect_script
            phase = 'inspection'
            result = inspect_script(args.source, schema)
        else:
            phase = 'edits_load'
            edits = load_script_json(args.edits, max_bytes=MAX_EDITS_JSON_BYTES)
            if args.cmd == 'script-plan':
                from .script import plan_script
                phase = 'plan'
                result = plan_script(args.source, schema, edits)
            else:
                from .script_patch import apply_script
                phase = 'apply'
                result = apply_script(args.source, args.out, schema, edits,
                                      expected_plan_id=args.expected_plan,
                                      protected_inputs=(args.schema, args.edits))
        phase = 'response_encoding'
        encode_result(result)
        return result
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        cancelled = result.get('cancelled') is True or isinstance(exc, KeyboardInterrupt)
        # Reporting failure must not pretend a successfully published file rolled back.
        retained = ('schema_version', 'tool_version', 'scope', 'operation', 'written',
                    'publication_status', 'validation_status', 'output_verification_status',
                    'out_path', 'out_sha256', 'plan_id', 'source_sha256', 'schema_sha256')
        failure = {key: result[key] for key in retained if key in result}
        failure.update(ok=False, cancelled=cancelled, phase=phase,
                       write_supported=result.get('write_supported') is True,
                       warnings=[item[:256] for item in result.get('warnings', [])[:16]
                                 if type(item) is str],
                       status=result.get('publication_status') if result.get('written') is not False
                       and 'written' in result else ('CANCELLED' if cancelled else 'BLOCKED'),
                       error_code='CANCELLED' if isinstance(exc, KeyboardInterrupt)
                       else getattr(exc, 'code', type(exc).__name__),
                       error=('Operation cancelled' if isinstance(exc, KeyboardInterrupt) else str(exc))[:2048])
        return failure
