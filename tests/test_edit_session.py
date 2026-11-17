"""The "know every change" editor: tracing-engine lookup, the session model and its workbench operations.

The end-to-end tests run a real Game Boy Color game in the Gambatte tracing
engine. They need the tracing engines (ROMANCER_TRACE_CORES, or the
trace-win folder beside this checkout) and the local ROM corpus; without
either they are skipped.
"""
import base64
import functools
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = Path(os.environ.get('ROMANCER_TRACE_CORES') or ROOT.parent / 'trace-win')
CORPUS = ROOT.parent / 'trace' / 'corpus_index.json'
GAME = 'Tetris DX (World)'


@functools.lru_cache(maxsize=None)
def corpus_rom(name, system):
    """Bytes and suffix of the first corpus ROM whose member name starts with `name`."""
    if not CORPUS.is_file():
        return None
    for entry in json.loads(CORPUS.read_text()).values():
        if entry['system_id'] != system or not Path(entry['member'].split('!')[-1]).name.startswith(name):
            continue
        if not Path(entry['zip']).is_file():
            return None
        data = Path(entry['zip']).read_bytes()
        members = re.split(r'(?<=\.zip)!', entry['member'], flags=re.I)
        for member in members:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                data = archive.read(member)
        return data, Path(members[-1]).suffix
    return None


def tracing_ready():
    if not TRACE_DIR.is_dir():
        return False
    from romancer import trace_cores
    with mock.patch.dict(os.environ, {trace_cores.ENV: str(TRACE_DIR)}):
        try:
            trace_cores.trace_core_for('gbc')
        except trace_cores.TraceCoreMissing:
            return False
    return True


