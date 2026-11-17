"""Check that a tracing engine's domain contents are the machine's real state.

    python -B trace/palette_state_check.py CORE ROM [--other ROM2] [--plain CORE] [--frames N]

ROM may be a file or ZIP!member (nested ZIPs allowed), as for trace_probe.py.

Three checks, each of which a palette shadow that only follows the game's own
register writes fails:

* loadstate: save at frame S, run on until the palette domains hold something
  else, load the state. Every domain must hold exactly what it held at save
  time, every tag must be clear (tags are not part of a savestate), and
  two replays from the state must end with the same contents and screen.
* instances: run ROM, then ROM2 (default: ROM again), then ROM a second time,
  each as a new engine instance in this one process without unloading the
  library. The second run of ROM must match the first at power-on and at
  frame N, contents and tags alike, and a reset must match power-on.
* --plain CORE: the tracing engine draws the same frames as the unpatched one.

Exit status is 0 only if every check passes.
"""
import argparse
import ctypes
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trace_probe import Domain, LibretroFrontend, read_rom, script  # noqa: E402

PALETTES = ('palette', 'dmg_palette')


def start(core, rom, suffix, work, tracing=True):
    path = Path(work) / ('game' + suffix)
    path.write_bytes(rom)
    fe = LibretroFrontend(core, save_dir=Path(tempfile.mkdtemp(prefix='rt-', dir=work)))
    if tracing:
        fe.lib.romancer_trace_domain.restype = ctypes.POINTER(Domain)
    fe.load_game(path)
    if tracing:
        fe.lib.romancer_trace_enable(1)   # deliberately no romancer_trace_reset: loading must leave nothing behind
    return fe


def domains(fe):
    out = {}
    for i in range(fe.lib.romancer_trace_domain_count()):
        d = fe.lib.romancer_trace_domain(i).contents
        n = d.size
        out[d.name.decode()] = {'data': ctypes.string_at(d.data, n) if d.data else None, 'tag': d.tag[:n], 'pc': d.pc[:n]}
    return out


def palettes(fe):
    out = {}
    for i in range(fe.lib.romancer_trace_domain_count()):
        d = fe.lib.romancer_trace_domain(i).contents
        if d.name.decode() in PALETTES and d.data:
            out[d.name.decode()] = ctypes.string_at(d.data, d.size)
    return out


def data_of(snapshot):
    return {name: d['data'] for name, d in snapshot.items()}


def differing(a, b, what=('data',)):
    return sorted(name for name in a if any(a[name][k] != b[name][k] for k in what))


def tagged(snapshot):
    return {name: sum(1 for t in d['tag'] if t) for name, d in snapshot.items() if any(d['tag'])}


def check_loadstate(core, rom, suffix, work, save_at, frames):
    fe = start(core, rom, suffix, work)
    try:
        for f in range(save_at):
            fe.run_frame(script(f))
        state, saved = fe.serialize(), domains(fe)
        moved_at = None
        for f in range(save_at, frames):
            fe.run_frame(script(f))
            if moved_at is None and palettes(fe) != {n: saved[n]['data'] for n in PALETTES if n in saved}:
                moved_at = f + 1
        stale, left, replays = [], {}, []
        # Twice: the second load starts from whatever the first replay left behind.
        for _ in range(2):
            fe.unserialize(state)
            loaded = domains(fe)
            stale += differing(saved, loaded)
            left.update(tagged(loaded))
            for f in range(save_at, frames):
                fe.run_frame(script(f))
            replays.append((data_of(domains(fe)), fe.last_frame.sha256()))
        # Gambatte itself does not continue from a loaded state exactly as it did from the save
        # (the unpatched engine behaves the same), so replays are compared with each other.
        replay_bad = differing({n: {'data': d} for n, d in replays[0][0].items()},
                               {n: {'data': d} for n, d in replays[1][0].items()})
        if replays[0][1] != replays[1][1]:
            replay_bad.append('screen')
    finally:
        fe.close()
    ok = moved_at is not None and not stale and not left and not replay_bad
    print(f'loadstate: saved at frame {save_at}; palette contents first differed at frame {moved_at}; '
          f'after loading, domains differing from save time: {sorted(set(stale)) or "none"}; tags left: {left or "none"}; '
          f'two replays from the state to frame {frames} differ in: {replay_bad or "nothing"} -> {"PASS" if ok else "FAIL"}')
    return ok


def check_instances(core, rom, suffix, other, other_suffix, work, frames):
    def play(data, sfx, with_reset=False):
        fe = start(core, data, sfx, work)
        try:
            boot = domains(fe)
            for f in range(frames):
                fe.run_frame(script(f))
            end = domains(fe)
            reset = None
            if with_reset:
                fe.lib.retro_reset()
                reset = domains(fe)
            return boot, end, reset
        finally:
            fe.close()

    first_boot, first_end, _ = play(rom, suffix)
    other_boot, other_end, _ = play(other, other_suffix)
    again_boot, again_end, again_reset = play(rom, suffix, with_reset=True)
    both = ('data', 'tag', 'pc')
    boot_bad = differing(first_boot, again_boot, both)
    end_bad = differing(first_end, again_end, both)
    reset_bad = differing(first_boot, again_reset, both)
    boot_tags = tagged(again_boot)
    ok = not boot_bad and not end_bad and not reset_bad and not boot_tags
    print(f'instances: second run vs first, domains differing at power-on: {boot_bad or "none"}; '
          f'at frame {frames}: {end_bad or "none"}; after reset vs power-on: {reset_bad or "none"}; '
          f'tags at power-on: {boot_tags or "none"} -> {"PASS" if ok else "FAIL"}')
    return ok


def check_plain(core, plain, rom, suffix, work, frames):
    a, b = start(core, rom, suffix, work), start(plain, rom, suffix, work, tracing=False)
    try:
        bad = None
        for f in range(frames):
            x, y = a.run_frame(script(f)), b.run_frame(script(f))
            if (x.sha256() if x else None) != (y.sha256() if y else None):
                bad = f + 1
                break
        same_state = bad is None and a.serialize() == b.serialize()
    finally:
        a.close(); b.close()
    ok = bad is None and same_state
    print(f'plain: {frames} frames compared with the unpatched engine; first differing frame: {bad or "none"}; '
          f'savestates identical at the end: {same_state} -> {"PASS" if ok else "FAIL"}')
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('core'); ap.add_argument('rom')
    ap.add_argument('--other', help='a different game to run between the two runs of ROM')
    ap.add_argument('--plain', help='the unpatched engine, to compare frames against')
    ap.add_argument('--frames', type=int, default=1200)
    ap.add_argument('--save-at', type=int, default=30)
    a = ap.parse_args()
    rom, suffix = read_rom(a.rom)
    other, other_suffix = read_rom(a.other) if a.other else (rom, suffix)
    with tempfile.TemporaryDirectory() as work:
        results = [check_loadstate(a.core, rom, suffix, work, a.save_at, a.frames),
                   check_instances(a.core, rom, suffix, other, other_suffix, work, a.frames)]
        if a.plain:
            results.append(check_plain(a.core, a.plain, rom, suffix, work, a.frames))
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
