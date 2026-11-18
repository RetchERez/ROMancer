"""Native graphics access trails, distinct from inferred or proved dataflow."""
import base64
from .asset_schema import number,label
from .debugger_protocol import _rom_regions,validate_capture,PHYSICAL_DOMAINS,BUTTONS
from .assets import checked_path
from .native_debugger import verify_backend
from .visual_checks import _png
from . import workbench_projects as projects

VIDEO_DOMAINS={'nes': ['nesChrRam', 'nesSpriteRam', 'nesPaletteRam', 'nesNametableRam'], 'snes': ['snesVideoRam', 'snesSpriteRam', 'snesCgRam'], 'gb': ['gbVideoRam', 'gbSpriteRam'], 'gbc': ['gbVideoRam', 'gbSpriteRam', 'gbBgPaletteRam', 'gbObjPaletteRam'], 'sms': ['smsVideoRam', 'smsPaletteRam']}


def capture_config(system, raw, replay, offset, length, start_frame):
    number(offset, 0, len(raw) - 1)
    number(length, 1, min(2048, len(raw) - offset))
    if replay.get('status') != 'READY' or type(replay.get('steps')) is not list or (not 1 <= len(replay['steps']) <= 64):
        raise ValueError('Capture a fresh cold-start route of at most 64 input steps.')
    steps = []
    for step in replay['steps']:
        if type(step) is not dict or set(step) != {'frames', 'buttons', 'port'} or step['port'] != 0 or (type(step['buttons']) is not list):
            raise ValueError('Use a single supported controller route.')
        mapping = {'a': 'b', 'b': 'a', 'r': 'c', 'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right', 'start': 'start'} if system == 'genesis' else {'a': 'one', 'b': 'two', 'start': 'pause', 'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'} if system == 'sms' else {b: b for b in BUTTONS.get(system, ())}
        if any((type(b) is not str or b not in mapping for b in step['buttons'])):
            raise ValueError('This route uses buttons unavailable on the native observer controller. Record a supported route.')
        steps.append({**step, 'buttons': [mapping[b] for b in step['buttons']]})
    frames = sum((number(s['frames'], 1, 3600) for s in steps))
    if frames != replay.get('frames') or not 1 <= frames <= 3600:
        raise ValueError('Native graphics replay is limited to 3600 frames; the recorded route must fit without truncation.')
    number(start_frame, 0, frames - 1)
    if system == 'genesis':
        probes = [{'kind': 'read', 'start': offset, 'end': offset + length - 1}, {'kind': 'write', 'start': 12582912, 'end': 12582943}]
    else:
        regions = _rom_regions(raw, system)
        region = next(((name, base, size) for name, (base, size) in regions.items() if base <= offset and offset + length <= base + size), None)
        if region is None:
            raise ValueError('Choose a source span inside a checked native ROM region.')
        name, base, _ = region
        probes = [{'kind': 'read', 'domain': name, 'start': offset - base, 'end': offset - base + length - 1}]
        probes.extend(({'kind': 'write', 'domain': name, 'start': 0, 'end': PHYSICAL_DOMAINS[system][name]} for name in VIDEO_DOMAINS[system]))
    result = {'steps': steps, 'probes': probes, 'start_frame': start_frame, 'event_limit': 2000, 'instruction_limit': 20000000, 'timeout': 60, 'graphics_snapshot': True}
    validate_capture(system, result)
    return result


def public_capture(result):
    snapshot=result.get('graphics_snapshot',{});memory=snapshot.get('memory',{});events=result.get('events',[])
    packet={k:v for k,v in result.items() if k!='graphics_snapshot'}
    packet.update(memory_domains=[{'name':name,'size':r['size'],'sha256':r['data_sha256']} for name,r in memory.items()],graphics_state=snapshot.get('state',{}),
        observed_rom_offsets=sorted({e['file_offset'] for e in events if e.get('file_offset') is not None}),observed_dma_events=sum(e.get('actor')=='dma' for e in events),
        observation_counts_scope='returned_event_page',causal_dataflow_proven=False,same_runtime_state_claimed=False,snapshot_complete=snapshot.get('complete_memory_snapshot',False),snapshot_missing=snapshot.get('missing_or_partial_domains',[]),
        scope='Recorded access trail and end-of-capture video snapshot from a separate native observer replay. Adjacent ROM reads and video writes do not by themselves establish dataflow or game meaning.')
    if snapshot.get('frame'):
        frame=snapshot['frame'];raw=base64.b64decode(frame['rgb24_base64'],validate=True)
        packet['scene']={k:frame[k] for k in ('width','height','sha256')};packet['scene']['png_base64']=_png(raw,frame['width'],frame['height'])
    return packet


def capture_ids(row):
    ids=row.get('graphics_captures',[])
    if type(ids) is not list or len(ids)>64 or len(set(ids))!=len(ids):raise ValueError('Saved graphics capture index is invalid.')
    for ident in ids:projects.identifier(ident)
    return ids

