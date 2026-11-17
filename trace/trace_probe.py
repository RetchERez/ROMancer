"""Run a tracing engine on a ROM and check its provenance tags.

    python -B trace/trace_probe.py CORE ROM [--frames N] [--causal K] [--out FILE]

ROM may be a file or ZIP!member. The probe boots the game, presses Start at
intervals so it leaves the title screen, then reads every traced domain.

Two checks decide whether an engine's tags can be trusted:

* consistency: for every non-weak RT_ROM/RT_IMM tag, the ROM byte at the tagged
  offset equals the current domain byte (when the engine exposes contents);
* causality (--causal K): for K sampled tagged bytes, change that ROM byte,
  replay the same frames and confirm the domain byte changed. This is the
  check that makes an edit's effect known rather than guessed.
"""
import argparse
import ctypes
import hashlib
import io
import json
import random
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import romancer.bundled_cores as _bundled  # noqa: E402

_bundled.require_reviewed_release_core = lambda path: None  # tracing builds are probed before pinning
from romancer.libretro_frontend import LibretroFrontend  # noqa: E402

KINDS = {0: 'none', 1: 'rom', 2: 'imm', 3: 'derived'}


class Domain(ctypes.Structure):
    _fields_ = [('name', ctypes.c_char_p), ('size', ctypes.c_uint32),
                ('tag', ctypes.POINTER(ctypes.c_uint32)), ('pc', ctypes.POINTER(ctypes.c_uint32)),
                ('data', ctypes.POINTER(ctypes.c_uint8))]


def read_rom(spec):
    if '!' in spec:
        archive, *members = spec.split('!')
        data = Path(archive).read_bytes()
        for member in members:  # nested ZIPs: outer.zip!inner.zip!game.gb
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                data = z.read(member)
        return data, Path(members[-1]).suffix or '.bin'
    return Path(spec).read_bytes(), Path(spec).suffix


def header_skip(data, suffix):
    if suffix.lower() == '.nes' and data[:4] == b'NES\x1a': return 16
    if suffix.lower() in ('.smc', '.sfc') and len(data) % 1024 == 512: return 512
    return 0


def script(frame):
    """Default input: idle, then Start/A taps every 90 frames to pass title screens."""
    if frame < 240 or frame % 90 >= 6: return []
    return ['start'] if (frame // 90) % 2 else ['a']


def run(core, rom_bytes, suffix, frames, workdir):
    path = Path(workdir) / ('game' + suffix)
    path.write_bytes(rom_bytes)
    fe = LibretroFrontend(core, save_dir=Path(workdir) / 'rt')
    lib = fe.lib
    lib.romancer_trace_domain.restype = ctypes.POINTER(Domain)
    lib.romancer_trace_writes.restype = ctypes.c_uint64
    fe.load_game(path)
    lib.romancer_trace_reset()
    lib.romancer_trace_enable(1)
    for f in range(frames):
        fe.run_frame(script(f))
    domains = {}
    for i in range(lib.romancer_trace_domain_count()):
        d = lib.romancer_trace_domain(i).contents
        n = d.size
        domains[d.name.decode()] = {
            'tag': d.tag[:n], 'pc': d.pc[:n],
            'data': bytes(d.data[:n]) if d.data else None,
        }
    writes = lib.romancer_trace_writes()
    frame = fe.last_frame.sha256() if getattr(fe, 'last_frame', None) else None
    fe.close()
    return domains, writes, frame


def summarize(domains, rom, skip):
    report = {}
    for name, d in domains.items():
        counts = {k: 0 for k in KINDS.values()}
        weak = consistent = checked = 0
        for i, tag in enumerate(d['tag']):
            kind = KINDS.get((tag >> 28) & 7, 'bad')
            counts[kind] = counts.get(kind, 0) + 1
            if tag & 0x80000000: weak += 1
            if kind in ('rom', 'imm') and not tag & 0x80000000 and d['data'] is not None:
                off = (tag & 0x0FFFFFFF) + skip
                checked += 1
                consistent += off < len(rom) and rom[off] == d['data'][i]
        report[name] = {'size': len(d['tag']), **counts, 'weak': weak,
                        'consistency': f'{consistent}/{checked}' if checked else 'n/a'}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('core'); ap.add_argument('rom')
    ap.add_argument('--frames', type=int, default=1200)
    ap.add_argument('--causal', type=int, default=0)
    ap.add_argument('--domains', default='palette')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--out')
    a = ap.parse_args()
    rom, suffix = read_rom(a.rom)
    skip = header_skip(rom, suffix)
    with tempfile.TemporaryDirectory() as work:
        domains, writes, frame = run(a.core, rom, suffix, a.frames, work)
        result = {'core': a.core, 'rom_sha256': hashlib.sha256(rom).hexdigest(), 'frames': a.frames,
                  'writes': writes, 'frame_sha256': frame, 'domains': summarize(domains, rom, skip)}
        if a.causal:
            rng = random.Random(a.seed); trials = []
            for name in a.domains.split(','):
                d = domains.get(name)
                if not d or d['data'] is None: continue
                candidates = [i for i, t in enumerate(d['tag']) if (t >> 28) & 7 in (1, 2) and not t & 0x80000000]
                for i in rng.sample(candidates, min(a.causal, len(candidates))):
                    off = (d['tag'][i] & 0x0FFFFFFF) + skip
                    edited = bytearray(rom); edited[off] ^= 0x0E  # visible in every palette format
                    again, _, _ = run(a.core, bytes(edited), suffix, a.frames, work)
                    after = again[name]['data'][i]
                    trials.append({'domain': name, 'index': i, 'rom_offset': off - skip,
                                   'before': d['data'][i], 'after': after, 'changed': after != d['data'][i]})
            result['causal'] = {'passed': sum(t['changed'] for t in trials), 'trials': len(trials), 'detail': trials}
    text = json.dumps(result, indent=1)
    if a.out: Path(a.out).write_text(text)
    print(text if not a.causal else json.dumps({k: v for k, v in result.items() if k != 'causal'} | {'causal': {k: result['causal'][k] for k in ('passed', 'trials')}}, indent=1))


if __name__ == '__main__':
    main()
