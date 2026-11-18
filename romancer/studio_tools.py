"""Source-bound studio endpoints, using existing reviewed integrity plans."""
from pathlib import Path
import base64,hashlib,io,tempfile,wave,time,threading
from collections import OrderedDict
from . import workbench_projects as projects
from .workbench_files import read_bounded


class StudioTools:

    def __init__(self, api):
        self.api = api
        self.searches = OrderedDict()
        self.search_lock = threading.RLock()

    def routes(self):
        return {'levels.presets': ('project_id artifact_id', self.level_presets), 'levels.preset': ('project_id artifact_id preset_id', self.level_preset), 'studio.example': ('', self.example), 'resources.relationships': ('project_id artifact_id', self.relationships), 'resources.explain': ('project_id artifact_id offset', self.explain), 'values.start': ('project_id artifact_id region offset length width endian signed target', self.values_start), 'values.narrow': ('project_id artifact_id search_id relation target', self.values_narrow), 'video.inspect': ('project_id artifact_id offset length codec', self.video_inspect), 'studio.definition': ('project_id artifact_id kind definition', self.definition), 'levels.inspect': ('project_id artifact_id definition', self.levels_inspect), 'levels.plan': ('project_id artifact_id definition document_id changes', self.levels_plan), 'sound.system': ('project_id artifact_id', self.sound_system), 'sound.inspect': ('project_id artifact_id definition', self.sound_inspect), 'sound.plan': ('project_id artifact_id definition document_id changes', self.sound_plan), 'sound.preview': ('project_id artifact_id definition kind resource_id changes', self.sound_preview), 'sound.export': ('project_id artifact_id definition kind resource_id changes', self.sound_export), 'sound.capture': ('project_id artifact_id frames', self.sound_capture)}

    def relationships(self, p, c):
        from .studio_discovery import resource_relationships
        _, row, raw = self.source(p, c, allow_sms=True)
        return resource_relationships(raw, row.get('descriptors', {}), row['sha256'])

    def explain(self, p, c):
        from .source_information import explain_bytes
        from .research_tools import notes_for, note_summaries
        _, row, raw = self.source(p, c, allow_sms=True)
        result = explain_bytes(raw, row.get('descriptors', {}), row['sha256'], p['offset'])
        result['research_notes'] = note_summaries([n for n in notes_for(row) if n['offset'] <= p['offset'] < n['offset'] + n['length']])
        return result

    def observe(self, p, c, region, offset, length):
        project, row, _ = self.api.source(p)
        if row.get('system_id') not in ('nes', 'snes', 'genesis', 'gb', 'gbc', 'sms'):
            raise ValueError('select a supported cartridge source')
        if self.api.runtime.session_selection(project) != {'id': row['artifact_id'], 'sha256': row['sha256']}:
            raise ValueError('load the selected source in Playtest first')
        packet = self.api._memory_snapshot({'project_id': p['project_id'], 'region': region, 'offset': offset, 'length': length}, c)
        if packet.get('game_sha256') != row['sha256'] or any((packet.get(k) != v for k, v in [('region', region), ('offset', offset), ('length', length)])):
            raise ValueError('memory observation source or range differs')
        return packet

    def search_response(self, ident, search):
        s = search['snapshot']
        raw = bytes.fromhex(s['raw_hex'])
        matches = search['matches'] or [{'offset': o, 'previous': None, 'value': int.from_bytes(raw[o - s['offset']:o - s['offset'] + search['width']], search['endian'], signed=search['signed'])} for o in search['offsets'][:100]]
        return {'ok': True, 'search_id': ident, 'total': len(search['offsets']), 'matches': matches[:100], 'source_sha256': s['game_sha256'], 'region': s['region'], 'offset': s['offset'], 'length': s['length'], 'width': search['width'], 'endian': search['endian'], 'signed': search['signed'], 'sequence': s['sequence'], 'rom_location_known': False, 'memory_written': False, 'scope': 'native_ram_candidates'}

    def prune_searches(self):
        for ident, row in list(self.searches.items()):
            if time.monotonic() - row['touched'] > 300:
                del self.searches[ident]

    def values_start(self, p, c):
        from .value_search import begin_search
        import uuid
        with self.search_lock, self.api.runtime.lock:
            self.prune_searches()
            packet = self.observe(p, c, p['region'], p['offset'], p['length'])
            search = begin_search(packet, p['width'], p['endian'], p['signed'], p['target'])
            ident = uuid.uuid4().hex
            self.searches[ident] = {'selection': (p['project_id'], p['artifact_id']), 'search': search, 'touched': time.monotonic()}
            while len(self.searches) > 32:
                self.searches.popitem(last=False)
            return self.search_response(ident, search)

    def values_narrow(self, p, c):
        from .value_search import narrow_search
        with self.search_lock, self.api.runtime.lock:
            self.prune_searches()
            owned = self.searches.get(p['search_id'])
            if not owned or owned['selection'] != (p['project_id'], p['artifact_id']):
                raise ValueError('search expired or belongs to another source; start a new search')
            old = owned['search']['snapshot']
            packet = self.observe(p, c, old['region'], old['offset'], old['length'])
            search = narrow_search(owned['search'], packet, p['relation'], p['target'])
            owned.update(search=search, touched=time.monotonic())
            self.searches.move_to_end(p['search_id'])
            return self.search_response(p['search_id'], search)

    def video_inspect(self, p, c):
        from .asset_codecs import cell_size, decode_cell
        size = cell_size(p['codec'], 8, 8)
        with self.api.runtime.lock:
            packet = self.observe(p, c, 3, p['offset'], p['length'])
        raw = bytes.fromhex(packet['raw_hex'])
        if len(raw) % size:
            raise ValueError('read a whole number of tiles for the chosen codec')
        tiles = [decode_cell(raw[i:i + size], codec=p['codec'], width=8, height=8) for i in range(0, len(raw), size)]
        return {'ok': True, 'source_sha256': packet['game_sha256'], 'observation': packet, 'codec': p['codec'], 'tiles': tiles, 'rom_location_known': False, 'palette_known': False, 'scope': 'available_video_memory_tiles'}

    def source(self, p, c, *, allow_sms=True):
        project, row, path = self.api.source(p)
        if row.get('system_id') not in ('nes', 'snes', 'genesis', 'gb', 'gbc') and (not (allow_sms and row.get('system_id') == 'sms')):
            raise ValueError('studio editing requires a supported cartridge source')
        raw = read_bounded(path, 64 * 1024 ** 2, row, cancelled=c)
        return (project, row, raw)

    def definition(self, p, c):
        project, row, raw = self.source(p, c)
        kind = p['kind']
        if kind == 'levels':
            from .level_design import inspect_level
            inspect_level(raw, p['definition'], row['sha256'])
        elif kind == 'sound':
            from .sound_studio import inspect_sound
            inspect_sound(raw, p['definition'], row['sha256'])
        else:
            raise ValueError('choose a level or sound definition')
        if c():
            raise KeyboardInterrupt
        with projects.locked(project) as value:
            owned = next((a for a in value['sources'] + value['builds'] if a['artifact_id'] == row['artifact_id']))
            owned.setdefault('descriptors', {})[kind] = p['definition']
            projects.write_json(project / 'project.json', value)
        return {'ok': True, 'status': 'SAVED', 'source_sha256': row['sha256'], 'kind': kind}

    def level_presets(self,p,c):
        from .level_presets import catalog
        project,row,path=self.api.source(p)
        return catalog(project,row,path,cancelled=c)

    def level_preset(self,p,c):
        from .level_presets import definition
        project,row,path=self.api.source(p)
        return definition(project,row,path,p['preset_id'],cancelled=c)

    def levels_inspect(self, p, c):
        from .adapters.registry import adapter_for
        _, row, raw = self.source(p, c)
        return adapter_for('levels',raw,p['definition'],row['sha256']).inspect()

    def levels_plan(self, p, c):
        from .adapters.registry import adapter_for
        _, row, raw = self.source(p, c)
        result = adapter_for('levels',raw,p['definition'],row['sha256']).plan(p['document_id'],p['changes'])
        return {**self.plan(p, result['edits'], c), 'affected_rooms': result['affected_rooms'], 'document_id': result['document_id'],
                'adapter_id':result['adapter_id'],'adapter_sha256':result['adapter_sha256'],'resource_impact':result['resource_impact'],
                **({'affected_cells':result['affected_cells']}if 'affected_cells'in result else {})}

    def plan(self, p, edits, c):
        merged = []
        chunks = [{'offset': edit['offset'] + i // 2, 'before': edit['before'][i:i + 8192], 'after': edit['after'][i:i + 8192]} for edit in edits for i in range(0, len(edit['before']), 8192) if edit['before'][i:i + 8192] != edit['after'][i:i + 8192]]
        for edit in sorted(chunks, key=lambda e: e['offset']):
            if merged and merged[-1]['offset'] + len(merged[-1]['before']) // 2 == edit['offset'] and ((len(merged[-1]['before']) + len(edit['before'])) // 2 <= 4096):
                merged[-1]['before'] += edit['before']
                merged[-1]['after'] += edit['after']
            else:
                merged.append(dict(edit))
        if c():
            raise KeyboardInterrupt
        return self.api._integrity_plan({**p, 'edits': merged}, c)

    def sound_system(self, p, c):
        from .audio_systems import audio_system_info
        _, row, _ = self.api.source(p)
        result = audio_system_info(row.get('system_id'), row['sha256'])
        definition = row.get('descriptors', {}).get('sound')
        if definition and definition.get('songs'):
            try:
                doc = self.sound_inspect({**p, 'definition': definition}, c)
                if doc['songs']:
                    if doc['songs'][0]['driver'] in ('hillside-pulse-v1', 'mossy-pulse-v1'):
                        ident = doc['songs'][0]['driver']
                        result['driver'] = {'status': 'VERIFIED_WORKSHOP_DRIVER', 'id': ident, 'name': 'Mossy Hollow pulse driver' if ident == 'mossy-pulse-v1' else 'Hillside pulse driver', 'reference': None, 'evidence': 'Driver code, pitch table and event layout checked against the original workshop implementation.'}
                        result['sequence_edit_supported'] = True
            except ValueError:
                pass
        return result

    def sound_inspect(self, p, c):
        from .sound_studio import inspect_sound
        _, row, raw = self.source(p, c)
        return inspect_sound(raw, p['definition'], row['sha256'])

    def sound_plan(self, p, c):
        from .sound_studio import plan_sound
        project, row, raw = self.source(p, c)
        result = plan_sound(raw, p['definition'], p['document_id'], self.sound_changes(project, p['changes'], c), row['sha256'])
        return {**self.plan(p, result['edits'], c), 'lossy_reencoded_samples': result['lossy_reencoded_samples'], 'document_id': result['document_id']}

    def sound_preview(self, p, c):
        from .sound_studio import preview_sound
        project, row, raw = self.source(p, c)
        wav, meta = preview_sound(raw, p['definition'], row['sha256'], p['kind'], p['resource_id'], self.sound_changes(project, p['changes'], c))
        if c():
            raise KeyboardInterrupt
        return {'ok': True, **meta, 'source_sha256': row['sha256'], 'wav_sha256': hashlib.sha256(wav).hexdigest(), 'wav_base64': base64.b64encode(wav).decode()}

    def sound_changes(self, project, changes, c):
        from .workbench_files import input_file
        if type(changes) is not list or len(changes) > 256:
            raise ValueError('invalid bounded sound changes')
        result = []
        for change in changes:
            if type(change) is not dict:
                raise ValueError('sound changes must be objects')
            change = dict(change)
            if 'wav_input_id' in change:
                if change.get('operation') != 'replace_wav' or change.get('wav_base64') is not None:
                    raise ValueError('ambiguous WAV replacement input')
                row, path = input_file(project, change.pop('wav_input_id'), 'audio')
                change['wav_base64'] = base64.b64encode(read_bounded(path, 2 * 1024 ** 2, row, cancelled=c)).decode()
            result.append(change)
        return result

    def sound_export(self, p, c):
        from .release import publish_bytes
        result = self.sound_preview(p, c)
        project = self.api.project(p)
        path = self.api._export_path(project, 'wav')
        wav = base64.b64decode(result.pop('wav_base64'), validate=True)
        publish_bytes(path, wav, cancelled=c)
        return {**result, 'status': 'EXPORTED', 'export': self.api._record_export(project, path, 'audio', result)}

    def sound_capture(self, p, c):
        from .asset_schema import number
        from .workbench_evidence import store_evidence
        project, row, _ = self.api.source(p)
        number(p['frames'], 1, 300)
        packets = []
        rate = None
        remaining = p['frames']
        with self.api.runtime.lock:
            selected = self.api.runtime.session_selection(project)
            if selected != {'id': row['artifact_id'], 'sha256': row['sha256']}:
                raise ValueError('loaded game differs from selected sound source')
            self.api.runtime.request(project, 'audio', {}, cancelled=c)
            while remaining:
                frames = min(60, remaining)
                self.api.runtime.request(project, 'advance', {'frames': frames, 'buttons': [], 'port': 0}, cancelled=c)
                packet = self.api.runtime.request(project, 'audio', {}, cancelled=c)
                raw = base64.b64decode(packet['pcm_s16le_base64'], validate=True)
                if not packet.get('complete') or packet.get('channels') != 2 or packet.get('format') != 's16le' or len(raw) % 4 or (packet.get('captured_frames') != len(raw) // 4):
                    raise ValueError('native audio capture is incomplete')
                if rate is not None and packet['sample_rate'] != rate:
                    raise ValueError('native audio rate changed during recording')
                rate = packet['sample_rate']
                packets.append(raw)
                remaining -= frames
                if sum(map(len, packets)) > 4 * 1024 ** 2:
                    raise ValueError('native preview exceeds 4 MiB; request fewer frames')
            frame = self.api.runtime.request(project, 'capture', {}, cancelled=c)
        if frame.get('game_sha256') != row['sha256']:
            raise ValueError('native audio source changed')
        if type(rate) not in (int, float) or not float(rate).is_integer() or (not 1000 <= rate <= 192000):
            raise ValueError('unsupported native sample rate')
        raw = b''.join(packets)
        if not raw:
            raise ValueError('no native audio frames captured')
        out = io.BytesIO()
        with wave.open(out, 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(int(rate))
            wav.writeframes(raw)
        data = out.getvalue()
        projects._measure(row['path'], row, cancelled=c)
        meta = {'scope': 'native_sound_preview', 'origin': 'owned_native_worker', 'source_sha256': row['sha256'], 'sample_rate': int(rate), 'sample_frames': len(raw) // 4, 'channels': 2, 'pcm_sha256': hashlib.sha256(raw).hexdigest(), 'frames_advanced': p['frames'], 'core_sha256': frame.get('core_sha256'), 'preview_scope': 'Measured native mixed stereo output. Hardware channels are not separated.', 'timing_status': 'NOT_ASSERTED'}
        evidence = store_evidence(project, 'runtime', meta)
        return {'ok': True, **meta, 'evidence_id': evidence['evidence_id'], 'wav_sha256': hashlib.sha256(data).hexdigest(), 'wav_base64': base64.b64encode(data).decode(), 'frame': frame}

    def example(self, p, c):
        from .studio_examples import make_studio_example
        example = make_studio_example()
        if c():
            raise KeyboardInterrupt
        result = projects.create_project(self.api.projects, 'Design studio')
        project = self.api.project(result)
        with tempfile.TemporaryDirectory(prefix='studio-', dir=self.api.incoming) as temp:
            source = Path(temp) / 'Hillside.nes'
            source.write_bytes(example['raw'])
            owned = projects.register_source(project, source, None, cancelled=c)
        with projects.locked(project) as value:
            value['sources'][0]['descriptors'] = {'levels': example['levels'], 'sound': example['sound']}
            value['demo'] = True
            projects.write_json(project / 'project.json', value)
        return {'ok': True, 'project_id': result['project_id'], 'artifact_id': owned['artifact_id'], 'original_fixture': True}
