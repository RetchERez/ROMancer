"""Fresh-workspace acceptance for the "Scenes & colors" tracing engines.

    python tools/verify_trace_engines.py --workspace <new folder> --output <new report.json> [--rom <game>]

Run it with the release's own Python to check a packaged build (the pinned
tracing engines in trace-cores are then the only ones that load), or from a
source checkout with ROMANCER_TRACE_CORES set.

For each of the six systems it opens ROMancer's original drawing program in
the editor and records scenes with the tracing engine. With --rom it also
runs the whole editor on that game: record scenes, change one color, wait for
the real engine to confirm it, keep it, review, save a separate build and
check the new bytes. This tests engine loading and the edit pipeline, not
every game.
"""
import argparse
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from romancer import ROMANCER_VERSION
from romancer.workbench_api import WorkbenchAPI

SYSTEMS = ('nes', 'snes', 'genesis', 'gb', 'gbc', 'sms')


def _wait(read, done, seconds, what):
    deadline = time.monotonic() + seconds
    value = read()
    while not done(value):
        if time.monotonic() > deadline:
            raise ValueError('timed out: ' + what)
        time.sleep(0.2)
        value = read()
    return value


def verify_trace_engines(workspace, output, rom=None, *, steps=6):
    from romancer import trace_cores
    from romancer.bundled_cores import packaged_release
    workspace = Path(workspace).absolute()
    output = Path(output).absolute()
    if workspace.exists() or output.exists():
        raise ValueError('choose new acceptance workspace and report paths')
    report = {'ok': False, 'version': ROMANCER_VERSION, 'packaged_release': packaged_release(),
              'scope': 'Tracing-engine loading, scene recording and (with --rom) one confirmed color edit. Not whole-game certification.',
              'systems': [], 'edit': None}
    api = WorkbenchAPI(workspace)

    def call(operation, **parameters):
        result = api.dispatch(operation, parameters)
        if not result.get('ok'):
            raise ValueError(operation + ': ' + str(result.get('error')))
        return result

    def record(base):
        opened = call('edits.open', **base)
        if not opened['engine']['installed']:
            raise ValueError(opened['engine'].get('reason') or 'tracing engine is not installed')
        call('edits.record', **base, steps=steps, restart=False)
        state = _wait(lambda: call('edits.open', **base), lambda s: s['recording']['state'] != 'running', 300, 'recording scenes')
        if state['recording']['state'] != 'finished':
            raise ValueError('recording did not finish: ' + json.dumps(state['recording'])[:300])
        if not state['scenes']:
            # A still picture gives automatic play nothing new to record: capture a moment by hand.
            _wait(lambda: call('edits.play', **base, frames=30, buttons=[]), lambda frame: not frame.get('busy'), 120, 'starting play')
            call('edits.capture', **base, label='Acceptance')
            state = call('edits.open', **base)
        if not state['scenes']:
            raise ValueError('no scene could be recorded or captured')
        return state

    try:
        for system in SYSTEMS:
            core = trace_cores.trace_core_for(system)
            pin = trace_cores.require_reviewed_trace_core(core)
            if report['packaged_release'] and not pin:
                raise ValueError(system + ': a packaged release loaded an unpinned tracing engine')
            demo = call('project.demo_system', system_id=system)
            source = call('project.open', project_id=demo['project_id'])['sources'][0]
            base = {'project_id': demo['project_id'], 'artifact_id': source['artifact_id']}
            state = record(base)
            view = call('edits.scene', **base, scene_id=state['scenes'][0]['id'])
            call('edits.close', **base)
            report['systems'].append({'system': system, 'engine': core.name, 'pinned': bool(pin), 'name': (pin or {}).get('name'),
                                      'scenes': len(state['scenes']), 'colors': len(view['swatches']),
                                      'editable_colors': sum(1 for s in view['swatches'] if s['editable'])})
        if rom is not None:
            project = call('project.create', name='Tracing acceptance')
            imported = call('source.import', project_id=project['project_id'], path=str(Path(rom).absolute()), system=None)
            base = {'project_id': project['project_id'], 'artifact_id': imported['artifact_id']}
            state = record(base)
            change = None
            tried = 0
            for row in state['scenes']:
                view = call('edits.scene', **base, scene_id=row['id'])
                for swatch in view['swatches']:
                    if not swatch['editable'] or len(swatch['colors']) != 1 or tried >= 6:
                        continue
                    tried += 1
                    wanted = [[0, 0, 255]] if swatch['colors'] != [[0, 0, 255]] else [[0, 255, 0]]
                    proposed = call('edits.propose_color', **base, scene_id=row['id'], domain=swatch['domain'], entry=swatch['entry'],
                                    colors=wanted, scope='all')['change']
                    proposed = _wait(lambda: call('edits.change', **base, change_id=proposed['id'])['change'],
                                     lambda c: not c['working'], 300, 'confirming the color change')
                    if proposed['verified']:
                        change, target = proposed, swatch
                        break
                    call('edits.remove', **base, change_id=proposed['id'])
                if change:
                    break
            if not change:
                raise ValueError('no color change was confirmed by the engine in the recorded scenes')
            call('edits.keep', **base, change_id=change['id'])
            review = _wait(lambda: call('edits.review', **base), lambda r: r['ready'], 300, 'review')
            saved = call('edits.save', **base, revision=review['revision'])
            original = Path(rom).read_bytes()
            built = Path(saved['path']).read_bytes()
            changed = sum(1 for a, b in zip(original, built) if a != b)
            if saved['status'] != 'BUILT' or len(built) != len(original) or not changed:
                raise ValueError('the saved build does not carry the edit')
            report['edit'] = {'system': imported.get('system_id'), 'scenes': len(state['scenes']), 'from_rgb': target['colors'],
                              'to_rgb': change['to_rgb'], 'verified': True, 'scenes_affected': change['scene_count'],
                              'badge': change['badge'], 'bytes_changed': changed, 'checksum_note': saved['checksum_note'],
                              'build_status': saved['status']}
        report['ok'] = True
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        api.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rom', type=Path, help='a game to run one confirmed color edit on')
    args = parser.parse_args()
    print(json.dumps(verify_trace_engines(args.workspace, args.output, args.rom)))
