#!/usr/bin/env python3
from romancer.cheat_archive_v21 import build_cheat_archive
import argparse
import json

p = argparse.ArgumentParser(description="ROMancer v21 cheat archive builder wrapper")
p.add_argument("--out", default="MASTER_GAME_CHEAT_CODES.txt")
p.add_argument("--libretro-dir")
p.add_argument("--extra-dir", action="append", default=[])
p.add_argument("--clone-libretro", action="store_true")
p.add_argument("--workdir", default="sources")
p.add_argument("--source-last-checked", default="local run")
args = p.parse_args()
res = build_cheat_archive(
    out=args.out,
    libretro_dir=args.libretro_dir,
    extra_dirs=args.extra_dir,
    clone_libretro=args.clone_libretro,
    workdir=args.workdir,
    source_last_checked=args.source_last_checked,
)
print(json.dumps(res, indent=2, sort_keys=True))
