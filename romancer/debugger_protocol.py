"""Validate bounded native trace requests and observational event records."""
import re
from .asset_schema import fields,number

LIMITS={'nes':0xffff,'snes':0xffffff,'gb':0xffff,'gbc':0xffff,'gba':0xfffffff,'genesis':0xffffff,'sms':0xffff}
PHYSICAL_DOMAINS={'nes':{'nesInternalRam':2047,'nesPrgRom':64*1024**2-1},
    'snes':{'snesWorkRam':131071,'snesPrgRom':8*1024**2-1},
    'gb':{'gbWorkRam':8191,'gbPrgRom':8*1024**2-1},
    'gbc':{'gbWorkRam':32767,'gbPrgRom':8*1024**2-1},
    'gba':{'gbaExtWorkRam':262143,'gbaIntWorkRam':32767,'gbaPrgRom':32*1024**2-1},
    'genesis':{'genesisWorkRam':65535},'sms':{'smsPrgRom':4*1024**2-1,'smsWorkRam':8191,'smsVideoRam':16383,'smsPaletteRam':31}}
PHYSICAL_DOMAINS['nes'].update(nesChrRom=64*1024**2-1,nesChrRam=32767,nesSpriteRam=255,nesPaletteRam=31,nesNametableRam=4095)
PHYSICAL_DOMAINS['snes'].update(snesVideoRam=65535,snesSpriteRam=543,snesCgRam=511)
for _system in ('gb','gbc'):PHYSICAL_DOMAINS[_system].update(gbVideoRam=16383 if _system=='gbc' else 8191,gbSpriteRam=159,gbBgPaletteRam=63,gbObjPaletteRam=63)
PHYSICAL_DOMAINS['gba'].update(gbaVideoRam=98303,gbaSpriteRam=1023,gbaPaletteRam=1023)
BUTTONS={'nes':{'a','b','select','start','up','down','left','right'},
    'snes':{'a','b','x','y','l','r','select','start','up','down','left','right'},
    'gb':{'a','b','select','start','up','down','left','right'},
    'gbc':{'a','b','select','start','up','down','left','right'},
    'gba':{'a','b','l','r','select','start','up','down','left','right'},
    'genesis':{'a','b','c','start','up','down','left','right'},'sms':{'one','two','pause','up','down','left','right'}}


def validate_capture(system,config):
    if system not in LIMITS:raise ValueError('this native trace backend does not support the selected system')
    fields(config,'steps probes event_limit instruction_limit timeout'+(' start_frame' if 'start_frame' in config else '')+(' graphics_snapshot' if 'graphics_snapshot' in config else ''))
    if 'graphics_snapshot' in config and type(config['graphics_snapshot']) is not bool:raise ValueError('Choose whether to capture a graphics snapshot.')
    number(config['event_limit'],1,2000);number(config['instruction_limit'],1000,20000000);number(config['timeout'],1,60)
    if type(config['steps']) is not list or not 1<=len(config['steps'])<=64:raise ValueError('record 1 to 64 input steps')
    total=0
    for step in config['steps']:
        fields(step,'frames buttons port');number(step['frames'],1,3600);number(step['port'],0,0);total+=step['frames']
        buttons=step['buttons']
        if type(buttons) is not list or any(type(b) is not str for b in buttons) or len(buttons)!=len(set(buttons)) or set(buttons)-BUTTONS[system]:
            raise ValueError('choose supported controller buttons without duplicates')
    number(total,1,3600)
    number(config.get('start_frame',0),0,total-1)
    if type(config['probes']) is not list or not 1<=len(config['probes'])<=8:raise ValueError('choose 1 to 8 memory probes')
    prior=[]
    for probe in config['probes']:
        fields(probe,'kind start end'+(' domain' if 'domain' in probe else ''))
        if probe['kind'] not in ('read','write','exec'):raise ValueError('choose read, write or execution events')
        if system=='genesis' and probe['kind']=='exec':raise ValueError('Genesis execution range watches are unavailable; use read/write probes and separately ordered global instruction samples.')
        domain=probe.get('domain','cpu');limit=LIMITS[system] if domain=='cpu' else PHYSICAL_DOMAINS[system].get(domain)
        if limit is None:raise ValueError('choose a supported CPU or physical memory domain')
        number(probe['start'],0,limit);number(probe['end'],probe['start'],limit)
        if any(p['kind']==probe['kind'] and p.get('domain','cpu')==domain and probe['start']<=p['end'] and p['start']<=probe['end'] for p in prior):
            raise ValueError('same-kind probe ranges must not overlap')
        prior.append(probe)
    return {**config,'frames':total,'start_frame':config.get('start_frame',0)}