def remember_capture(project,row,ident):
    projects.identifier(ident)
    with projects.locked(project) as store:
        owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id'])
        if owned['sha256']!=row['sha256']:raise ValueError('Selected source changed during graphics capture.')
        owned['graphics_captures']=([i for i in capture_ids(owned) if i!=ident]+[ident])[-64:]
        projects.write_json(project/'project.json',store)

def require_graphics(result):
    if not result.get('graphics_snapshot') or not result.get('investigation_link',{}).get('graphics_trace_id'):
        raise ValueError('Choose an authenticated graphics access capture.')
    return result


class GraphicsAccessTools:
    def __init__(self,api):self.api=api
    def routes(self):
        return {'graphics.accesses.list':('project_id artifact_id',self.list),'graphics.accesses.capture':('project_id artifact_id trace_id offset length start_frame',self.capture),
            'graphics.accesses.get':('project_id artifact_id evidence_id offset limit',self.get),
            'graphics.accesses.memory':('project_id artifact_id evidence_id domain offset length',self.memory),'graphics.accesses.tiles':('project_id artifact_id evidence_id domain offset count codec',self.tiles)}
    def capture(self,p,c):
        project,row,path=self.api.source(p);trace=self.api.traces.get(p,c)
        if not trace['runtime_trusted']:raise ValueError('Use a fresh local trace for native graphics replay.')
        if row['size']>64*1024**2:raise ValueError('Native graphics replay supports cartridges up to 64 MiB.')
        from .debugger_provision import preferred_root
        root=preferred_root(self.api.workspace,row['system_id']);backend=verify_backend(root,row['system_id'])
        if row['system_id']!='genesis' and not backend.get('native_access_details'):raise ValueError('The full graphics observer is required. Install the current complete Windows package or rebuild its documented observer source.')
        config=capture_config(row['system_id'],checked_path(path).read_bytes(),trace.get('replay',{}),p['offset'],p['length'],p['start_frame'])
        result=self.api.debugger._capture(p,c,config,{'graphics_trace_id':p['trace_id'],'same_runtime_state_claimed':False})
        remember_capture(project,row,result['evidence_id'])
        return public_capture(result)
    def list(self,p,c):
        _,row,_=self.api.source(p);items=[]
        for ident in reversed(capture_ids(row)):
            if c():raise KeyboardInterrupt
            r=require_graphics(self.api.debugger.get({**p,'evidence_id':ident,'offset':0,'limit':1},c))
            items.append({'evidence_id':ident,'trace_id':r['investigation_link']['graphics_trace_id'],'runtime_trusted':r['runtime_trusted'],'total_events':r['total_events'],'status':r.get('status'),'system_id':r['system_id']})
        return {'ok':True,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],'captures':items}
    def get(self,p,c):return public_capture(require_graphics(self.api.debugger.get(p,c)))
    def memory(self,p,c):
        result=require_graphics(self.api.debugger.get({**p,'offset':0,'limit':1},c));label(p['domain'],64);domain=result.get('graphics_snapshot',{}).get('memory',{}).get(p['domain'])
        if domain is None:raise ValueError('Choose a memory domain recorded in this graphics capture.')
        offset=number(p['offset'],0,domain['size']-1);length=number(p['length'],1,min(4096,domain['size']-offset));raw=bytes.fromhex(domain['data_hex'])[offset:offset+length]
        return {'ok':True,'evidence_id':p['evidence_id'],'runtime_trusted':result['runtime_trusted'],'source_sha256':result['source_sha256'],'artifact_id':result['artifact_id'],
            'domain':p['domain'],'offset':offset,'length':length,'raw_hex':raw.hex(),'domain_sha256':domain['data_sha256'],'write_authorized':False,'point':'end_of_capture'}

    def tiles(self,p,c):
        from .asset_codecs import decode_cell,cell_size
        from .graphics_discovery import SYSTEM_CODECS
        _,row,_=self.api.source(p)
        allowed=[SYSTEM_CODECS[row['system_id']]]
        if row['system_id']=='snes':allowed+=['tile8-paired2-msb-v1']
        if p['codec'] not in allowed:raise ValueError('Choose a tested literal tile codec for this system.')
        video={'nes': 'nesPpuMemory', 'snes': 'snesVideoRam', 'sms': 'smsVideoRam', 'gb': 'gbVideoRam', 'gbc': 'gbVideoRam', 'genesis': 'genesisVideoRam'}[row['system_id']]
        if p['domain']!=video:raise ValueError('Choose the captured pattern/video memory domain for tile decoding.')
        count=number(p['count'],1,64);extent=cell_size(p['codec'],8,8)
        result=self.memory({**p,'length':count*extent},c);raw=bytes.fromhex(result['raw_hex'])
        if len(raw)!=count*extent:raise ValueError('Recorded memory does not contain every complete requested tile.')
        cells=[{'index':i,'offset':p['offset']+i*extent,'pixels':decode_cell(raw[i*extent:(i+1)*extent],codec=p['codec'],width=8,height=8)} for i in range(count)]
        return {k:v for k,v in result.items() if k!='raw_hex'}|{'codec':p['codec'],'cells':cells,'rom_source_proven':False,'palette_scope':'stored indices; display with a declared palette or grayscale'}