class TraceCoreLookupTests(unittest.TestCase):
    def test_missing_engine_is_a_plain_message_and_only_tracing_builds_are_accepted(self):
        from romancer import trace_cores
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {trace_cores.ENV: temp}):
            with self.assertRaisesRegex(trace_cores.TraceCoreMissing, 'tracing engine is not installed for Mega Drive'):
                trace_cores.trace_core_for('genesis')
            suffix = trace_cores._suffix()
            ordinary = Path(temp) / ('blastem_libretro' + suffix)
            ordinary.write_bytes(b'an ordinary playback engine')
            with self.assertRaises(trace_cores.TraceCoreMissing):
                trace_cores.trace_core_for('genesis')
            nested = Path(temp) / 'out'
            nested.mkdir()
            (nested / ('blastem_libretro' + suffix)).write_bytes(b'\0' + trace_cores.MARKER + b'\0')
            self.assertEqual(trace_cores.trace_core_for('genesis'), (nested / ('blastem_libretro' + suffix)).resolve())
            self.assertEqual(trace_cores.trace_core_for('sms'), trace_cores.trace_core_for('genesis'))
            states = trace_cores.available()
            self.assertTrue(states['genesis']['installed'])
            self.assertFalse(states['nes']['installed'])
            self.assertIn('NES', states['nes']['reason'])
        with self.assertRaises(trace_cores.TraceCoreMissing):
            trace_cores.trace_core_for('gba')

    def test_packaged_release_runs_only_pinned_tracing_engines_and_play_keeps_its_own_check(self):
        from romancer import bundled_cores, trace_cores
        with tempfile.TemporaryDirectory() as temp:
            core = Path(temp) / 'engine.dll'
            core.write_bytes(trace_cores.MARKER)
            self.assertIsNone(trace_cores.require_reviewed_trace_core(core), 'a source checkout loads any tracing build')
            with mock.patch.object(bundled_cores, 'packaged_release', return_value=True):
                with self.assertRaisesRegex(ValueError, 'reviewed tracing engines'):
                    trace_cores.require_reviewed_trace_core(core)
                with self.assertRaisesRegex(ValueError, 'reviewed open-source'):
                    bundled_cores.require_reviewed_release_core(core)
                import hashlib
                pin = {'name': 'Reviewed', 'license': 'GPL-2.0', 'source_url': 'https://example.invalid', 'source_commit': 'abc'}
                with mock.patch.dict(trace_cores.TRACE_CORE_PINS, {hashlib.sha256(core.read_bytes()).hexdigest(): pin}):
                    self.assertEqual(trace_cores.require_reviewed_trace_core(core)['name'], 'Reviewed')
            plain = Path(temp) / 'plain.dll'
            plain.write_bytes(b'no marker')
            with self.assertRaisesRegex(ValueError, 'not a ROMancer tracing build'):
                trace_cores.require_reviewed_trace_core(plain)

    def test_header_skip_and_pickers_match_what_each_system_stores(self):
        from romancer import trace_cores
        from romancer.edit_session import picker_for
        self.assertEqual(trace_cores.header_skip(b'NES\x1a' + bytes(12), '.nes'), 16)
        self.assertEqual(trace_cores.header_skip(bytes(512 + 32768), '.smc'), 512)
        self.assertEqual(trace_cores.header_skip(bytes(32768), '.sfc'), 0)
        self.assertEqual(len(picker_for('rgb555-le')['levels']), 32)
        self.assertEqual(picker_for('genesis')['levels'], [0, 36, 73, 109, 146, 182, 219, 255])
        self.assertEqual(picker_for('sms-rgb222')['levels'], [0, 85, 170, 255])
        nes = picker_for('nes-index')
        self.assertEqual((nes['kind'], len(nes['colors'])), ('master', 64))
        self.assertEqual(picker_for('dmg-shades')['kind'], 'shades')

    def test_scene_graphics_finds_a_scrolled_background_in_the_recorded_screen_and_names_the_picture_under_a_pixel(self):
        """No engine needed: a Game Boy Color scene is built by hand, drawn scrolled, and found again from the picture."""
        from array import array
        from romancer import edit_session as es, graphics_trace as gt, provenance as pv, scene_graphics as sg
        from romancer.level_palette import decode_palette
        import random
        rng = random.Random(7)
        vram, tags = bytearray(0x4000), array('I', [0]) * 0x4000
        for n in range(1, 40):                                   # 39 pictures with something in them
            vram[n * 16:n * 16 + 16] = bytes(rng.randrange(256) for _ in range(16))
        for i in range(0x400):                                   # a map of them, with palette lines 0-3 in bank 1
            vram[0x1800 + i] = 1 + (i * 7 + i // 32) % 39
            vram[0x3800 + i] = (i // 5) % 4
        for a in list(range(16, 40 * 16)) + list(range(0x1800, 0x1C00)):
            tags[a] = pv.RT_ROM << 28 | (0x4000 + a)             # plain copies from the ROM
        for a in range(0x3800, 0x3C00):
            tags[a] = pv.RT_DERIVED << 28 | 0x9000
        palette = bytearray()
        for i in range(64):
            palette += ((i * 5 % 32) | (i * 11 % 32) << 5 | (31 - i % 32) << 10).to_bytes(2, 'little')
        domains = {'vram': pv.DomainSnapshot('vram', bytes(vram), tags, array('I', [0]) * 0x4000),
                   'palette': pv.DomainSnapshot('palette', bytes(palette), array('I', [pv.RT_ROM << 28 | (0x100 + i) for i in range(128)]), array('I', [0]) * 128),
                   'oam': pv.DomainSnapshot('oam', bytes(160), array('I', [0]) * 160, array('I', [0]) * 160)}
        scene = pv.Scene('0123456789abcdef', 600, 'ab', [], pv.Snapshot(600, domains, 'ab'))
        scene.video = {'system': 'gbc', 'source': 'registers', 'lcdc': 0x91, 'scx': 0, 'scy': 0, 'wx': 7, 'wy': 144}   # registers say "not scrolled"
        colors = decode_palette(bytes(palette), 'rgb555-le', 64)
        rgb = bytearray()
        for y in range(144):                                     # the screen, really scrolled 13 across and 21 down
            for x in range(160):
                mx, my = (x + 13) % 256, (y + 21) % 256
                cell = (my // 8) * 32 + mx // 8
                raw = vram[vram[0x1800 + cell] * 16:vram[0x1800 + cell] * 16 + 16]
                rgb += bytes(colors[vram[0x3800 + cell] * 4 + gt.decode_tile(bytes(raw), 'gb-2bpp')[(my % 8) * 8 + mx % 8]])
        rom = bytes(0x8000)
        graphics = sg.SceneGraphics(scene, 'gbc', rom, bytes(rgb), 160, 144)
        layer = graphics.layers()[0]
        self.assertEqual((layer.source, graphics.bands(layer)), ('picture', [[0, 144, 13, 21]]), 'the picture, not the registers, places the layer')
        hit = graphics.lookup(50, 60)[0]
        cell = ((60 + 21) // 8) * 32 + (50 + 13) // 8
        self.assertEqual((hit['kind'], hit['cell'], hit['tile']), ('background', [cell % 32, cell // 32], sg.tile_id('vram', vram[0x1800 + cell] * 16, 'gb-2bpp')))
        self.assertEqual(hit['pixel'], [(50 + 13) % 8, (60 + 21) % 8])
        self.assertEqual(hit['rect'], [50 - (50 + 13) % 8, 60 - (60 + 21) % 8, 8, 8])
        view = graphics.view(lambda tile: 2, {}, {})
        self.assertEqual(view['layers'][0]['seen'], 100)
        self.assertEqual(view['layers'][0]['counts'], {'rom': 0, 'code': 0, 'derived': 1024, 'unknown': 0}, 'a cell with a computed byte is not plain')
        shown = [t for t in view['tiles'] if t['on_screen']]
        self.assertEqual(len(shown), 39)
        self.assertTrue(all(t['how'] == 'direct' and t['editable'] and t['uses'] == 2 and 'plain picture data' in t['reason'] for t in shown))
        empty = sg.tile_reason(graphics.tile('vram', 100 * 16, 'gb-2bpp'), 'gbc')
        self.assertEqual(empty[:2], ('patch', True))
        self.assertEqual(sg.tile_reason(graphics.tile('vram', 100 * 16, 'gb-2bpp'), 'nes')[:2] if not sg.overlay_available('nes') else ('locked', False), ('locked', False))
        pixels = sg.parse_pixels(shown[0]['pixels'], 'gb-2bpp')
        self.assertEqual(sg.pixel_text(pixels, 'gb-2bpp'), shown[0]['pixels'])
        with self.assertRaisesRegex(ValueError, '8 by 8'):
            sg.parse_pixels('0123', 'gb-2bpp')
        first = layer.layer.cell(0, 0)
        self.assertEqual(sg.hardware_tile(layer, first, 'vram', 5 * 16, 'gb-2bpp'), 5)
        with self.assertRaisesRegex(ValueError, 'other picture bank'):
            sg.hardware_tile(layer, first, 'vram', 0x2000 + 5 * 16, 'gb-2bpp')
        # scene files keep the video registers
        import tempfile as _t
        with _t.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.scene'
            es.write_scene(path, scene, {'id': scene.id, 'frame': 600, 'screen_sha256': 'ab', 'run': 'r', 'video': scene.video}, 160, 144, bytes(rgb))
            self.assertEqual(es.read_scene(path)[0].video['lcdc'], 0x91)


    def test_scene_file_round_trip_and_checkpoint_thinning(self):
        from array import array
        from romancer import edit_session as es, provenance as pv
        snapshot = pv.Snapshot(7, {'palette': pv.DomainSnapshot('palette', b'\x01\x02', array('I', [0x10000005, 0]), array('I', [9, 0])),
                                   'chr': pv.DomainSnapshot('chr', None, array('I', [0x30000001]), array('I', [3]))}, 'ab')
        scene = pv.Scene('0123456789abcdef', 7, 'ab', [], snapshot, 'Title')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.scene'
            es.write_scene(path, scene, {'id': scene.id, 'frame': 7, 'screen_sha256': 'ab', 'label': 'Title', 'run': 'r'}, 2, 1, b'\x01\x02\x03\x04\x05\x06')
            loaded, header, rgb = es.read_scene(path)
            self.assertEqual((loaded.id, loaded.frame, header['label'], rgb), (scene.id, 7, 'Title', b'\x01\x02\x03\x04\x05\x06'))
            self.assertEqual(loaded.snapshot.domains['palette'].sources(), {5: [0]})
            self.assertIsNone(loaded.snapshot.domains['chr'].data)
            self.assertEqual(es.read_scene_header(path)['width'], 2)
        states = [(f, b'') for f in range(0, 3001, 60)]
        frames = [f for f, _ in es._thin(states, 2990)]
        self.assertEqual(frames[0], 0)
        self.assertEqual(frames[-1], 2940)
        self.assertLess(len(frames), 9, 'replays step back twice as far each time, not through every savestate')
        self.assertEqual(es._thin(states, 0), [])


@unittest.skipUnless(tracing_ready() and corpus_rom(GAME, 'gbc'), 'needs the Gambatte tracing engine and the local ROM corpus')
class EditSessionEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = Path(tempfile.mkdtemp(prefix='romancer-edit-'))
        data, suffix = corpus_rom(GAME, 'gbc')
        cls.rom = cls.temp / ('game' + suffix)
        cls.rom.write_bytes(data)
        cls.patcher = mock.patch.dict(os.environ, {'ROMANCER_TRACE_CORES': str(TRACE_DIR), 'ROMANCER_TRACE_WORKERS': '2'})
        cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        shutil.rmtree(cls.temp, ignore_errors=True)

    def test_model_records_scenes_shows_every_affected_scene_and_saves_only_after_review(self):
        from romancer.edit_session import EditSession
        store = self.temp / 'store'
        session = EditSession(store, self.rom, 'gbc')
        try:
            session.record(12, wait=True)
            self.assertEqual(session.recording['state'], 'finished', session.recording)
            summary = session.summary()
            self.assertGreaterEqual(len(summary['scenes']), 3)
            # The title screen: its red is shared by several scenes.
            target = None
            for row in summary['scenes']:
                view = session.scene_view(row['id'])
                target = next((s for s in view['swatches'] if s['editable'] and s['uses'] >= 2 and s['colors'] == [[255, 0, 0]]), None)
                if target:
                    scene_id = row['id']
                    break
            self.assertIsNotNone(target, 'an editable shared color')
            self.assertEqual(view['pickers']['rgb555-le']['kind'], 'levels')
            self.assertTrue(all(s['editable'] or s['locked_reason'] for s in view['swatches']))
            with self.assertRaisesRegex(ValueError, 'already has'):
                session.propose_color(scene_id, target['domain'], target['entry'], [[255, 0, 0]])
            change = session.propose_color(scene_id, target['domain'], target['entry'], [[0, 255, 0]])
            self.assertEqual(change['state'], 'preview')
            self.assertEqual(change['to_rgb'], [[0, 255, 0]])
            self.assertTrue(session.wait(300))
            change = session.change(change['id'])
            self.assertEqual(change['working'], 0)
            self.assertTrue(change['verified'] and change['verified_here'])
            self.assertEqual(change['scene_count'], target['uses'])
            self.assertRegex(change['badge'], r'Used in \d+ scenes')
            self.assertIn("Scenes you haven't recorded can't be shown", change['coverage'])
            own = change['affected'][0]
            self.assertTrue(own['edited_here'] and own['verified'])
            self.assertTrue(all(a['after'] and a['state'] == 'done' for a in change['affected']))
            self.assertTrue(session.image(own['after']).startswith(b'\x89PNG'))
            visible = [a for a in change['affected'] if a['visible']]
            self.assertTrue(visible, 'at least one scene is redrawn differently by the real engine')
            self.assertNotEqual(session.image(visible[0]['before']), session.image(visible[0]['after']))
            with self.assertRaisesRegex(ValueError, 'Keep or cancel'):
                session.review()
            exported = []
            with self.assertRaisesRegex(ValueError, 'Review'):
                session.save(lambda edits, notes: exported.append(edits) or {}, session.revision)
            session.keep(change['id'])
            listing = session.change_list()
            self.assertEqual(len(listing['changes']), 1)
            self.assertRegex(listing['summary'], r'1 change: affects \d+ scenes')
            self.assertEqual(session.scene_view(scene_id)['swatches'][target['entry']]['pending'], [[0, 255, 0]])
            # A generic write list (as graphics_trace plans) goes through the same pipeline.
            offset = target['details'][0]['file_offset']
            generic = session.propose_writes(scene_id, [[offset + 2, session.rom[offset + 2], session.rom[offset + 2] ^ 0x1F]], 'Tile edit')
            self.assertEqual(generic['kind'], 'graphics')
            self.assertTrue(session.wait(300))
            session.remove(generic['id'])
            self.assertIsNone(session.summary()['preview'])
            review = session.review()
            deadline = time.monotonic() + 120
            while not review['ready'] and time.monotonic() < deadline:
                time.sleep(0.2)
                review = session.review()
            self.assertTrue(review['ready'])
            self.assertEqual(review['bytes'], 2)
            self.assertIn('1 change will be written', review['headline'])
            self.assertEqual(len(review['scenes']), target['uses'])
            with self.assertRaisesRegex(ValueError, 'Review it again'):
                session.save(lambda edits, notes: {}, review['revision'] + 1)
            result = session.save(lambda edits, notes: exported.append((edits, notes)) or {'artifact_id': 'x'}, review['revision'])
            self.assertEqual(result, {'artifact_id': 'x'})
            edits, notes = exported[0]
            self.assertEqual([(e['offset'], e['before']) for e in edits], [(offset, session.rom[offset:offset + 2].hex())])
            self.assertEqual(notes['changes'][0]['verified'], True)
            self.assertEqual(session.change_list()['changes'], [])
            # Capture from play.
            frame = session.play(20, ['start'])
            deadline = time.monotonic() + 60
            while frame.get('busy') and time.monotonic() < deadline:
                time.sleep(0.2)
                frame = session.play(20, ['start'])
            self.assertTrue(base64.b64decode(frame['png_base64']).startswith(b'\x89PNG'))
            before = len(session.scenes)
            captured = session.capture('My moment')
            self.assertEqual(len(session.scenes), before + 1)
            self.assertEqual(next(s for s in captured['scenes'] if s['id'] == captured['scene_id'])['label'], 'My moment')
        finally:
            session.close()
        # Scenes and their impact index are still there next time.
        reopened = EditSession(store, self.rom, 'gbc')
        try:
            self.assertEqual(len(reopened.scenes), before + 1)
            self.assertEqual(reopened.scene_view(scene_id)['swatches'][target['entry']]['uses'], target['uses'] + 1, 'the captured moment uses it too')
        finally:
            reopened.close()

    def test_a_picture_and_background_cells_are_planned_replayed_listed_and_saved(self):
        from romancer import graphics_trace as gt, scene_graphics as sg
        from romancer.edit_session import EditSession
        store = self.temp / 'store-graphics'
        session = EditSession(store, self.rom, 'gbc')

        def settle(change):
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                view = session.change(change['id'])
                if not view['working']:
                    return view
                time.sleep(0.2)
            self.fail('the change never settled')
        try:
            session.record(12, wait=True)
            self.assertEqual(session.recording['state'], 'finished', session.recording)
            # a scene whose background was found in the picture and holds plainly stored pictures and cells
            for scene_id in session.scenes:
                self.assertEqual(session.scenes[scene_id].video['source'], 'registers', 'the video registers are stored with the scene')
                view = session.graphics_view(scene_id)
                layer = max(view['layers'], key=lambda row: row['seen'])
                plain = [t for t in view['tiles'] if t['on_screen'] and t['how'] == 'direct' and t['kind'] == 'bg' and not t['blank']]
                if layer['placed_by'] == 'picture' and len(plain) > 4 and layer['cells']['status'].count('r') > 20:
                    break
            else:
                self.fail('no scene with a placed background and plain pictures')
            self.assertEqual(len(view['colors']), 64)
            self.assertTrue(all(t['editable'] or t['reason'] for t in view['tiles']))
            first, last, across, down = layer['bands'][0]
            # the picture under a pixel: a cell fully on screen whose picture is stored plainly
            target = None
            for index, address in enumerate(layer['cells']['tile']):
                tile = next((t for t in plain if t['address'] == address and t['domain'] == layer['tile_domain']), None)
                x, y = (index % 32 * 8 - across) % 256, (index // 32 * 8 - down) % 256
                if tile and x < 152 and first <= y < last - 8:
                    target = (tile, x, y, index)
                    break
            self.assertIsNotNone(target)
            tile, x, y, index = target
            found = session.tile_at(scene_id, x + 3, y + 5)
            self.assertEqual(found['hits'][0]['tile'], tile['id'])
            self.assertEqual(found['hits'][0]['cell'], [index % 32, index // 32])
            self.assertEqual(found['hits'][0]['rect'], [x, y, 8, 8])
            with self.assertRaisesRegex(ValueError, 'already has'):
                session.propose_tile(scene_id, tile['id'], tile['pixels'])
            drawn = ''.join('%x' % (3 - int(c, 16)) for c in tile['pixels'])
            change = session.propose_tile(scene_id, tile['id'], drawn)
            self.assertTrue(change['planning'])
            change = settle(change)
            self.assertEqual((change['error'], change['method'], change['kind']), ('', 'direct', 'graphics'))
            self.assertTrue(change['verified'])
            here, power = change['checks'][0], change['checks'][1]
            self.assertEqual((here['name'], here['state']), ('In this scene', 'good'))
            self.assertIn('came out exactly as you made it', here['text'])
            self.assertEqual((power['name'], power['state']), ('From power-on', 'good'))
            self.assertIn('ROMancer also replayed the game from power-on: clean', power['text'])
            self.assertGreaterEqual(change['scene_count'], tile['uses'], 'every scene that loads those ROM bytes is re-rendered')
            self.assertTrue(all(a['state'] == 'done' and a['after'] for a in change['affected']))
            self.assertTrue(change['affected'][0]['visible'])
            self.assertEqual(change['tiles'], [{'id': tile['id'], 'from': tile['pixels'], 'to': drawn}])
            self.assertFalse(any(row['file_offset'] in (0x14D, 0x14E, 0x14F) for row in change['details']), 'the checksum is the session\'s to update')
            session.keep(change['id'])
            pending = next(t for t in session.graphics_view(scene_id)['tiles'] if t['id'] == tile['id'])['pending']
            self.assertEqual(pending['pixels'], drawn)
            # background: two cells that are stored on their own take another picture, as one change
            source = layer['cells']['source']
            alone = [i for i, s in enumerate(layer['cells']['status']) if s == 'r' and source.count(source[i]) == 1
                     and layer['cells']['tile'][i] != tile['address'] and layer['cells']['tile'][i] >> 13 == tile['address'] >> 13][:2]
            self.assertEqual(len(alone), 2)
            cells = [{'layer': layer['index'], 'x': i % 32, 'y': i // 32, 'tile': tile['id']} for i in alone]
            painted = settle(session.propose_cells(scene_id, cells))
            self.assertEqual((painted['error'], painted['method'], painted['kind'], painted['cell_count']), ('', 'cells', 'background', 2))
            self.assertTrue(painted['verified'], painted['checks'])
            self.assertIn('clean', painted['checks'][1]['text'])
            self.assertEqual(painted['title'], '2 background cells')
            session.keep(painted['id'])
            self.assertEqual(len(session.graphics_view(scene_id)['layers'][layer['index']]['pending']), 2)
            with self.assertRaisesRegex(ValueError, 'outside the background'):
                session.propose_cells(scene_id, [{'layer': layer['index'], 'x': 99, 'y': 0, 'tile': tile['id']}])
            review = session.review()
            deadline = time.monotonic() + 300
            while not review['ready'] and time.monotonic() < deadline:
                time.sleep(0.2)
                review = session.review()
            self.assertTrue(review['ready'])
            self.assertEqual((len(review['changes']), review['unverified'], review['grows']), (2, [], 0))
            exported = []
            session.save(lambda edits, notes: exported.append((edits, notes)) or {'artifact_id': 'x'}, review['revision'])
            edits, notes = exported[0]
            self.assertEqual([c['method'] for c in notes['changes']], ['direct', 'cells'])
            self.assertTrue(all(c['verified'] for c in notes['changes']))
            built = bytearray(session.rom)
            for edit in edits:
                self.assertEqual(session.rom[edit['offset']:edit['offset'] + len(edit['before']) // 2].hex(), edit['before'])
                built[edit['offset']:edit['offset'] + len(edit['after']) // 2] = bytes.fromhex(edit['after'])
            item = session._graphics(scene_id).tile(*sg.parse_tile_id(tile['id']))
            at = item.sources[0]['offset']
            self.assertEqual(bytes(built[at:at + 16]), gt.encode_tile(sg.parse_pixels(drawn, 'gb-2bpp'), 'gb-2bpp'))
            for i in alone:
                self.assertEqual(built[source[i]], (tile['address'] & 0x1FFF) // 16 % 256)
        finally:
            session.close()


    def test_workbench_operations_change_a_color_and_the_saved_build_boots_with_it(self):
        from romancer import palette_trace as pt, provenance as pv, trace_cores
        from romancer.edit_session import _Engine
        from romancer.workbench_api import WorkbenchAPI
        api = WorkbenchAPI(self.temp / 'workspace')
        try:
            project = api.dispatch('project.create', {'name': 'Colors'})
            imported = api.dispatch('source.import', {'project_id': project['project_id'], 'path': str(self.rom), 'system': None})
            self.assertTrue(imported['ok'], imported)
            base = {'project_id': project['project_id'], 'artifact_id': imported['artifact_id']}

            def call(operation, **more):
                result = api.dispatch('edits.' + operation, {**base, **more})
                self.assertTrue(result['ok'], result)
                return result
            opened = call('open')
            self.assertTrue(opened['engine']['installed'])
            self.assertEqual(opened['scenes'], [])
            state = call('record', steps=8, restart=False)
            deadline = time.monotonic() + 120
            while state['recording']['state'] == 'running' and time.monotonic() < deadline:
                time.sleep(0.2)
                state = call('open')
            self.assertEqual(state['recording']['state'], 'finished', state['recording'])
            for row in state['scenes']:
                view = call('scene', scene_id=row['id'])
                target = next((s for s in view['swatches'] if s['editable'] and s['colors'] == [[255, 0, 0]]), None)
                if target:
                    break
            self.assertIsNotNone(target)
            self.assertTrue(base64.b64decode(call('image', key=view['scene']['image'])['png_base64']).startswith(b'\x89PNG'))
            change = call('propose_color', scene_id=row['id'], domain=target['domain'], entry=target['entry'], colors=[[0, 0, 255]], scope='all')['change']
            deadline = time.monotonic() + 300
            while change['working'] and time.monotonic() < deadline:
                time.sleep(0.2)
                change = call('change', change_id=change['id'])['change']
            self.assertTrue(change['verified'], change['verdict'])
            self.assertIn(opened['private_copy']['available'], (True, False))
            self.assertTrue(opened['private_copy']['available'] or 'private copy' in opened['private_copy']['reason'])
            kept = call('keep', change_id=change['id'])
            self.assertEqual(len(kept['changes']['changes']), 1)
            refused = api.dispatch('edits.save', {**base, 'revision': kept['changes']['revision']})
            self.assertFalse(refused['ok'])
            review = call('review')
            deadline = time.monotonic() + 300
            while not review['ready'] and time.monotonic() < deadline:
                time.sleep(0.2)
                review = call('review')
            saved = call('save', revision=review['revision'])
            self.assertEqual(saved['status'], 'BUILT')
            self.assertIn('checksum', saved['checksum_note'])
            self.assertEqual(saved['session']['changes']['changes'], [])
            built = Path(saved['path'])
            original = self.rom.read_bytes()
            patched = built.read_bytes()
            offset = target['details'][0]['file_offset']
            self.assertEqual(patched[offset:offset + 2], bytes.fromhex('007c'), 'pure blue in RGB555')
            self.assertEqual(original[offset:offset + 2], bytes.fromhex('1f00'))
            # The saved build boots in the engine and the game loads the new color into the same palette entry.
            scene = api.edit_sessions.session(base).scenes[row['id']]
            with mock.patch.dict(os.environ, {'ROMANCER_TRACE_CORES': str(TRACE_DIR)}):
                fe = _Engine(trace_cores.trace_core_for('gbc'), save_dir=self.temp / 'boot', core_options=trace_cores.core_options('gbc'))
            try:
                fe.load_game(built)
                session = pv.TraceSession(fe)
                session.start()
                from romancer.edit_session import explore
                session.run(scene.frame, explore)
                booted = pv.scene_from_session(session)
                swatch = next(s for s in pt.swatches(booted, 'gbc') if s.domain == target['domain'] and s.entry == target['entry'])
                self.assertEqual(swatch.rgb, [[0, 0, 255]])
            finally:
                fe.close()
        finally:
            api.close()


if __name__ == '__main__':
    unittest.main()
