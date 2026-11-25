"""Level maps in an EditSession: record one while the game scrolls, show it, and change it.

A level is a list of scenes captured while the game was played, and the map
level_map.stitch puts together from them. Only the captures the map needs are
kept. The stitched map is stored beside the scenes (levels/<id>.json and one
PNG for each plane), so opening a level does not read every scene again.

An edit made on the map is a background cell edit in the scene that shows
that place. Places in several scenes are planned one scene after another by
scene_graphics (`what: 'level'`), each confirmed by replay, and offered as one
change. Every recorded scene that uses the changed bytes is then replayed, as
for any change, and the level picture is redrawn from those replays so the
map shows every place that changes.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import time
import uuid

from . import graphics_trace as gt
from . import level_layout as ll
from . import level_map as lm
from . import scene_graphics as sg

LEVEL_EVERY = 4             # frames between looks at the screen while a level is recorded
LEVEL_GAP = 12              # frames between two captures at least
MAX_LEVEL_CAPTURES = 600    # captures in one recording, before the map is put together
MAX_LEVEL_SCENES = 120      # captures a finished level may keep
MAX_LEVELS = 24
MAX_PLANES = 3
MIN_PLANE_CELLS = 200
MAX_LEVEL_CELLS = 256       # places painted in one change


class _Same(Exception):
    """A place that already shows what was painted."""


class LevelTools:
    """Mixed into EditSession."""

    # ---- store

    def _levels_init(self) -> None:
        self.levels: list[dict] = []
        self.level_rec: dict | None = None
        self.level_job: dict | None = None
        self._level_cache: dict = {}
        (self.store / 'levels').mkdir(parents=True, exist_ok=True)
        for path in sorted((self.store / 'levels').glob('*.json')):
            try:
                level = json.loads(path.read_text())
            except (ValueError, OSError):
                continue
            if not isinstance(level, dict):
                continue                    # the list of places that changed, kept beside a map after a check
            if level.get('rom_sha') == self.rom_sha and all(sid in self.scenes for sid in level.get('scene_ids', ())):
                self.levels.append(level)
        self.levels.sort(key=lambda level: level.get('created', 0))

    def _level_save(self, level: dict) -> None:
        temporary = self.store / 'levels' / (level['id'] + '.tmp')
        temporary.write_text(json.dumps(level, separators=(',', ':')))
        os.replace(temporary, self.store / 'levels' / (level['id'] + '.json'))

    def _level(self, level_id: str) -> dict:
        for level in self.levels:
            if level['id'] == level_id:
                return level
        raise ValueError('That level map is no longer stored. Record it again.')

    def level_scene_ids(self) -> set:
        ids = {sid for level in self.levels for sid in level['scene_ids']}
        if self.level_rec:
            ids.update(self.level_rec['scene_ids'])
        return ids

    def level_summary(self) -> dict:
        return {'levels': [{'id': level['id'], 'name': level['name'], 'scenes': len(level['scene_ids']),
                            'planes': [{'name': p['name'], 'width': p['width'], 'height': p['height'], 'cell': p['px']}
                                       for p in level['planes']],
                            'image': f"level:{level['id']}:0", 'pixel_width': level['planes'][0]['width'] * level['planes'][0]['px'],
                            'pixel_height': level['planes'][0]['height'] * level['planes'][0]['px']} for level in self.levels],
                'level_limit': MAX_LEVELS,
                'level_recording': {'name': self.level_rec['name'], 'captures': len(self.level_rec['scene_ids']),
                                    'limit': MAX_LEVEL_CAPTURES, 'extends': self.level_rec.get('extends'),
                                    'added': len(self.level_rec['scene_ids']) - self.level_rec.get('had', 0)} if self.level_rec else None,
                'level_job': dict(self.level_job) if self.level_job else None}

    # ---- recording

    def level_start(self, name: str = '', extend: str = None) -> dict:
        """Begin keeping captures of the live game as it is played; level_stop puts the map together. With extend (a
        level id), the new captures are added to that map: play through the parts it is missing, and the map is put
        together again from everything."""
        self._require_core()
        with self.lock:
            if self.level_job and self.level_job['state'] == 'running':
                raise ValueError('ROMancer is still putting the last level map together. Wait for it to finish.')
            if self.level_rec:
                return self.summary()
            if not (self._host and self._host[0].is_alive()):
                raise ValueError('Play the game to the start of the level first, then start recording the level.')
            if extend:
                level = self._level(extend)
                if any(c.get('level', {}).get('id') == extend for c in self._active()):
                    raise ValueError('A pending change was made on this level map. Keep or undo it before adding to the map.')
                self.level_rec = {'id': uuid.uuid4().hex[:16], 'name': level['name'], 'scene_ids': list(level['scene_ids']),
                                  'extends': extend, 'had': len(level['scene_ids'])}
                self.level_job = None
                return self.summary()
            if len(self.levels) >= MAX_LEVELS:
                raise ValueError(f'This game already has {MAX_LEVELS} level maps. Remove one before recording another.')
            number = len(self.levels) + 1
            self.level_rec = {'id': uuid.uuid4().hex[:16], 'name': str(name).strip()[:60] or f'Level map {number}', 'scene_ids': []}
            self.level_job = None
        return self.summary()

    def _level_captured(self, metas) -> None:
        """Take the scenes the host captured during a play step into the recording (the host lock is held)."""
        for meta in metas or ():
            self._add_scene(self.store / 'scenes' / (meta['id'] + '.scene'))
            if self.level_rec is not None and meta['id'] not in self.level_rec['scene_ids']:
                self.level_rec['scene_ids'].append(meta['id'])

    def level_play_label(self):
        """What play() passes to the host so it captures as it goes, or None when no level is being recorded."""
        rec = self.level_rec
        if rec is None or len(rec['scene_ids']) >= MAX_LEVEL_CAPTURES:
            return None
        return rec['name']

    def level_auto(self, steps: int = 6, direction: str = 'right', *, wait: bool = False) -> dict:
        """Let ROMancer walk on in one direction, jumping now and then, while the level is recorded."""
        self._require_core()
        steps = max(1, min(40, int(steps)))
        if direction not in ('right', 'left', 'up', 'down'):
            raise ValueError('Choose right, left, up or down.')
        with self.lock:
            if self.level_rec is None:
                raise ValueError('Start recording a level first.')
            if self.recording and self.recording['state'] == 'running':
                return self.summary()
            self.recording = {'state': 'running', 'done': 0, 'total': steps, 'found': 0, 'message': 'Playing the level…'}

        def work():
            recording = self.recording
            try:
                with self.host_lock:
                    self._start_host()
                    _, conn, variant = self._host
                    conn.send(('explore', steps, variant, self.level_rec['name'], direction))
                    while True:
                        event = self._receive()
                        if event[0] == 'step':
                            self.live['frame'] = event[4]
                            self._level_captured(event[5] if len(event) > 5 else ())
                            recording['done'] = event[1]
                            recording['found'] = len(self.level_rec['scene_ids'])
                            if recording.get('stop') or len(self.level_rec['scene_ids']) >= MAX_LEVEL_CAPTURES:
                                conn.send(('stop',))
                        elif event[0] == 'done':
                            self.live['frame'] = event[1]
                            break
                recording.update(state='finished', message=f"Captured {recording['found']} moments of the level.")
            except (RuntimeError, ValueError, OSError) as error:
                recording.update(state='failed', message=str(error))
        thread = threading.Thread(target=work, name='romancer-level-play', daemon=True)
        thread.start()
        if wait:
            thread.join()
        return self.summary()

    def level_stop(self, *, wait: bool = False) -> dict:
        """Put the map together from what was captured; runs in the background and reports through level_job."""
        with self.lock:
            rec = self.level_rec
            if rec is None:
                return self.summary()
            if self.recording and self.recording['state'] == 'running':
                raise ValueError('ROMancer is still playing. Stop it first.')
            self.level_rec = None
            self.level_job = {'state': 'running', 'done': 0, 'total': len(rec['scene_ids']), 'message': 'Putting the map together…',
                              'level_id': None}
        thread = threading.Thread(target=self._level_build, args=(rec,), name='romancer-level', daemon=True)
        thread.start()
        if wait:
            thread.join()
        return self.summary()

    def _level_frames(self, scene_ids, job=None) -> list:
        frames = []
        for number, scene_id in enumerate(scene_ids):
            meta = self.meta[scene_id]
            graphics = sg.SceneGraphics(self._scene(scene_id), self.system, self.rom, self.rgb[scene_id], meta['width'], meta['height'])
            graphics.layers()
            frames.append(lm.Frame(scene_id, graphics, meta['frame']))
            if job is not None:
                job['done'] = number + 1
        return frames

    def _level_build(self, rec: dict) -> None:
        job = self.level_job
        try:
            ids = [sid for sid in rec['scene_ids'] if sid in self.scenes]
            if len(ids) < 2:
                raise ValueError('Nothing was captured. Start recording, then play so that the screen scrolls.')
            frames = self._level_frames(ids, job)
            job['message'] = 'Laying the captures side by side…'
            planes = [p for p in lm.stitch(frames, self.system) if len(p.cells) >= MIN_PLANE_CELLS][:MAX_PLANES]
            if not planes:
                raise ValueError('ROMancer could not find a background that scrolled in what was captured.')
            keep = planes[0].cover()
            if len(keep) > MAX_LEVEL_SCENES:
                raise ValueError('This recording covers more of the game than one level map can hold. Record a shorter stretch.')
            index = {old: new for new, old in enumerate(keep)}
            stored = []
            for plane in planes:
                plane.windows = {index[n]: w for n, w in plane.windows.items() if n in index}
                for window in plane.windows.values():
                    for spot in list(window.cells.values()) + list(window.weak.values()) + list(window.faint.values()):
                        spot.frame = index[spot.frame]
                plane.assign()
            kept = [frames[n] for n in keep]
            job['message'] = 'Drawing the map with every layer…'
            screens = {n: lm.screen_picture(frame.graphics, self.system) for n, frame in enumerate(kept)}
            planes = [p for p in planes if len(p.cells) >= MIN_PLANE_CELLS]
            level = {'id': rec['id'], 'name': rec['name'], 'created': time.time(), 'rom_sha': self.rom_sha,
                     'scene_ids': [f.scene_id for f in kept], 'planes': []}
            for number, plane in enumerate(planes):
                left, top, right, bottom = plane.bounds()
                status = {}
                for (column, row), spot in plane.cells.items():
                    cell = kept[spot.frame].graphics.layers()[spot.layer].layer.cell(spot.x, spot.y)
                    status[(column, row)] = (cell.status[:1] or 'u')
                # the first map shows every layer the game drew; the others show their own layer alone
                plane.picture(kept, screens if number == 0 else None).save(self.store / 'levels' / f"{level['id']}-{number}.png")
                level['planes'].append({
                    'name': plane.name, 'px': plane.px, 'left': left, 'top': top, 'width': right - left, 'height': bottom - top,
                    'blocks': self._level_blocks(plane, kept, left, top),
                    'sections': [[a - left, b - left] for a, b in plane.sections],
                    'windows': {str(n): [w.section, w.across, w.down, w.first, w.last] for n, w in plane.windows.items()},
                    'cells': [[c - left, r - top, s.frame, s.layer, s.x, s.y, status[(c, r)]] for (c, r), s in sorted(plane.cells.items())]})
            with self.lock:
                old = next((other for other in self.levels if other['id'] == rec.get('extends')), None)
                if old is not None:         # the map it adds to is replaced by the one put together from everything
                    level['created'] = old.get('created', level['created'])
                    self._drop_level(old)
                self._level_save(level)
                self.levels.append(level)
                self.levels.sort(key=lambda other: other.get('created', 0))
                others = {sid for other in self.levels for sid in other['scene_ids']}
                drop = [sid for sid in ids if sid not in others]
            self._forget_many(drop)
            job.update(state='finished', level_id=level['id'], message=f"{level['name']} is ready: "
                       f"{level['planes'][0]['width']} by {level['planes'][0]['height']} cells from {len(kept)} captures.")
        except (ValueError, OSError, KeyError) as error:
            others = {sid for other in self.levels for sid in other['scene_ids']}     # a map being added to keeps its own
            self._forget_many([sid for sid in rec['scene_ids'] if sid in self.scenes and sid not in others])
            job.update(state='failed', message=str(error))

    def _level_blocks(self, plane, kept, left: int, top: int):
        """How the level is built from blocks, for snapping the brush: {'width', 'height', 'left', 'top'} in map cells counted
        from the map's corner, with 'larger' in the same form when the blocks are laid out by larger ones; None when it is not."""
        skip = gt.rom_skip(self.rom, self.system)
        groups: dict = {}
        for (column, row), spot in plane.cells.items():
            groups.setdefault((spot.frame, spot.layer), ((column - left, row - top), spot))
        counts: dict = {}
        for (column, row), spot in plane.cells.items():
            counts[(spot.frame, spot.layer)] = counts.get((spot.frame, spot.layer), 0) + 1
        votes: dict = {}
        richest = None
        for key, ((column, row), spot) in groups.items():
            layer = kept[key[0]].graphics.layers()[key[1]].layer
            grid = ll.find_grid(ll.cell_sources(layer, skip), layer.width, layer.height)
            if grid is None:
                continue
            shape = (grid.width, grid.height, (column - (spot.x - grid.left)) % grid.width, (row - (spot.y - grid.top)) % grid.height)
            votes[shape] = votes.get(shape, 0) + counts[key]
            kinds = len(set(grid.first.values()))
            if richest is None or kinds > richest[0]:
                richest = (kinds, grid, column, row, spot)
        if not votes:
            return None
        width, height, across, down = max(votes, key=votes.get)
        hint = {'width': width, 'height': height, 'left': across, 'top': down}
        _, grid, column, row, spot = richest
        if (grid.width, grid.height) == (width, height):
            table = ll.find_entries(self.rom, grid)
            larger = None
            if table is not None:
                larger = ll.find_grid(table.placed, max(at[0] for at in grid.first) + 1, max(at[1] for at in grid.first) + 1)
            if larger is not None and (larger.width, larger.height) == (table.width, table.height):
                wide, tall = larger.width * width, larger.height * height
                x0, y0 = grid.left + larger.left * width, grid.top + larger.top * height
                hint['larger'] = {'width': wide, 'height': tall, 'left': (column - (spot.x - x0)) % wide, 'top': (row - (spot.y - y0)) % tall}
        return hint

    def _forget_many(self, scene_ids) -> None:
        """Remove captures no level needs, in one go."""
        with self.lock:
            used = {c['scene_id'] for c in self._active()}
            gone = [sid for sid in scene_ids if sid in self.scenes and sid not in used]
            if not gone:
                return
            for sid in gone:
                for suffix in ('.scene', '.png'):
                    (self.store / 'scenes' / (sid + suffix)).unlink(missing_ok=True)
                for table in (self.scenes, self.meta, self.rgb):
                    table.pop(sid, None)
                for cache in (self._graphics_cache, self._editable, self._chr_used):
                    cache.pop(sid, None)
                for change in self.changes:
                    change['affected'].pop(sid, None)
            self._sources = {k: v for k, v in self._sources.items() if k[0] not in set(gone)}
            self.impact = type(self.impact)()
            for scene in self.scenes.values():
                self.impact.add(scene)
            self._views.clear()
            self._persist()

    def level_forget(self, level_id: str) -> dict:
        with self.lock:
            level = self._level(level_id)
            if any(c.get('level', {}).get('id') == level_id for c in self._active()):
                raise ValueError('A pending change was made on this level map. Undo that change first.')
            self._drop_level(level)
            others = {sid for other in self.levels for sid in other['scene_ids']}
        self._forget_many([sid for sid in level['scene_ids'] if sid not in others])
        return self.summary()

    def _drop_level(self, level: dict) -> None:
        """Take a map out of the store (its captures stay; the lock is held)."""
        self.levels.remove(level)
        for key in [k for k in self._level_cache if k == level['id'] or (isinstance(k, tuple) and k[0] == level['id'])]:
            self._level_cache.pop(key, None)
        for path in (self.store / 'levels').glob(level['id'] + '*'):
            path.unlink(missing_ok=True)

    # ---- the map

    def _level_plane(self, level: dict, number: int) -> lm.Plane:
        """The stored plane as a level_map.Plane (cells counted from its top left corner)."""
        key = (level['id'], number)
        plane = self._level_cache.get(key)
        if plane is None:
            if not 0 <= number < len(level['planes']):
                raise ValueError('That layer is not part of this level map.')
            stored = level['planes'][number]
            plane = lm.Plane(stored['name'], stored['px'])
            shift = stored['left'] * stored['px'], stored['top'] * stored['px']
            for n, (section, across, down, first, last) in stored['windows'].items():
                plane.windows[int(n)] = lm.Window(section, across - shift[0], down - shift[1], first, last, {})
            for column, row, frame, layer, x, y, _ in stored['cells']:
                plane.cells[(column, row)] = lm.Spot(frame, layer, x, y)
            self._level_cache[key] = plane
        return plane

    def level_view(self, level_id: str, plane: int = 0) -> dict:
        with self.lock:
            level = self._level(level_id)
            number = int(plane)
            if not 0 <= number < len(level['planes']):
                raise ValueError('That layer is not part of this level map.')
            stored = level['planes'][number]
            width, height = stored['width'], stored['height']
            frames = [-1] * (width * height)
            status = ['.'] * (width * height)
            for column, row, frame, _, _, _, letter in stored['cells']:
                frames[row * width + column] = frame
                status[row * width + column] = letter
            pending, after = [], None
            for change in self._active():
                mark = change.get('level')
                if not mark or mark['id'] != level_id or mark['plane'] != number or change.get('error'):
                    continue
                pending += [{'col': c, 'row': r, 'change': change['id']} for c, r in mark['places']]
            preview = self.preview
            shown = preview if preview and not preview.get('planning') and not preview.get('error') else None
            changes = ([shown] if shown else []) + [c for c in self.changes if c is not shown]
            ready = [c for c in changes if any(sid in level['scene_ids'] and r.get('state') == 'done' and r.get('pixels', 0) > 0
                                               for sid, r in c['affected'].items())]
            if ready:
                stamp = hashlib.sha1(repr([(c['id'], sorted((sid, r.get('key')) for sid, r in c['affected'].items()
                                                              if r.get('state') == 'done')) for c in ready]).encode()).hexdigest()[:16]
                after = f'levelafter:{level_id}:{number}:{stamp}'
            working = any(c['affected'] and any(r.get('state') == 'working' for r in c['affected'].values())
                          for c in changes) or bool(preview and preview.get('planning'))
            unshown = 0
            if after and shown and not working and shown.get('level', {}).get('id') == level_id and shown['level']['plane'] == number:
                # Did the places that were painted change on the map? A change that the replay confirmed in video
                # memory but that shows somewhere else is said plainly.
                differ = self._level_changed(level_id, number, after.rsplit(':', 1)[1])
                unshown = sum(1 for place in shown['level']['places'] if tuple(place) not in differ)
            layout = self._layout_grid(level) if number == 0 else None
            if layout:                      # a packed layout the profile can change: its places are not locked
                for place in layout['cells']:
                    at = place[1] * width + place[0]
                    if 0 <= at < len(status) and status[at] == 'u':
                        status[at] = 'p'
            return {'id': level_id, 'name': level['name'], 'plane': number, 'unshown': unshown,
                    'layout': {k: layout[k] for k in ('width', 'height', 'left', 'top')} if layout else None,
                    'planes': [{'index': k, 'name': p['name'], 'width': p['width'], 'height': p['height'], 'cell': p['px']}
                               for k, p in enumerate(level['planes'])],
                    'width': width, 'height': height, 'cell': stored['px'], 'sections': stored['sections'], 'blocks': stored.get('blocks'),
                    'image': f'level:{level_id}:{number}', 'after': after, 'frames': frames, 'status': ''.join(status),
                    'scenes': [{'id': sid, 'label': self._label(sid)} for sid in level['scene_ids']],
                    'pending': pending, 'working': working}

    # ---- what a game's level profile knows (romancer/level_profiles): enemies, items, secrets, block roles, length

    def _profile_context(self, level: dict):
        """(profile, [one entry per part of the map]) or None without a profile. Each part of the map (a section: a room
        the game drew in place of another) is its own part of the game, so each gets the profile's name for it and where
        that part's pixel 0, 0 is on the map, from the earliest capture of that part."""
        from . import level_profiles
        profile = level_profiles.profile_for(self.rom)
        if profile is None:
            return None
        plane = self._level_plane(level, 0)
        ordered = sorted(plane.windows.items(), key=lambda item: self.meta[level['scene_ids'][item[0]]]['frame'])
        found = {}          # section -> [(part, dx, dy)] for every capture the profile can place
        for number, window in ordered:
            ram = level_profiles.ram_of(self._scene(level['scene_ids'][number]).snapshot)
            where = profile.where(ram) if ram is not None else None
            if where is not None:
                found.setdefault(window.section, []).append((where['part'], window.across - where['x'], window.down - where['y']))
        parts = []
        for section, rows in found.items():
            # the part of the earliest capture, and the offset most of that part's captures agree on: one capture the
            # map placed off (a repeating forest, a restart) must not move every box in the section
            part = rows[0][0]
            offsets = [(dx, dy) for p, dx, dy in rows if p == part]
            dx, dy = max(set(offsets), key=offsets.count)
            columns = [c for (c, r), spot in plane.cells.items() if plane.windows.get(spot.frame) and plane.windows[spot.frame].section == section]
            parts.append({'section': section, 'part': part, 'name': profile.part_name(part), 'dx': dx, 'dy': dy,
                          'left': min(columns) * plane.px if columns else 0, 'right': (max(columns) + 1) * plane.px if columns else 0})
        return profile, parts

    def _profile_part(self, level: dict, part: dict):
        context = self._profile_context(level)
        if context is None:
            raise ValueError('ROMancer does not know the objects of this game yet.')
        profile, parts = context
        if not isinstance(part, dict) or not any(p['part'] == part for p in parts):
            raise ValueError('That part of the level is not on this map.')
        return profile, next(p for p in parts if p['part'] == part)

    def _layout_grid(self, level: dict):
        """Where the blocks of every packed layout the profile knows sit on the first map: {'width', 'height', 'left',
        'top'} (one block in map cells, and where the grid starts) and 'cells': {(column, row): (part, block column,
        block row)}; None when the game has no such layout."""
        try:
            context = self._profile_context(level)
        except Exception:
            return None
        if context is None:
            return None
        profile, parts = context
        px = level['planes'][0]['px']
        plane = self._level_plane(level, 0)
        out = None
        for part in parts:
            grid = profile.layout(part['part'])
            if not grid or grid['size'] % px:
                continue
            cells = grid['size'] // px
            left, top = part['dx'] + grid.get('left', 0), part['dy'] + grid.get('top', 0)
            if out is None:
                out = {'width': cells, 'height': cells, 'left': (left // px) % cells, 'top': (top // px) % cells, 'cells': {}}
            for (column, row), spot in plane.cells.items():
                window = plane.windows.get(spot.frame)
                if window is None or window.section != part['section']:
                    continue
                bx, by = (column * px - left) // grid['size'], (row * px - top) // grid['size']
                if 0 <= bx < grid['width'] and 0 <= by < grid['height']:
                    out['cells'][(column, row)] = (part['part'], bx, by)
        return out

    def propose_level_layout(self, level_id: str, cells) -> dict:
        """Copy whole blocks of a packed layout from one place on the first map to others ([{'col', 'row', 'from'}]);
        the profile packs the layout again, and the change is checked by replaying the recorded walk."""
        with self.lock:
            level = self._level(level_id)
            grid = self._layout_grid(level)
            if not grid:
                raise ValueError('ROMancer cannot change the layout of this level yet.')
            profile, _ = self._profile_context(level)
            wanted: dict = {}
            places = []
            part = None
            for item in cells:
                here, there = (int(item['col']), int(item['row'])), (int(item['from'][0]), int(item['from'][1]))
                target, source = grid['cells'].get(here), grid['cells'].get(there)
                if target is None or source is None:
                    raise ValueError('No capture showed that part of the level, so it cannot be painted.')
                if target[0] != source[0] or (part is not None and target[0] != part):
                    raise ValueError('Copy blocks within one part of the level at a time.')
                part = target[0]
                layout = profile.layout(part)
                wanted.setdefault((target[1], target[2]), layout['blocks'][source[2] * layout['width'] + source[1]])
                places.append(list(here))
            if part is None:
                raise ValueError('Paint something first.')
            layout = profile.layout(part)
            changes = [(bx, by, block) for (bx, by), block in sorted(wanted.items())
                       if layout['blocks'][by * layout['width'] + bx] != block]
            if not changes:
                raise ValueError('Those places already look like that. Paint a different picture first.')
            plan = profile.set_layout(part, changes)
            change = self.propose_writes(level['scene_ids'][0], plan['writes'], plan['title'], kind='level-object')
            stored = self._find(change['id'])
            stored['level'] = {'id': level_id, 'plane': 0, 'places': places, 'name': level['name']}
            stored['object_check'] = {'state': 'working', 'text': 'Playing the game from the start to see the new blocks…'}
            watch = plan['watch']
            watcher = lambda: profile.watcher(watch)
        threading.Thread(target=self._watch_change, args=(stored, level, watcher), name='romancer-layout-check', daemon=True).start()
        return self.change(change['id'])

    def level_objects(self, level_id: str) -> dict:
        """Everything the game's profile knows in the level, placed on the map, and what each map place is (solid,
        breakable, open) when the profile knows block roles."""
        with self.lock:
            level = self._level(level_id)
            context = self._profile_context(level)
            if context is None:
                return {'profile': None, 'objects': [], 'roles': ''}
            profile, parts = context
            stored = level['planes'][0]
            px = stored['px']
            objects = []
            for part in parts:
                for item in profile.objects(part['part']):
                    x, y = item['x'] + part['dx'], item['y'] + part['dy']
                    if part['left'] - px <= x < part['right'] + px:
                        objects.append({**item, 'map_x': x, 'map_y': y, 'part': part['part']})
            roles = ''
            if profile.tile_role(0) is not None:
                cells = ['.'] * (stored['width'] * stored['height'])
                plane = self._level_plane(level, 0)
                for (column, row), spot in plane.cells.items():
                    graphics = self._graphics(level['scene_ids'][spot.frame])
                    cell = graphics.layers()[spot.layer].layer.cell(spot.x, spot.y)
                    role = profile.tile_role((cell.tile_address % 0x1000) // 16)
                    cells[row * stored['width'] + column] = {'solid': 's', 'breakable': 'b'}.get(role, '.')
                roles = ''.join(cells)
            self._object_pictures(level, [o for o in objects if o['style'] in ('enemy', 'item')])
            return {'profile': profile.name, 'parts': [{k: part[k] for k in ('section', 'part', 'name')} for part in parts],
                    'objects': objects, 'roles': roles, 'choices': profile.choices(),
                    'resizable': any(profile.screens(part['part']) for part in parts),
                    'addable': any(profile.addable(part['part']) for part in parts)}

    def _object_pictures(self, level: dict, objects: list) -> None:
        """Give each object the picture the game draws for it: from a capture that shows that spot, the pixels where the
        real screen differs from the same screen drawn without sprites. Objects of a type never seen take the picture of
        one that was. Adds 'picture' (PNG as base64) and 'picture_box' ([left, top, width, height] on the map)."""
        import base64
        from PIL import Image, ImageChops, ImageFilter
        plane = self._level_plane(level, 0)
        shots = {}

        def shot(number):
            if number not in shots:
                graphics = self._graphics(level['scene_ids'][number])
                real = Image.new('RGB', (graphics.width, graphics.height))
                palette = [tuple(c) for c in graphics.reps] + [lm.EMPTY] * (256 - len(graphics.reps))
                real.putdata([palette[v] if v < len(palette) else lm.EMPTY for line in graphics.screen for v in line])
                shots[number] = (real, lm.screen_picture(graphics, self.system))
            return shots[number]
        # the player is on screen in nearly every capture at much the same spot; sprite pixels that show at the same
        # screen place in most captures are the player, not the object there
        numbers = sorted(plane.windows)
        common = None
        if len(numbers) >= 4:
            counts = None
            for number in numbers:
                real, plain = shot(number)
                diff = ImageChops.difference(real, plain).convert('L').point(lambda v: 1 if v else 0)
                counts = diff if counts is None else ImageChops.add(counts, diff)
            limit = max(2, len(numbers) // 2)
            common = counts.point(lambda v: 255 if v >= limit else 0).filter(ImageFilter.MaxFilter(5))
        by_type = {}
        for item in objects:
            left, top, width, height = item['map_x'] - 12, item['map_y'] - 32, 24, 32
            for number, window in sorted(plane.windows.items()):
                x0, y0 = left - window.across, top - window.down
                real, plain = shot(number)
                if x0 < 0 or y0 < window.first or x0 + width > real.width or y0 + height > window.last:
                    continue
                box = (x0, y0, x0 + width, y0 + height)
                piece, ground = real.crop(box), plain.crop(box)
                mask = ImageChops.difference(piece, ground).convert('L').point(lambda v: 255 if v else 0)
                if common is not None:
                    mask = ImageChops.subtract(mask, common.crop(box))
                if mask.getbbox() is None:
                    continue
                picture = piece.convert('RGBA')
                picture.putalpha(mask)
                out = io.BytesIO()
                picture.save(out, format='PNG')
                item['picture'] = base64.b64encode(out.getvalue()).decode()
                item['picture_box'] = [left, top, width, height]
                by_type.setdefault((item['style'], item.get('type')), item['picture'])
                break
        for item in objects:
            if 'picture' not in item and (item['style'], item.get('type')) in by_type:
                item['picture'] = by_type[(item['style'], item.get('type'))]
                item['picture_box'] = [item['map_x'] - 12, item['map_y'] - 32, 24, 32]
                item['picture_from_another'] = True

    def propose_level_edit(self, level_id: str, part: dict, object_id: str, values: dict = None, remove: bool = False) -> dict:
        """Change one thing the profile knows (an enemy, an item, a secret), checked by replaying the recorded walk."""
        with self.lock:
            level = self._level(level_id)
            profile, _ = self._profile_part(level, part)
            item = profile.find(part, str(object_id))
            values = dict(values or {})
            if remove and not item.get('remove'):
                raise ValueError('That cannot be removed.')
            for field in item.get('fields', []):
                if field['key'] in values:
                    values[field['key']] = profile.pick(field, profile.choices(), values[field['key']])['value']
            plan = profile.edit(part, str(object_id), values, bool(remove))
            if not plan['writes']:
                raise ValueError('That is how the game already has it.')
            change = self.propose_writes(level['scene_ids'][0], plan['writes'], plan['title'], kind='level-object')
            stored = self._find(change['id'])
            stored['object_check'] = {'state': 'working', 'text': 'Playing the game from the start to see the change happen…'}
            watch = plan['watch']
            watcher = lambda: profile.watcher(watch)
        threading.Thread(target=self._watch_change, args=(stored, level, watcher), name='romancer-object-check', daemon=True).start()
        return self.change(change['id'])

    def _part_at(self, parts: list, x: float) -> dict:
        return min(parts, key=lambda p: 0 if p['left'] <= x < p['right'] else min(abs(x - p['left']), abs(x - p['right'])))

    def level_add_at(self, level_id: str, x: float, y: float) -> dict:
        """What can be added at a map spot: the part of the game it is in, the spot in that part's pixels, and the
        kinds the profile offers there."""
        with self.lock:
            level = self._level(level_id)
            context = self._profile_context(level)
            if context is None:
                raise ValueError('ROMancer does not know the objects of this game yet.')
            profile, parts = context
            part = self._part_at(parts, float(x))
            options = profile.addable(part['part'])
            if not options:
                raise ValueError('ROMancer cannot add new things to this part of the level yet.')
            return {'part': part['part'], 'name': part['name'], 'x': int(round(float(x) - part['dx'])),
                    'y': int(round(float(y) - part['dy'])), 'map_x': float(x), 'map_y': float(y),
                    'options': options, 'choices': profile.choices()}

    def propose_level_add(self, level_id: str, part: dict, kind: str, x: int, y: int, values: dict = None) -> dict:
        """Add a new enemy, item or secret at a spot in a part of the level, checked by replaying the recorded walk."""
        with self.lock:
            level = self._level(level_id)
            profile, _ = self._profile_part(level, part)
            option = next((o for o in profile.addable(part) if o['kind'] == kind), None)
            if option is None:
                raise ValueError('That cannot be added here.')
            values = dict(values or {})
            for field in option.get('fields', []):
                if field['key'] in values:
                    values[field['key']] = profile.pick(field, profile.choices(), values[field['key']])['value']
            plan = profile.add(part, kind, int(x), int(y), values)
            if not plan['writes']:
                raise ValueError('That is how the game already has it.')
            change = self.propose_writes(level['scene_ids'][0], plan['writes'], plan['title'], kind='level-object')
            stored = self._find(change['id'])
            stored['object_check'] = {'state': 'working', 'text': 'Playing the game from the start to see the new one appear…'}
            watch = plan['watch']
            watcher = lambda: profile.watcher(watch)
        threading.Thread(target=self._watch_change, args=(stored, level, watcher), name='romancer-object-check', daemon=True).start()
        return self.change(change['id'])

    def _watch_change(self, change: dict, level: dict, watcher) -> None:
        """Replay the recorded walk from the level's first checkpoint with the change (and first without it, when the
        watcher compares) and let the watcher look at the game every few frames."""
        from array import array
        import zlib
        from . import edit_session as es
        from .level_profiles import ram_of
        make = watcher if callable(watcher) and not hasattr(watcher, 'see') else (lambda: watcher)
        firsts = {}             # one walk per recording that went into the map (a map can be added to)
        for sid in level['scene_ids']:
            firsts.setdefault(self.meta[sid]['run'], sid)
        result = None
        path = self.store / 'work' / f'watch-{change["id"]}.bin'
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self._rom_with([change]))
            for walk, first in firsts.items():
                watcher_now = make()
                meta = self.meta[first]
                run_dir = self.store / 'runs' / walk
                inputs = array('H')
                inputs.frombytes((run_dir / 'inputs.bin').read_bytes())
                start = min(meta['checkpoints'])
                state = zlib.decompress((run_dir / f'{start}.st').read_bytes())
                same_run = [self.meta[s]['frame'] for s in level['scene_ids'] if self.meta[s]['run'] == walk]
                end = len(inputs) if watcher_now.compare else min(len(inputs), max(same_run) + 120)
                runs = ([('original', self.rom_path)] if watcher_now.compare else []) + [('changed', path)]
                for run, rom_path in runs:
                    fe = es._frontend(self._cfg(), rom_path)
                    try:
                        if int(fe.lib.retro_serialize_size()) <= 0:
                            fe.run_frame([])
                        fe.unserialize(state)
                        session = es._Session(fe, checkpoint_every=10 ** 9)
                        session.frame = start
                        frame = start
                        while frame < end:
                            session.run(watcher_now.every, lambda f: es._names(inputs[f]) if f < len(inputs) else ())
                            frame += watcher_now.every
                            ram = ram_of(session.snapshot())
                            if ram is not None and watcher_now.see(ram, frame, run):
                                break
                    finally:
                        es._close(fe)
                result = watcher_now.result()
                if result.get('state') != 'warn' or len(firsts) == 1:
                    break
        except Exception as error:      # shown to the user; the editor keeps working
            result = {'state': 'warn', 'text': f'The change could not be watched in the game: {error}'}
        finally:
            path.unlink(missing_ok=True)
        change['object_check'] = result

    def level_screen_at(self, level_id: str, x: float) -> dict:
        """Which screen of which part of the level a map spot is on (for making a part longer or shorter)."""
        with self.lock:
            level = self._level(level_id)
            context = self._profile_context(level)
            if context is None:
                raise ValueError('ROMancer does not know how long the parts of this game are yet.')
            profile, parts = context
            x = float(x)
            part = self._part_at(parts, x)
            screens = profile.screens(part['part'])
            if not screens:
                raise ValueError('ROMancer cannot change the length of this part yet.')
            screen = max(0, min(screens['count'] - 1, int((x - part['dx']) // 256)))
            return {'part': part['part'], 'name': part['name'], 'screen': screen, 'screens': screens['count'],
                    'map_left': part['dx'] + screen * 256, 'most': screens['most']}

    def propose_level_length(self, level_id: str, part: dict, screen: int, delta: int) -> dict:
        """Remove screens from a part of the level, or repeat one; everything after moves along with it."""
        with self.lock:
            level = self._level(level_id)
            profile, _ = self._profile_part(level, part)
            if any(c.get('length') for c in self._active()):
                raise ValueError('ROMancer changes the length of one part of the level at a time. Keep or cancel the other length change, save, and then make the next one.')
            screen, delta = int(screen), int(delta)
            before = profile.screens(part)['count']
            plan = profile.resize(part, screen, delta)
            count = abs(delta)
            title = (f'Screen {screen + 1} repeated {count} more time{"s" if count > 1 else ""} ({before} to {before + delta} screens)' if delta > 0 else
                     f'{count} screen{"s" if count > 1 else ""} removed from screen {screen + 1} ({before} to {before + delta} screens)')
            change = self.propose_writes(level['scene_ids'][0], plan['writes'], title, kind='level-object')
            stored = self._find(change['id'])
            stored['length'] = True
            stored['object_check'] = {'state': 'working', 'text': 'Playing the game from the start on the old and the new length…'}
            watch = plan['watch']
            watcher = lambda: profile.watcher(watch)
        threading.Thread(target=self._watch_change, args=(stored, level, watcher), name='romancer-length-check', daemon=True).start()
        return self.change(change['id'])

    def level_capture_at(self, level: dict, x: float, y: float) -> str:
        """The capture that shows this map spot nearest the middle of its screen (the earliest such, on a tie)."""
        plane = self._level_plane(level, 0)
        best = None
        for number, window in plane.windows.items():
            sid = level['scene_ids'][number]
            meta = self.meta[sid]
            width, height = meta['width'], meta['height']
            if not (window.across <= x < window.across + width and window.down <= y < window.down + height):
                continue
            score = (abs(x - (window.across + width / 2)), meta['frame'])
            if best is None or score < best[0]:
                best = (score, sid)
        if best is None:
            distance = lambda item: abs(x - item[1].across) + abs(y - item[1].down)
            number = min(plane.windows.items(), key=distance)[0]
            return level['scene_ids'][number]
        return best[1]

    def level_play_from(self, level_id: str, x: float, y: float) -> dict:
        """Start the live game with the kept changes at the recorded moment nearest this map spot."""
        busy = self._live_busy()
        if busy:
            raise ValueError(busy['message'])
        with self.lock:
            level = self._level(level_id)
            sid = self.level_capture_at(level, float(x), float(y))
            meta = dict(self.meta[sid])
            if not meta.get('run') or not (self.store / 'runs' / meta['run'] / 'inputs.bin').exists():
                raise ValueError('The recording for that part of the map is gone, so the game cannot start there.')
            rom = self._rom_with(self.changes)
            path = self.store / 'work' / 'playtest.bin'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(rom)
            kept = len(self.changes)
        label = f'with {kept} change{"s" if kept != 1 else ""}' if kept else 'with no changes yet'
        with self.host_lock:
            self._start_playtest(path, meta, label)
        return {'playtest': self.live.get('playtest'), 'frame': meta['frame'], 'scene_id': sid}

    COMPARE_FRAMES = 1200       # 20 seconds of play
    COMPARE_EVERY = 3           # every third frame goes in the picture (20 pictures a second)

    def level_compare(self, level_id: str, x: float = None, y: float = None) -> dict:
        """Start (with a map spot) or look at a before-and-after replay: the recorded walk played on the original game and
        on the game with the kept changes, from that spot for 20 seconds, side by side in one animated picture."""
        with self.lock:
            level = self._level(level_id)
            job = self._compares.get(level_id) if hasattr(self, '_compares') else None
            if x is None:
                return {'compare': self._compare_view(job)}
            if job and job['state'] == 'running':
                return {'compare': self._compare_view(job)}
            if not self.changes:
                raise ValueError('Keep a change first; then the replay shows the game before and after it.')
            sid = self.level_capture_at(level, float(x), float(y))
            first = self.meta[level['scene_ids'][0]]
            meta = self.meta[sid]
            if meta.get('run') != first.get('run') or not (self.store / 'runs' / meta['run'] / 'inputs.bin').exists():
                raise ValueError('The recording for that part of the map is gone, so it cannot be replayed.')
            job = {'id': uuid.uuid4().hex[:12], 'state': 'running', 'done': 0, 'total': self.COMPARE_FRAMES * 2,
                   'kept': len(self.changes), 'message': 'Replaying the original game…'}
            if not hasattr(self, '_compares'):
                self._compares = {}
            self._compares[level_id] = job
            rom = self._rom_with(self.changes)
            target = max(first['frame'], meta['frame'] - 60)
        threading.Thread(target=self._compare_worker, args=(job, first, target, rom, level['name']), name='romancer-compare', daemon=True).start()
        return {'compare': self._compare_view(job)}

    def level_compare_file(self, level_id: str) -> dict:
        job = getattr(self, '_compares', {}).get(level_id)
        if not job or job['state'] != 'finished':
            raise ValueError('The before-and-after replay is not ready yet.')
        return {'gif': job['path'].read_bytes(), 'name': job['name']}

    @staticmethod
    def _compare_view(job):
        if not job:
            return None
        return {k: job[k] for k in ('id', 'state', 'done', 'total', 'message', 'kept', 'differs', 'width', 'height', 'seconds') if k in job}

    def _compare_worker(self, job: dict, first: dict, target: int, rom: bytes, name: str) -> None:
        from array import array
        import io
        import zlib
        from PIL import Image, ImageDraw
        from . import edit_session as es
        try:
            run_dir = self.store / 'runs' / first['run']
            inputs = array('H')
            inputs.frombytes((run_dir / 'inputs.bin').read_bytes())
            start = min(first['checkpoints'])
            state = zlib.decompress((run_dir / f'{start}.st').read_bytes())
            end = min(len(inputs), target + self.COMPARE_FRAMES)
            work = self.store / 'work'
            work.mkdir(parents=True, exist_ok=True)
            changed = work / f'compare-{job["id"]}.bin'
            changed.write_bytes(rom)
            runs = []
            for number, path in enumerate((self.rom_path, changed)):
                job['message'] = 'Replaying the original game…' if number == 0 else 'Replaying the game with your changes…'
                fe = es._frontend(self._cfg(), path)
                pictures = []
                try:
                    if int(fe.lib.retro_serialize_size()) <= 0:
                        fe.run_frame([])
                    fe.unserialize(state)
                    session = es._Session(fe, checkpoint_every=10 ** 9)
                    session.frame = start
                    if target > start:
                        session.run(target - start, lambda f: es._names(inputs[f]) if f < len(inputs) else ())
                    for at in range(target, end, self.COMPARE_EVERY):
                        session.run(self.COMPARE_EVERY, lambda f: es._names(inputs[f]) if f < len(inputs) else ())
                        frame = fe.last_frame
                        pictures.append((frame.width, frame.height, bytes(frame.rgb)))
                        job['done'] = number * self.COMPARE_FRAMES + (at - target)
                finally:
                    es._close(fe)
                runs.append(pictures)
            changed.unlink(missing_ok=True)
            job['message'] = 'Making the picture…'
            differs = None
            frames = []
            count = min(len(runs[0]), len(runs[1]))
            for n in range(count):
                (w, h, before), (_, _, after) = runs[0][n], runs[1][n]
                if differs is None and before != after:
                    differs = round(n * self.COMPARE_EVERY / 60, 1)
                sheet = Image.new('RGB', (w * 2 + 4, h + 14), (16, 20, 24))
                sheet.paste(Image.frombytes('RGB', (w, h), before), (0, 14))
                sheet.paste(Image.frombytes('RGB', (w, h), after), (w + 4, 14))
                draw = ImageDraw.Draw(sheet)
                draw.text((4, 2), 'Before', fill=(230, 230, 230))
                draw.text((w + 8, 2), 'After', fill=(120, 230, 180))
                frames.append(sheet.convert('P', palette=Image.Palette.ADAPTIVE, colors=128))
            if not frames:
                raise ValueError('The recording ends before that spot, so there was nothing to replay.')
            out = io.BytesIO()
            frames[0].save(out, 'GIF', save_all=True, append_images=frames[1:], duration=int(1000 * self.COMPARE_EVERY / 60), loop=0, optimize=False)
            path = work / f'compare-{job["id"]}.gif'
            path.write_bytes(out.getvalue())
            safe = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in name).strip() or 'level'
            job.update(state='finished', path=path, name=f'{safe} before and after.gif', differs=differs,
                       width=frames[0].width, height=frames[0].height, seconds=round(count * self.COMPARE_EVERY / 60, 1), done=job['total'],
                       message=('The two games look different from the first moment.' if differs == 0 else
                                f'The two games first look different {differs} seconds in.' if differs is not None else
                                'The two games look the same the whole way. Your changes may be somewhere this walk does not show.'))
        except Exception as error:      # shown to the user; the editor keeps working
            job.update(state='failed', message=f'The replay could not be made: {error}')

    def level_place(self, level_id: str, plane: int, col: int, row: int) -> dict:
        """Which scene, layer and cell a place on the map is, for opening it in the scene editors."""
        with self.lock:
            level = self._level(level_id)
            spot = self._level_plane(level, int(plane)).cells.get((int(col), int(row)))
            if spot is None:
                raise ValueError('No capture showed that part of the level.')
            return {'scene_id': level['scene_ids'][spot.frame], 'layer': spot.layer, 'x': spot.x, 'y': spot.y}

    def level_image(self, level_id: str, plane: int, stamp: str = '') -> bytes:
        """PNG of the map as recorded, or (with a stamp from level_view) with every pending change drawn in."""
        with self.lock:
            level = self._level(level_id)
            number = int(plane)
            path = self.store / 'levels' / f'{level_id}-{number}.png'
            if not path.is_file():
                raise ValueError('That picture is no longer stored. Record the level again.')
            if not stamp:
                return path.read_bytes()
            cached = self.store / 'levels' / f'{level_id}-{number}-after-{stamp}.png'
            if cached.is_file():
                return cached.read_bytes()
            from PIL import Image
            picture = Image.open(path).convert('RGB')
            mapped = self._level_plane(level, number)
            shots = {}
            for frame, scene_id in enumerate(level['scene_ids']):
                look = self._look(scene_id)
                if look.get('state') == 'same' or not look.get('image', '').startswith('render:'):
                    continue
                after = self.store / 'renders' / (look['image'].split(':', 1)[1] + '.png')
                if not after.is_file():
                    continue
                meta = self.meta[scene_id]
                rgb = Image.open(after).convert('RGB')
                if rgb.size != (meta['width'], meta['height']):
                    continue
                shots[frame] = (meta['width'], meta['height'], self.rgb[scene_id], rgb.tobytes())
            places = mapped.changed(picture, shots)
            for old in (self.store / 'levels').glob(f'{level_id}-{number}-after-*'):
                old.unlink(missing_ok=True)
            out = io.BytesIO()
            picture.save(out, 'PNG')
            cached.write_bytes(out.getvalue())
            cached.with_suffix('.json').write_text(json.dumps(places))
            return out.getvalue()

    def _level_changed(self, level_id: str, number: int, stamp: str) -> set:
        """Places of the map that look different with the pending changes drawn in."""
        self.level_image(level_id, number, stamp)
        try:
            return {tuple(place) for place in json.loads((self.store / 'levels' / f'{level_id}-{number}-after-{stamp}.json').read_text())}
        except (OSError, ValueError):
            return set()

    def export_level(self, level_id: str, plane: int = 0, edited: bool = False) -> dict:
        with self.lock:
            level = self._level(level_id)
            view = self.level_view(level_id, plane)
            stamp = view['after'].rsplit(':', 1)[1] if edited and view['after'] else ''
            name = ''.join(ch if ch.isalnum() else '-' for ch in level['name']).strip('-').lower() or 'level'
            return {'png': self.level_image(level_id, plane, stamp), 'name': f"{name}{'-edited' if stamp else ''}.png",
                    'width': view['width'] * view['cell'], 'height': view['height'] * view['cell']}

    # ---- changes

    def _level_across(self, level: dict, shown: int, other: int, place: tuple):
        """The place in another layer's map that the game drew over a place of the map being shown, or None.

        Layers scroll at their own speeds, so the same spot of the level is at
        different places of their maps. The capture that showed the place says
        where both layers sat on the screen at that moment.
        """
        here, there = self._level_plane(level, shown), self._level_plane(level, other)
        spot = here.cells.get(place)
        if spot is None:
            return None
        mine, theirs = here.windows.get(spot.frame), there.windows.get(spot.frame)
        if mine is None or theirs is None:
            return None
        x, y = place[0] * here.px - mine.across, place[1] * here.px - mine.down
        return ((x + theirs.across) // there.px, (y + theirs.down) // there.px)

    def propose_level(self, level_id: str, plane: int, cells, layers=None) -> dict:
        """Plan copying the picture of one place on the map to others: [{'col', 'row', 'from': [col, row]}].

        Places are given on the map of `plane`. `layers` names the layers to
        change (indices into the level's planes); None means that plane only.
        In another layer the place that the game drew over each place is
        painted, where that layer was captured there.
        """
        with self.lock:
            self._require_core()
            level = self._level(level_id)
            number = int(plane)
            mapped = self._level_plane(level, number)
            groups: dict = {}
            places, seen = [], set()
            nes = self.system == 'nes'
            wanted = [number] if layers is None else sorted({int(k) for k in layers})
            if not wanted or any(not 0 <= k < len(level['planes']) for k in wanted):
                raise ValueError('Choose which layer to paint on.')
            jobs = []
            for item in cells:
                here, there = (int(item['col']), int(item['row'])), (int(item['from'][0]), int(item['from'][1]))
                for k in wanted:
                    if k == number:
                        jobs.append((k, here, here, there))
                        continue
                    to, origin = self._level_across(level, number, k, here), self._level_across(level, number, k, there)
                    if to is not None and origin is not None and to != origin:
                        jobs.append((k, here, to, origin))
            for k, shown, (col, row), origin in jobs:
                if (k, col, row) in seen:
                    continue
                seen.add((k, col, row))
                mapped = self._level_plane(level, k)
                try:
                    target = mapped.cells.get((col, row))
                    source = mapped.cells.get(origin)
                    if target is None or source is None:
                        raise ValueError('No capture showed that part of the level, so it cannot be painted.')
                    t_scene, s_scene = level['scene_ids'][target.frame], level['scene_ids'][source.frame]
                    t_graphics = self._graphics(t_scene)
                    t_view = t_graphics.layers()[target.layer]
                    now = t_view.layer.cell(target.x, target.y)
                    s_graphics = self._graphics(s_scene)
                    s_view = s_graphics.layers()[source.layer]
                    want = s_view.layer.cell(source.x, source.y)
                    fmt = s_view.layer.tile_format
                    pixels = s_graphics.tile_pixels(s_view.layer.tile_domain, want.tile_address, fmt)
                    address = None
                    if t_view.layer.tile_format == fmt:
                        if t_graphics.tile_pixels(t_view.layer.tile_domain, want.tile_address, fmt) == pixels:
                            address = want.tile_address
                        else:               # the same picture may be loaded somewhere else at that point of the level
                            for other in t_view.layer.cells:
                                if t_graphics.tile_pixels(t_view.layer.tile_domain, other.tile_address, fmt) == pixels:
                                    address = other.tile_address
                                    break
                    if address is None:
                        raise ValueError('The picture you chose is not loaded at that point of the level, so the game cannot '
                                         'show it there. Choose a picture from nearer that place.')
                    change = {'layer': target.layer, 'x': target.x, 'y': target.y,
                              'tile': sg.tile_id(t_view.layer.tile_domain, address, fmt), 'scene_id': t_scene,
                              'like': {'scene_id': s_scene, 'layer': source.layer, 'x': source.x, 'y': source.y}}
                    if len(now.addresses) > 1 and not nes:
                        change.update(hflip=want.hflip, vflip=want.vflip, line=want.palette)
                    if now.status == 'unknown':
                        raise ValueError(sg.CELL_REASONS['unknown'])
                    sg.hardware_tile(t_view, now, t_view.layer.tile_domain, address, fmt)
                    if (now.tile_address, now.hflip, now.vflip, now.palette) == (address, change.get('hflip', now.hflip),
                                                                               change.get('vflip', now.vflip), change.get('line', now.palette)):
                        raise _Same()
                    change['from'] = {'tile': sg.tile_id(t_view.layer.tile_domain, now.tile_address, t_view.layer.tile_format),
                                      'hflip': now.hflip, 'vflip': now.vflip, 'line': now.palette}
                    groups.setdefault(t_scene, []).append(change)
                    if list(shown) not in places:
                        places.append(list(shown))
                except _Same:
                    continue
                except ValueError:
                    if k == number or len(wanted) == 1:
                        raise               # the layer being looked at: say why
                    continue                # another layer does not have that picture there: leave that layer as it is
            if not places:
                raise ValueError('Those places already look like that. Paint a different picture first.')
            if len(places) > MAX_LEVEL_CELLS:
                raise ValueError(f'That is too many places for one change. Paint up to {MAX_LEVEL_CELLS} at a time.')
            order = sorted(groups, key=lambda sid: -len(groups[sid]))
            key = 'level:' + level_id + ':' + hashlib.sha1(repr(sorted(map(tuple, places))).encode()).hexdigest()[:16]
            offsets = set()
            for sid in order:
                layers = self._graphics(sid).layers()
                for c in groups[sid]:
                    offsets.update(s['offset'] for s in layers[c['layer']].layer.cell(c['x'], c['y']).sources if s)
            count = len(places)
            change = {'kind': 'background', 'key': key, 'scene_id': order[0],
                      'title': f"{count} place{'s' if count != 1 else ''} in {level['name']}",
                      'swatch': None, 'from_rgb': None, 'to_rgb': None, 'writes': [], 'scope': 'all',
                      'cells': [c for sid in order for c in groups[sid]], 'extra_scenes': list(level['scene_ids']),
                      'level': {'id': level_id, 'plane': number, 'places': places, 'name': level['name']},
                      'planning': True, 'plan_task': 'graphics', 'expect_offsets': sorted(offsets) or None,
                      'plan_job': {'what': 'level', 'scene_id': order[0], 'avoid': self._avoid(key),
                                   'groups': [{'scene_id': sid, 'cells': groups[sid]} for sid in order]}}
            return self._propose(change)

    def _planned_level(self, change: dict, result: dict) -> None:
        """After scene_graphics planned a level change: the scene it was first confirmed in, and what was left out."""
        if result.get('scene_id'):
            change['scene_id'] = result['scene_id']
        skipped = result.get('skipped') or []
        if skipped:
            gone = {s['scene_id'] for s in skipped}
            left = sum(s['cells'] for s in skipped)
            change['cells'] = [c for c in change['cells'] if c.get('scene_id') not in gone]
            reasons = list(dict.fromkeys(s['reason'] for s in skipped))
            change['notes'] = list(change.get('notes', [])) + [
                f"{left} place{'s were' if left != 1 else ' was'} left out: " + ' '.join(reasons)]
