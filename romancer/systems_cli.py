"""Read-only system foundation commands over the same bounded services as the UI."""
from pathlib import Path

COMMANDS={'systems-list','systems-identify','systems-nes-chr'}


def add_commands(subparsers):
    for name in sorted(COMMANDS):
        parser=subparsers.add_parser(name)
        parser.add_argument('--json',action='store_true')
        if name!='systems-list':parser.add_argument('source',type=Path)
        if name=='systems-nes-chr':
            parser.add_argument('--expect-sha',required=True)
            parser.add_argument('--first-tile',type=int,default=0);parser.add_argument('--count',type=int,default=16)


def dispatch(args):
    if args.cmd not in COMMANDS:return None
    from .system_registry import system_inventory
    from .system_identify import identify_system
    from .system_resources import describe_nes_chr
    try:
        if args.cmd=='systems-list':return system_inventory()
        if args.cmd=='systems-identify':return identify_system(args.source)
        return describe_nes_chr(args.source,expected_sha256=args.expect_sha,first_tile=args.first_tile,count=args.count)
    except (ValueError,OSError,KeyboardInterrupt) as exc:
        return {'ok':False,'status':'CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED','error':str(exc)[:1024],
            'write_authorized':False,'runtime_verified':False}
