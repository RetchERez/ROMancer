"""Print what the trace knows about one unpacked tile of a dumped scene (see codec_survey.py dump).

    python -B trace/codec_show.py INDEX.json DUMPDIR SHA_PREFIX [--target N] [--rows N]

Shows the stretch of video memory the tile was loaded with, the candidate
stream starts, the ROM bytes there, and for each byte of video memory the
ROM offset its tag names (relative to the first candidate start; '=' rows
are bytes copied straight from the ROM, '~' computed after reading it).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))


def main():
    import codec_survey as cs
    from romancer import graphics_trace as gt
    from romancer.provenance import tag_kind, tag_offset
    ap = argparse.ArgumentParser()
    ap.add_argument('index'); ap.add_argument('dumpdir'); ap.add_argument('sha')
    ap.add_argument('--target', type=int, default=0); ap.add_argument('--rows', type=int, default=6)
    ap.add_argument('--at', type=lambda x: int(x, 0), help='ROM offset to dump instead of the anchors')
    a = ap.parse_args()
    index = json.loads(Path(a.index).read_text())
    path = next(p for p in sorted(Path(a.dumpdir).glob('*.pkl')) if p.stem.startswith(a.sha))
    rec, scene = cs.load_dump(path)
    rom, _ = cs.read_rom(index, rec['sha256'])
    skip = gt.rom_skip(rom, rec['system'])
    print(rec['system'], rec['member'].split('!')[-1], rec['counts'], 'targets', len(rec['targets']))
    t = rec['targets'][a.target]
    d = scene.snapshot.domains[t['domain']]
    cl = gt.source_cluster(scene, t['domain'], t['start'], t['length'])
    if cl is None:
        print('no cluster'); return
    lo, hi, anchors, tlo, thi = cl
    print(f"target {t['domain']}[{t['start']:#x}+{t['length']}] stretch {lo:#x}..{hi:#x} ({hi - lo}) target offsets {tlo:#x}..{thi:#x}")
    print('anchors', [hex(x) for x in anchors[:10]])
    pc, win, via = cs.writer_window(rec, scene, rom, skip, t)
    print('writer pc', hex(pc) if pc is not None else None, 'via', via)
    pcs = Counter(d.pcs[i] for i in range(lo, hi))
    print('writer pcs in stretch', [(hex(p), n) for p, n in pcs.most_common(4)])
    if win:
        for i in range(0, len(win), 32):
            print('   code', win[i:i + 32].hex(' '))
    base = anchors[0]
    for at in ([a.at] if a.at is not None else anchors[:3]):
        print(f'ROM at {at:#x} (-16):')
        for r in range(a.rows):
            o = at - 16 + r * 32
            print(f'  {o:06x}', rom[skip + o:skip + o + 32].hex(' '))
    for name, s in (('stretch start', lo), ('target', max(lo, t['start'] - 32))):
        print(f'{name}: video memory, then tag offsets relative to {base:#x}')
        for r in range(a.rows):
            i = s + r * 16
            if i >= hi:
                break
            print(f'  {i:05x}', bytes(d.data[i:i + 16]).hex(' '))
            print('       ', ' '.join(('=' if tag_kind(d.tags[k]) == 1 else '~' if tag_kind(d.tags[k]) == 3 else 'c' if tag_kind(d.tags[k]) == 2 else '.')
                                      + (f'{tag_offset(d.tags[k]) - base:x}' if tag_kind(d.tags[k]) else '') for k in range(i, min(i + 16, hi))))


if __name__ == '__main__':
    main()
