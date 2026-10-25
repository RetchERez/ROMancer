"""Read-only font measurement and reviewed dialogue layout proposals."""
from pathlib import Path

from . import ROMANCER_VERSION
from .script_cli import encode_result, emit_result
from .script_schema import load_script_json, MAX_SCHEMA_JSON_BYTES

COMMANDS = {'font-measure', 'layout-check', 'layout-plan'}
MAX_DESCRIPTOR_BYTES = 1024 * 1024


def add_commands(subparsers):
    for command in sorted(COMMANDS):
        parser = subparsers.add_parser(command, help='Measure declared fonts and dialogue layout.')
        if command != 'font-measure':
            parser.add_argument('script_schema', type=Path)
            parser.add_argument('source', type=Path)
        parser.add_argument('font_schema', type=Path)
        parser.add_argument('font', type=Path)
        if command != 'font-measure':
            parser.add_argument('layout', type=Path)
        if command == 'layout-plan':
            parser.add_argument('request', type=Path)
        parser.add_argument('--json', action='store_true')


def dispatch(args):
    if args.cmd not in COMMANDS:
        return None
    scope = 'native_font_metrics' if args.cmd == 'font-measure' else 'dialogue_layout'
    result = {'schema_version': 1, 'tool_version': ROMANCER_VERSION, 'scope': scope,
              'operation': args.cmd, 'ok': False, 'written': False, 'status': 'BLOCKED',
              'native_render_verified': False, 'warnings': []}
    phase = 'font_schema_load'
    try:
        font_schema = load_script_json(args.font_schema, max_bytes=MAX_DESCRIPTOR_BYTES)
        if args.cmd == 'font-measure':
            from .font_metrics import measure_font
            phase = 'font_measurement'
            result = measure_font(args.font, font_schema)
        else:
            from .dialogue_layout import check_layout, plan_layout
            phase = 'script_schema_load'
            script_schema = load_script_json(args.script_schema, max_bytes=MAX_SCHEMA_JSON_BYTES)
            phase = 'layout_policy_load'
            policy = load_script_json(args.layout, max_bytes=MAX_DESCRIPTOR_BYTES)
            if args.cmd == 'layout-check':
                phase = 'layout_analysis'
                result = check_layout(args.source, script_schema, args.font, font_schema, policy)
            else:
                phase = 'layout_request_load'
                request = load_script_json(args.request, max_bytes=MAX_DESCRIPTOR_BYTES)
                phase = 'layout_proposal'
                result = plan_layout(args.source, script_schema, args.font, font_schema, policy, request)
        phase = 'response_encoding'
        encode_result(result)
        return result
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        cancelled = (isinstance(exc, KeyboardInterrupt) or result.get('cancelled') is True
                     or result.get('status') == 'CANCELLED')
        return {'schema_version': 1, 'tool_version': ROMANCER_VERSION, 'scope': scope,
                'operation': args.cmd, 'ok': False, 'written': False,
                'status': 'CANCELLED' if cancelled else 'BLOCKED', 'cancelled': cancelled,
                'native_render_verified': False, 'warnings': [],
                'error': {'phase': phase,
                          'code': 'CANCELLED' if isinstance(exc, KeyboardInterrupt)
                          else getattr(exc, 'code', type(exc).__name__),
                          'message': 'Operation cancelled' if isinstance(exc, KeyboardInterrupt)
                          else str(exc)[:2048]}}
