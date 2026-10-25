from __future__ import annotations

from .cheat_archive_v21 import (
    V21_VERSION,
    audit_source_dir,
    build_cheat_archive,
    cheat_schema,
    cheat_sources,
    v21_self_test,
)

VERSION = V21_VERSION


def add_v21_parsers(sub):
    s = sub.add_parser('cheat-schema', help='[v21] Show the normalized cheat-code record schema')
    s.add_argument('--out')
    s.add_argument('--json', action='store_true')

    s = sub.add_parser('cheat-sources', help='[v21] Show accepted cheat-code source families and safety policy')
    s.add_argument('--out')
    s.add_argument('--json', action='store_true')

    s = sub.add_parser('cheat-audit-source', help='[v21] Audit a local cheat source folder for accepted files and forbidden payload candidates')
    s.add_argument('root')
    s.add_argument('--out')
    s.add_argument('--json', action='store_true')

    s = sub.add_parser('cheat-build-archive', help='[v21] Build a source-grounded master cheat-code TXT, TSV, JSONL, and report')
    s.add_argument('--out', default='MASTER_GAME_CHEAT_CODES.txt')
    s.add_argument('--libretro-dir')
    s.add_argument('--extra-dir', action='append', default=[])
    s.add_argument('--clone-libretro', action='store_true')
    s.add_argument('--workdir', default='sources')
    s.add_argument('--source-last-checked', default='local run')
    s.add_argument('--json', action='store_true')

    s = sub.add_parser('v21-self-test', help='[v21] Test cheat archive parsing, schema, audit, and build output')
    s.add_argument('--out')
    s.add_argument('--json', action='store_true')


def dispatch_v21(args):
    c = getattr(args, 'cmd', '')
    if c == 'cheat-schema':
        return True, cheat_schema(args.out)
    if c == 'cheat-sources':
        return True, cheat_sources(args.out)
    if c == 'cheat-audit-source':
        return True, audit_source_dir(args.root, args.out)
    if c == 'cheat-build-archive':
        return True, build_cheat_archive(
            out=args.out,
            libretro_dir=args.libretro_dir,
            extra_dirs=args.extra_dir,
            clone_libretro=args.clone_libretro,
            workdir=args.workdir,
            source_last_checked=args.source_last_checked,
        )
    if c == 'v21-self-test':
        return True, v21_self_test(args.out)
    return False, None
