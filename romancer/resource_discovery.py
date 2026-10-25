"""Deterministic, bounded read-only resource candidates; never write authority."""
from pathlib import Path
from .asset_schema import number
from .assets import checked_path,digest
from .resource_forms import TEMPLATES
from .system_identify import identify_system
from .system_registry import FOCUS_SYSTEM_IDS
from .workbench_projects import _measure

SCAN_LIMIT=16*1024**2
RESULT_LIMIT=2000


def _read(path,sha,start,length,cancelled):
    if cancelled():raise KeyboardInterrupt
    number(start,0,8*1024**3);number(length,1,SCAN_LIMIT)
    path=checked_path(Path(path));source=_measure(path,cancelled=cancelled)
    if source['sha256']!=sha:raise ValueError('source revision changed; select and inspect the current source')
    if start>=source['size']:raise ValueError('scan start is outside the source')
    length=min(length,source['size']-start)
    with path.open('rb') as stream:
        stream.seek(start);raw=stream.read(length)
    if len(raw)!=length:raise ValueError('source changed while scanning')
    return path,source,raw


def pointer_references(path,sha,*,target,width,endian,base,start=0,length=SCAN_LIMIT,cancelled=lambda:False):
    number(width,2,4);number(base,0,0xffffffff)
    if endian not in ('little','big'):raise ValueError('choose little or big pointer byte order')
    path,source,raw=_read(path,sha,start,length,cancelled)
    number(target,0,source['size']-1)
    if target+base>=1<<(width*8):raise ValueError('target plus pointer base does not fit the selected width')
    needle=(target+base).to_bytes(width,endian);rows=[];position=0
    while len(rows)<RESULT_LIMIT:
        if cancelled():raise KeyboardInterrupt
        position=raw.find(needle,position)
        if position<0:break
        rows.append({'kind':'pointer','offset':start+position,'length':width,'target_offset':target,'format':f'u{width*8}-{endian}',
                     'confidence':'possible','reason':'Exact encoded target under the supplied linear pointer base; not a proven reference.','preview':needle.hex()})
        position+=1
    _measure(path,source,cancelled=cancelled)
    return rows


def discover(path,sha,system_id,start,length,kinds,*,target=None,cancelled=lambda:False):
    if system_id not in FOCUS_SYSTEM_IDS:raise ValueError('choose NES, SNES, Genesis, Game Boy, Game Boy Color or GBA')
    if type(kinds) is not list or not kinds or len(kinds)!=len(set(kinds)) or set(kinds)-{'text','graphics','pointers','compression'}:
        raise ValueError('choose supported discovery kinds')
    path,source,raw=_read(path,sha,start,length,cancelled);rows=[];truncated=False;sampling=None;compression_budget={}
    def add(row):
        nonlocal truncated
        if len(rows)>=RESULT_LIMIT:truncated=True;return
        row['candidate_id']=digest({'source':sha,'kind':row['kind'],'offset':row['offset'],'length':row['length'],'format':row['format']})
        rows.append(row)
    if 'text' in kinds:
        run_start=None;preview=[]
        for position,value in enumerate(raw+b'\0'):
            if position%4096==0 and cancelled():raise KeyboardInterrupt
            if 32<=value<=126 and position<len(raw):
                if run_start is None:run_start=position
                if len(preview)<120:preview.append(value)
                continue
            if run_start is not None:
                count=position-run_start
                if count>=5:
                    capacity=min(count+(position<len(raw)),65536)
                    add({'kind':'text','offset':start+run_start,'length':capacity,'format':'ascii-fixed-slot','confidence':'possible',
                         'preview':bytes(preview).decode('ascii'),'reason':'Printable ASCII run; confirm encoding, terminator and allocation.',
                         'config':{'system_id':system_id,'offset':start+run_start,'capacity':capacity,'count':1,'stride':capacity,
                                   'pointer_offset':None,'encoding':'ascii','terminator':value if position<len(raw) else 0,'padding':255}})
                run_start=None;preview=[]
    if 'graphics' in kinds:
        derived=None
        if system_id=='nes':
            assessment=identify_system(path,expected_sha256=sha,cancelled=cancelled)
            if assessment['status']=='IDENTIFIED' and assessment['system_id']=='nes':
                derived=next((r for r in assessment['regions'] if r['id']=='chr-rom' and r['length']>=16 and start<=r['offset']<start+len(raw)),None)
                if derived:
                    count=min(16,derived['length']//16,(start+len(raw)-derived['offset'])//16)
                    if count:
                        add({'kind':'graphics','offset':derived['offset'],'length':count*16,'format':TEMPLATES['nes'],'confidence':'format-derived',
                             'preview':f'{count} stored CHR-ROM tiles','reason':'Validated NES header declares this stored CHR-ROM region; palettes/consumers remain unknown.',
                             'config':{'system_id':'nes','offset':derived['offset'],'count':count,'codec':TEMPLATES['nes']}})
        cell=16 if system_id in ('nes','gb','gbc') else 32;block_size=16*cell
        sampling=max(block_size,((len(raw)+4095)//4096+cell-1)//cell*cell)
        for offset in range(0,max(0,len(raw)-block_size+1),sampling):
            if cancelled():raise KeyboardInterrupt
            if derived and derived['offset']<=start+offset<derived['offset']+derived['length']:continue
            block=raw[offset:offset+block_size];variety=len(set(block));occupied=sum(b!=0 for b in block)
            if 1<variety<=32 and occupied>=block_size//8:
                add({'kind':'graphics','offset':start+offset,'length':block_size,'format':TEMPLATES[system_id],'confidence':'possible',
                     'preview':block[:16].hex(),'reason':f'Sampled16-tile block has{variety} byte values; inspect the system codec preview to confirm.',
                     'config':{'system_id':system_id,'offset':start+offset,'count':16,'codec':TEMPLATES[system_id]}})
    if 'pointers' in kinds:
        if type(target) is not dict or set(target)!={'offset','width','endian','base'}:raise ValueError('supply explicit target offset, pointer width, byte order and linear base')
        for row in pointer_references(path,sha,target=target['offset'],width=target['width'],endian=target['endian'],base=target['base'],start=start,length=len(raw),cancelled=cancelled):add(row)
    if 'compression' in kinds:
        # A codec parser is required before candidates can be emitted (Task4).
        from importlib.util import find_spec
        if find_spec('romancer.resource_compression'):
            from .resource_compression import compression_candidates
            for row in compression_candidates(raw,start,cancelled=cancelled,budget=compression_budget):add(row)
    _measure(path,source,cancelled=cancelled)
    end=start+len(raw)
    return {'ok':True,'status':'CANDIDATES','source_sha256':sha,'system_id':system_id,'candidates':rows,
            'scanned_offset':start,'scanned_length':len(raw),'partial':start!=0 or end<source['size'] or truncated or compression_budget.get('partial',False),
            'next_offset':compression_budget.get('next_offset') if compression_budget.get('partial') else end if end<source['size'] else None,'compression_scan':compression_budget,'results_truncated':truncated,'graphics_sampling_stride':sampling,
            'write_authorized':False,'runtime_verified':False,'note':'Candidate matches require confirmation. Graphics use sampled blocks, not exhaustive game-layout detection.'}
