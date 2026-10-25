"""Read-only console capability and revision-contract commands."""
from pathlib import Path

from . import ROMANCER_VERSION


def add_commands(subparsers):
    for name, help_text in (
        ('adapter-inventory', 'List explicit console capabilities and their limitations.'),
        ('profile-contract-check', 'Check exact revision and bytes without authorizing a write.'),
        ('profile-import-legacy', 'Read a historical profile with provenance; do not promote its claims.'),
    ):
        parser = subparsers.add_parser(name, help=help_text)
        if name != 'adapter-inventory':
            parser.add_argument('profile', type=Path)
        if name == 'profile-contract-check':
            parser.add_argument('artifact', type=Path)
        parser.add_argument('--json', action='store_true')


def dispatch(args):
    if args.cmd not in {'adapter-inventory', 'profile-contract-check', 'profile-import-legacy'}:
        return None
    try:
        from .contracts import adapter_inventory, check_contract, import_legacy_profile, load_contract
        profile = load_contract(args.profile) if args.cmd == 'profile-contract-check' else None
        if args.cmd == 'adapter-inventory':
            result = adapter_inventory()
        elif args.cmd == 'profile-contract-check':
            result = check_contract(profile, args.artifact)
        else:
            result = import_legacy_profile(args.profile)
    except (ValueError, OSError, RecursionError) as exc:
        result = {'ok': False, 'status': 'BLOCKED', 'error': str(exc),
                  'error_code': type(exc).__name__, 'scope': 'profile_preconditions'}
    return {'schema_version': 2, 'tool': 'ROMancer', 'version': ROMANCER_VERSION,
            'operation': args.cmd, **result, 'write_authorized': False}
