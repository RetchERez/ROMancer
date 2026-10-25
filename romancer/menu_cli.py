"""Declared menu inspection, preview and separately scoped captured pixels."""
from pathlib import Path
import sys

from . import ROMANCER_VERSION
from .script_cli import encode_result
from .script_schema import load_script_json, MAX_SCHEMA_JSON_BYTES

COMMANDS = {'menu-inspect', 'menu-preview', 'menu-compare'}
MAX_DESCRIPTOR_BYTES = 1024 * 1024


def register(subparsers):
    for command in sorted(COMMANDS):
        parser = subparsers.add_parser(command, help='Inspect declared menus; separate preview from captured pixels.')
        if command == 'menu-compare':
            parser.add_argument('project', type=Path)
        parser.add_argument('script_schema', type=Path)
        parser.add_argument('source', type=Path)
        parser.add_argument('menu_profile', type=Path)
        if command != 'menu-inspect':
            parser.add_argument('cases', type=Path)
            parser.add_argument('font_schema', type=Path)
            parser.add_argument('font', type=Path)
        if command == 'menu-compare':
            parser.add_argument('request', type=Path)
        parser.add_argument('--json', action='store_true')


def dispatch(args):
    if args.cmd not in COMMANDS:
        return None
    result = {'schema_version': 1, 'tool_version': ROMANCER_VERSION, 'scope': 'menu_displays',
              'operation': args.cmd, 'ok': False, 'written': False, 'status': 'BLOCKED',
              'preview_status': 'NOT_RUN', 'comparison_status': 'NOT_RUN',
              'transaction_status': 'NOT_RUN', 'actual_transaction_verified': False,
              'native_render_verified': False, 'warnings': []}
    phase = 'script_schema_load'
    try:
        script_schema = load_script_json(args.script_schema, max_bytes=MAX_SCHEMA_JSON_BYTES)
        phase = 'menu_profile_load'
        profile = load_script_json(args.menu_profile, max_bytes=MAX_DESCRIPTOR_BYTES)
        if args.cmd == 'menu-inspect':
            from .menu import inspect_menu
            phase = 'menu_inspection'
            result = inspect_menu(args.source, script_schema, profile)
        else:
            phase = 'menu_cases_load'
            cases = load_script_json(args.cases, max_bytes=MAX_DESCRIPTOR_BYTES)
            phase = 'font_schema_load'
            font_schema = load_script_json(args.font_schema, max_bytes=MAX_DESCRIPTOR_BYTES)
            if args.cmd == 'menu-preview':
                from .menu import preview_menu
                phase = 'menu_preview'
                result = preview_menu(args.source, script_schema, profile, cases, font_schema, args.font)
            else:
                from .menu_compare import compare_menu_captures
                phase = 'comparison_request_load'
                request = load_script_json(args.request, max_bytes=MAX_DESCRIPTOR_BYTES)
                phase = 'menu_comparison'
                result = compare_menu_captures(args.project, args.source, script_schema, profile,
                                               cases, font_schema, args.font, request)
        phase = 'response_encoding'
        encode_result(result)
        return result
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        cancelled = (isinstance(exc, KeyboardInterrupt) or result.get('cancelled') is True
                     or result.get('status') == 'CANCELLED')
        failure = {key: result[key] for key in ('schema_version', 'tool_version', 'scope',
                   'operation', 'source_sha256', 'menu_document_id', 'preview_id',
                   'font_schema_sha256', 'metrics_id') if key in result}
        failure.update(ok=False, written=False, status='CANCELLED' if cancelled else 'BLOCKED',
                       cancelled=cancelled, preview_status='BLOCKED', comparison_status='NOT_RUN',
                       transaction_status='NOT_RUN', actual_transaction_verified=False,
                       native_render_verified=False, warnings=[],
                       error={'phase': phase,
                              'code': 'CANCELLED' if isinstance(exc, KeyboardInterrupt)
                              else getattr(exc, 'code', type(exc).__name__),
                              'message': 'Operation cancelled' if isinstance(exc, KeyboardInterrupt)
                              else str(exc)[:2048]})
        return failure


def emit_result(result, json_mode):
    if json_mode:
        encoded = encode_result(result)
    else:
        lines = [f"Menu operation: {result.get('status', 'BLOCKED')}",
                 f"Declared preview: {result.get('preview_status', 'NOT_RUN')}",
                 f"Captured pixels: {result.get('comparison_status', 'NOT_RUN')}",
                 f"Actual transaction: {result.get('transaction_status', 'NOT_RUN')}"]
        if result.get('error'):
            error = result['error']
            if isinstance(error, dict):
                lines.append(f"{error.get('code', 'ERROR')}: {error.get('message', '')}")
        lines.append('Declared geometry and pixel comparisons do not verify game mechanics.')
        encoded = ('\n'.join(lines) + '\n').encode('utf-8')
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