def _rom_regions(raw,system):
    class Reader:
        identity={'size':len(raw)}
        def read_at(self,start,length):return raw[start:start+length]
    if system=='nes':
        from .system_formats.nes import candidates
        layouts=[c for c in candidates(Reader()) if c['layout_valid']]
        if len(layouts)!=1:return {}
        names={'prg-rom':'nesPrgRom','chr-rom':'nesChrRom'}
        return {names[r['id']]:(r['offset'],r['length']) for r in layouts[0]['regions'] if r['id'] in names}
    if system=='snes':
        from .system_formats.snes import candidates
        layouts=[c for c in candidates(Reader()) if c['layout_valid']]
        regions={(r['offset'],r['length']) for c in layouts for r in c['regions'] if r['id']=='rom'}
        return {'snesPrgRom':next(iter(regions))} if len(regions)==1 else {}
    if system in ('gb','gbc'):return {'gbPrgRom':(0,len(raw))}
    if system=='gba':return {'gbaPrgRom':(0,len(raw))}
    if system=='sms':
        from .system_formats.sms import candidates
        layouts=[c for c in candidates(Reader()) if c['layout_valid']]
        return {'smsPrgRom':(0,len(raw))} if len(layouts)==1 else {}
    return {}


def parse_capture(text,nonce,system,raw,config):
    requested=validate_capture(system,config)
    if type(text) is not str or len(text.encode('utf-8'))>2*1024**2:raise ValueError('native event output exceeds its budget')
    lines=text.splitlines()
    if not lines or lines[0]!='BEGIN\t1\t'+nonce+'\t'+system:raise ValueError('native capture identity or protocol differs')
    domains={};events=[];by_id={};end=None;regions=_rom_regions(raw,system);graphics={}
    def integer(value,minimum=0,maximum=2**53-1):
        if re.fullmatch('-?[0-9]{1,16}',value) is None:raise ValueError('invalid native integer')
        return number(int(value),minimum,maximum)
    def mapping(domain,address):
        domain_name=domains.get(domain)
        region=regions.get(domain_name);offset=None
        if region and 0<=address<region[1]:offset=region[0]+address
        return domain_name,offset
    for line in lines[1:]:
        if end is not None:raise ValueError('unexpected data after native end record')
        part=line.split('\t');kind=part[0]
        if kind in ('M','SCREEN','S'):
            if not config.get('graphics_snapshot'):raise ValueError('Graphics snapshot was not requested.')
            from .graphics_snapshot import parse_graphics_record
            parse_graphics_record(line,system,graphics)
        elif kind=='DOMAIN' and len(part)==3:
            if events or len(domains)>=128 or re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}',part[1]) is None:raise ValueError('invalid native domain declaration')
            ident=integer(part[2],0,255)
            if ident in domains or part[1] in domains.values():raise ValueError('duplicate native domain')
            domains[ident]=part[1]
        elif kind=='E' and len(part)==11:
            ident=integer(part[1],1,config['event_limit']);event_kind=part[2]
            address=integer(part[3],0,LIMITS[system]);value=integer(part[4],-2**31,2**32-1)
            if ident!=len(events)+1:raise ValueError('native event count differs')
            pc=integer(part[5],-1,LIMITS[system]);domain=integer(part[6],-1,255);physical=integer(part[7],-1,64*1024**2)
            context_domain=integer(part[8],-1,255);context_physical=integer(part[9],-1,64*1024**2)
            frame=integer(part[10],0,requested['frames']+1)
            if frame<requested['start_frame']:raise ValueError('native event precedes the requested capture window')
            domain_name,offset=mapping(domain,physical);context_name,context_offset=mapping(context_domain,context_physical)
            if not any(p['kind']==event_kind and ((p.get('domain','cpu')=='cpu' and p['start']<=address<=p['end']) or
                (p.get('domain')==domain_name and p['start']<=physical<=p['end'])) for p in config['probes']):
                raise ValueError('native event probe scope differs')
            agrees=raw[offset]==(value&255) if offset is not None else None
            # A byte disagreement indicates transformation or a mapping we have
            # not established; it cannot become a source-edit location.
            if agrees is False:offset=None
            event={'id':ident,'kind':event_kind,'address':address,'value':value,'frame':frame,
                'domain':domain_name,'physical_offset':physical if physical>=0 else None,'file_offset':offset,
                'source_byte_agrees':agrees,'execution_context':{'pc':pc if pc>=0 else None,
                    'domain':context_name,'physical_offset':context_physical if context_physical>=0 else None,
                    'file_offset':context_offset,'mapping_observed_at':'execution_callback'},
                'registers':{},'access_width':None,'actor':None,'causation_proven':False}
            events.append(event);by_id[ident]=event
        elif kind=='N' and len(part)==6:
            ident=integer(part[1],1,config['event_limit']);event=by_id.get(ident)
            operations={'read':{'Read','DmaRead','DummyRead','PpuRenderingRead'},'write':{'Write','DmaWrite','DummyWrite'},'exec':{'ExecOpCode','ExecOperand'}}
            width=integer(part[3],1,4);domain=integer(part[4],-1,255);physical=integer(part[5],-1,64*1024**2)
            if event is None or ident!=len(events) or 'operation_kind' in event or part[2] not in operations[event['kind']] or width not in (1,2,4):raise ValueError('Native operation details differ from the observed access.')
            name,_=mapping(domain,physical)
            if name!=event['domain'] or (physical if physical>=0 else None)!=event['physical_offset']:raise ValueError('Native physical mapping details differ.')
            event.update(operation_kind=part[2],callback_value_bytes=width,dma_channel=None,actor='dma' if part[2] in ('DmaRead','DmaWrite') else 'ppu_renderer' if part[2]=='PpuRenderingRead' else None)
        elif kind=='R' and len(part)==5:
            event=by_id.get(integer(part[1],1,config['event_limit']));name=part[2]
            if event is None or len(event['registers'])>=64 or re.fullmatch('[A-Za-z][A-Za-z0-9_.]{0,63}',name) is None or name in event['registers']:raise ValueError('invalid native register record')
            if part[3]=='b' and part[4] in ('true','false'):value=part[4]=='true'
            elif part[3]=='n':value=integer(part[4],-2**52,2**53-1)
            else:raise ValueError('invalid native register value')
            event['registers'][name]=value
        elif kind=='END' and len(part)==6:
            frame=integer(part[1],0,requested['frames']);emitted=integer(part[2],0,config['event_limit'])
            omitted=integer(part[3]);executed=integer(part[4],0,config['instruction_limit']);reason=part[5]
            if emitted!=len(events) or reason not in ('frames','instruction_limit') or reason=='frames' and frame!=requested['frames']:
                raise ValueError('native end record is incomplete or inconsistent')
            if reason=='instruction_limit' and executed!=config['instruction_limit']:raise ValueError('native instruction budget differs')
            end={'frames_observed':frame,'omitted_events':omitted,'executed_callbacks':executed,'stop_reason':reason,'route_complete':reason=='frames'}
        else:raise ValueError('unknown or malformed native event record')
    if end is None:raise ValueError('native capture did not produce its end record')
    snapshot={}
    if config.get('graphics_snapshot'):
        from .graphics_snapshot import finish_snapshot
        snapshot['graphics_snapshot']=finish_snapshot(graphics,system)
    return {'ok':True,'status':'CAPTURED' if end['route_complete'] and not end['omitted_events'] else 'BUDGET_EXCEEDED',**snapshot,
        'system_id':system,'native_callbacks_observed':True,'events':events,**end,
        'write_authorized':False,'memory_written':False,'runtime_scope':'main CPU callbacks from a bounded cold-start input route',
        'limitations':['Access width, DMA actor and dummy-read subtype are not exposed by this backend API.',
            'The last executed instruction supplies context; causal ownership of a transfer is not established.',
            'Physical ROM offsets are mapped only through supported source layouts; firmware and transformed storage remain unresolved.',
            'Cold-start captures do not import a libretro save state.']}
