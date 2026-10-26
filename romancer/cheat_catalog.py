"""Bounded local cheat-label research. Imported claims never authorize writes.

Code decoding and candidate ROM reads are separate from publication labels.
No code is executed, no network reference is followed, and no ROM is changed.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import zlib

from . import workbench_projects as projects
from .assets import checked_path
from .workbench_files import input_file,read_bounded

MAX_BYTES=16*1024*1024
MAX_RECORDS=20000
MAX_STORE=16*1024*1024
ALIASES={'nes':'nes','nintendo entertainment system':'nes','famicom':'nes',
         'genesis':'genesis','genesis / mega drive':'genesis','mega drive':'genesis','sega genesis':'genesis','megadrive':'genesis',
         'snes':'snes','super nintendo':'snes','super nes':'snes','super famicom':'snes',
         'gb':'gb','game boy':'gb','gameboy':'gb','gbc':'gbc','game boy color':'gbc',
         'gba':'gba','game boy advance':'gba','game gear':'gamegear','gamegear':'gamegear',
         'fc':'nes','sfc':'snes','md':'genesis','gen':'genesis','gameboycolor':'gbc',
         'sms':'sms','sega master system':'sms','master system':'sms'}


def _cancel(cancelled):
    if cancelled():raise KeyboardInterrupt('catalog research cancelled')


def _text(value,limit,name):
    if value is None:return ''
    if type(value) is not str or len(value)>limit or any(ord(c)<32 and c not in '\r\n\t' for c in value):raise ValueError(name+' is not bounded text')
    return value.strip()


def _system(value):
    value=_text(value,80,'system').lower().strip()
    return ALIASES.get(value,value)


def _title(value):
    value=unicodedata.normalize('NFKD',value).casefold()
    value=re.sub(r'\([^)]*\)|\[[^]]*\]',' ',value)
    return ''.join(c for c in value if c.isalnum())


def _pairs(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate JSON key: '+key[:80])
        value[key]=item
    return value


def _json(raw):
    try:return json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('non-finite JSON number')))
    except (RecursionError,UnicodeError) as exc:raise ValueError('catalog JSON nesting or encoding is invalid') from exc


def _first(record,*keys):
    return next((record[k] for k in keys if k in record and record[k] not in (None,'')),None)


def _format(value):
    value=_text(value,80,'code format').lower()
    compact=re.sub(r'[\s_-]+','',value)
    if compact in ('gamegenie','gg'):return 'game-genie'
    if 'actionreplay' in compact or compact in ('ar','par'):return 'action-replay'
    return re.sub(r'\s+','-',value)


def _canonical(record,index):
    if type(record) is not dict:raise ValueError('catalog records must be objects')
    data={str(k).strip().lower():v for k,v in record.items()}
    system=_system(_first(data,'system_id','system','platform') or '')
    game=_text(_first(data,'game_title','game','title') or '',240,'game title')
    code=_first(data,'code_text','code','codes') or ''
    if type(code) is list:
        if len(code)>32:raise ValueError('too many required code parts')
        code=' + '.join(_text(c,80,'code part') for c in code)
    code=_text(code,4096,'code text')
    label=_text(_first(data,'label','effect_name','effect','description') or 'Imported effect claim',2048,'effect label')
    refs=_first(data,'source_refs','source_references','source_ref','source_reference','source') or []
    if type(refs) is str:refs=[refs]
    if type(refs) is not list or len(refs)>16:raise ValueError('source references exceed the bounded list')
    refs=[_text(v,2048,'source reference') for v in refs]
    url=_text(_first(data,'source_url','url') or '',2048,'source URL')
    location=_text(_first(data,'source_location','location') or '',2048,'source location')
    source_path=_text(_first(data,'source_path','source_file') or '',2048,'source path label')
    if source_path and source_path not in refs and len(refs)<16:refs.append(source_path)
    if url and url not in refs and len(refs)<16:refs.append(url)
    if not url:url=next((m.group(0) for ref in refs if (m:=re.search(r'https?://[^\s<>]+',ref))), '')
    if url and not re.fullmatch(r'https?://[^\s<>]+',url):url=''
    hashes={}
    nested=data.get('hashes',{})
    if type(nested) is not dict:raise ValueError('revision hashes must be an object')
    for kind,length,keys in [('crc32',8,('rom_crc','rom_crc32','crc32','crc')),('md5',32,('rom_md5','md5')),('sha1',40,('rom_sha1','sha1')),('sha256',64,('rom_sha256','sha256'))]:
        value=_first(data,*keys) or nested.get(kind)
        if value is not None and value!='':
            value=_text(value,128,kind).lower().removeprefix('0x')
            if not re.fullmatch('[0-9a-f]{'+str(length)+'}',value):raise ValueError('invalid '+kind+' revision hash')
            hashes[kind]=value
    alternatives=[];reason=''
    for alternative in code.split('/'):
        group=[part.strip() for part in alternative.split('+')]
        if len(group)>32 or any(len(part)>80 for part in group):raise ValueError('code group exceeds its bounds')
        if not all(group):reason='empty code or required combination part'
        alternatives.append(group)
    if len(alternatives)>32:raise ValueError('too many alternative code revisions')
    if sum(map(len,alternatives))>128:raise ValueError('too many code parts in one record')
    if not system or not game:reason='missing system or game title'
    formats={_format(data[k]) for k in ('format','code_type','device_or_format') if data.get(k) not in (None,'')}
    code_format=next(iter(formats)) if len(formats)==1 else ('conflicting-formats' if formats else 'game-genie')
    value={'system_id':system,'game_title':game,'code_text':code,'label':label,'alternatives':alternatives,
           'format':code_format,
           'hashes':hashes,'source_refs':refs,'source_url':url,'source_location':location,'source_path':source_path,
           'parse_status':'INVALID' if reason else 'PARSED','parse_reason':reason,
           'source_claim':'Imported source/effect label; not independently verified gameplay.',
           'gameplay_verified':False,'write_authorized':False}
    value['id']=hashlib.sha256((str(index)+'\n'+json.dumps(value,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
    return value


def parse_catalog(raw):
    """Parse local UTF-8 publication text or old archive JSON/JSONL/CSV/TSV."""
    if type(raw) is not bytes or len(raw)>MAX_BYTES:raise ValueError('catalog exceeds 16 MiB or is not bytes')
    try:text=raw.decode('utf-8-sig')
    except UnicodeError as exc:raise ValueError('catalog must be UTF-8') from exc
    if '\x00' in text:raise ValueError('catalog contains NUL text')
    stripped=text.lstrip();records=[]
    if stripped.startswith('{') or re.match(r'^\[\s*[\{\]]',stripped):
        try:value=_json(text)
        except json.JSONDecodeError:
            value=[_json(line) for line in text.splitlines() if line.strip()]
        if type(value) is dict:
            value=next((value[k] for k in ('records','entries','cheats') if k in value),[value])
        if type(value) is not list:raise ValueError('catalog JSON must contain records')
        records=value
    else:
        first=next((line for line in text.splitlines() if line.strip()),'')
        delimiter='\t' if '\t' in first else ','
        headers=[h.strip().lower() for h in first.split(delimiter)]
        if any(k in headers for k in ('code_text','code','codes')) and any(k in headers for k in ('game_title','game','title')):
            try:
                reader=csv.DictReader(io.StringIO(text),delimiter=delimiter,strict=True)
                if reader.fieldnames is None or len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError('duplicate catalog column')
                for row in reader:
                    if None in row:raise ValueError('catalog row has extra columns')
                    records.append(row)
                    if len(records)>MAX_RECORDS:raise ValueError('catalog exceeds 20000 records')
            except csv.Error as exc:raise ValueError('invalid bounded delimited catalog') from exc
        else:
            system=game='';refs=[];url=location=source_path='';definitions={};current_source=None
            global_refs=[];global_url='';code_format='game-genie';in_note=False;community=False
            for line in text.splitlines():
                line=line.strip()
                if line=='END OF VERIFIED-PUBLICATION EXTRACT':
                    system=game='';refs=[];url=location=source_path='';current_source=None;in_note=False;community=True;continue
                if (m:=re.match(r'^(SOURCE-[A-Za-z0-9_-]+):\s*(.*)$',line)):
                    current_source=m[1];definitions[current_source]=[m[2]];continue
                if not system and current_source and line:
                    definitions[current_source].append(line)
                if not line:current_source=None;continue
                if (m:=re.fullmatch(r'\[([^]]+)\]\s*(.*)',line)):
                    system=_system(m[1]);game=m[2];refs=list(global_refs);url=global_url;location=source_path='';in_note=False;code_format='game-genie'
                    if (device:=re.search(r'\s*\((Game[ -]?Genie|(?:Pro[ -]?)?Action[ -]?Replay)\)\s*$',game,re.I)):
                        code_format=_format(device[1]);game=game[:device.start()].strip()
                    continue
                if line.upper().startswith('SOURCE:'):
                    items=line[7:].strip().split('|',1);key=items[0].strip();location=items[1].strip() if len(items)>1 else ''
                    if not system:
                        if re.fullmatch(r'https?://[^\s<>]+',key):global_url=key;global_refs=[key]
                        continue
                    if key in definitions:
                        refs=[key]+definitions[key];url=next((m.group(0) for ref in refs if (m:=re.search(r'https?://[^\s<>]+',ref))), '')
                    elif re.fullmatch(r'https?://[^\s<>]+',key):url=key;refs=list(global_refs)+[key]
                    else:
                        source_path=key if key.lower().endswith('.cht') else '';location=location or source_path;refs=list(global_refs)+[key];url=global_url
                    continue
                if not system:continue
                if line.upper().startswith(('NOTE:','NOTES:')):in_note=True;continue
                if line.startswith(('#',';')) or set(line)<={'=','-'}:continue
                if '|' in line:
                    in_note=False;code,label=line.split('|',1);records.append({'system':system,'game_title':game,'format':code_format,'code_text':code.strip(),'label':label.strip(),'source_refs':refs[:16],'source_url':url,'source_location':location,'source_path':source_path})
                elif not in_note and not community:records.append({'system':system,'game_title':game,'format':code_format,'code_text':line,'label':'Unparsed imported line','source_refs':refs[:16],'source_location':location})
                if len(records)>MAX_RECORDS:raise ValueError('catalog exceeds 20000 records')
    if not records or len(records)>MAX_RECORDS:raise ValueError('catalog must contain 1..20000 records')
    return [_canonical(row,index) for index,row in enumerate(records)]


def _catalog_path(project):
    return checked_path(checked_path(Path(project))/'catalog'/'cheats.json')


def import_catalog(project,input_id,*,cancelled=lambda:False):
    """Replace only the owned cheat catalog; never open a reference as a path."""
    _cancel(cancelled);incoming,path=input_file(project,input_id,'catalog');raw=read_bounded(path,MAX_BYTES,incoming,cancelled=cancelled);rows=parse_catalog(raw);_cancel(cancelled)
    payload={'format':'romancer-cheat-catalog-v1','input_id':input_id,'input_sha256':incoming['sha256'],'rows':rows}
    with projects.locked(project):
        folder=checked_path(Path(project)/'catalog');folder.mkdir(exist_ok=True);_cancel(cancelled)
        projects.write_json(_catalog_path(project),payload,max_bytes=MAX_STORE)
    return len(rows)


def _load(project,cancelled=lambda:False):
    path=_catalog_path(project)
    if not path.exists():return None,None
    raw=read_bounded(path,MAX_STORE,cancelled=cancelled);value=_json(raw)
    if type(value) is not dict or value.get('format')!='romancer-cheat-catalog-v1' or type(value.get('rows')) is not list or not 1<=len(value['rows'])<=MAX_RECORDS:raise ValueError('invalid owned cheat catalog')
    # Revalidate the stored records rather than granting authority to edited metadata.
    rows=[_canonical(row,index) for index,row in enumerate(value['rows'])]
    return rows,{'sha256':hashlib.sha256(raw).hexdigest(),'count':len(rows),'input_sha256':value.get('input_sha256'),'input_id':value.get('input_id')}


def catalog_info(project):
    rows,info=_load(project)
    return {'ok':True,'status':'IMPORTED' if rows else 'EMPTY',**(info or {'sha256':None,'count':0}),'gameplay_verified':False,'write_authorized':False}


def _fingerprints(path,cancelled):
    md5=hashlib.md5();sha1=hashlib.sha1();sha=hashlib.sha256();crc=0
    with Path(path).open('rb') as stream:
        while block:=stream.read(65536):
            _cancel(cancelled);md5.update(block);sha1.update(block);sha.update(block);crc=zlib.crc32(block,crc)
    return {'md5':md5.hexdigest(),'sha1':sha1.hexdigest(),'sha256':sha.hexdigest(),'crc32':f'{crc&0xffffffff:08x}'}


def _locations(system,decoded,path,assessment,profile,cancelled):
    """Conservative static windows. Candidate banks never imply runtime state."""
    address=decoded['address'];width=decoded['width'];compare=decoded.get('compare');size=Path(path).stat().st_size
    if type(address) is not int or width not in (1,2,4):return [],'UNRESOLVED','unsupported decoded address or width'
    if address%decoded.get('alignment',width):return [],'UNRESOLVED','unaligned decoded word; no file read inferred'
    candidates=[];status='RESOLVED';reason='';valid=[c for c in assessment.get('candidates',[]) if c.get('layout_valid')]
    chosen=valid[0] if len(valid)==1 else None;meta=chosen.get('metadata',{}) if chosen else {}
    if system=='nes':
        if not 0x8000<=address<=0xffff:return [],'NOT_ROM','CPU RAM/I/O is not a ROM file offset'
        if not chosen:return [],'UNRESOLVED','requires one valid NES cartridge header'
        prg=meta.get('prg_rom_bytes',0);base=16+(512 if meta.get('trainer_present') else 0);mapper=meta.get('mapper')
        if mapper==0 and prg in (16384,32768):candidates=[(base+(address-0x8000)%prg,None)]
        elif mapper==2 and prg%16384==0:
            if address>=0xc000:candidates=[(base+prg-16384+address-0xc000,prg//16384-1)]
            else:
                banks=prg//16384;candidates=[(base+b*16384+address-0x8000,b) for b in range(min(banks,32))];status='BANK_CANDIDATE';reason='switchable bank unknown; at most 32 physical banks examined'+('; candidates truncated' if banks>32 else '')
        else:return [],'UNRESOLVED','NES mapper/window is not supported by this static analyzer'
    elif system in ('gb','gbc'):
        if not 0<=address<0x8000:return [],'NOT_ROM','CPU RAM/I/O is not a ROM file offset'
        if not chosen:return [],'UNRESOLVED','requires one valid Game Boy header'
        mapper=meta.get('cartridge_type');banks=size//16384;known={0,8,9,5,6,15,16,17,18,19,25,26,27,28,29,30}
        if address<0x4000:
            if mapper not in known:return [],'UNRESOLVED','fixed bank zero is not established for this mapper (including MBC1 alternate mode)'
            candidates=[(address,0)]
        elif mapper in (0,8,9):candidates=[(address,1)]
        elif mapper in known|{1,2,3}:
            possible=range(0 if mapper in {25,26,27,28,29,30} else 1,banks)
            possible=[b for b in possible if mapper not in {1,2,3} or b%32]
            candidates=[(b*16384+address-0x4000,b) for b in possible[:32]];status='BANK_CANDIDATE';reason='switchable bank unknown; compare bytes cannot establish active bank'+('; candidates truncated' if len(possible)>32 else '')
        else:return [],'UNRESOLVED','Game Boy mapper/window not established'
    elif system=='genesis':
        if not 0<=address<0x400000:return [],'NOT_ROM','outside initial 4 MiB linear cartridge window'
        if not chosen or chosen.get('format')!='genesis-linear' or meta.get('rom_start')!=0 or type(meta.get('rom_end')) is not int:return [],'UNRESOLVED','requires one valid linear Genesis header; interleaved/headerless files are not inferred'
        if address+width>meta['rom_end']+1:return [],'NOT_ROM','outside the header-declared linear ROM extent'
        if not profile or profile['id']!='immortal-ue':status='HEURISTIC';reason='unique linear header is static mapping evidence, not runtime proof'
        candidates=[(address,None)]
    elif system=='snes':
        from .system_addresses import translate
        if profile and profile['id']=='chrono-trigger-usa':kind='hirom';prefix=0
        elif chosen and chosen['format'] in ('lorom','hirom'):
            kind=chosen['format'];prefix=meta['copier_header_bytes'];status='HEURISTIC';reason='unique valid header is a mapping heuristic, not gameplay evidence'
        else:return [],'UNRESOLVED','requires unique valid LoROM/HiROM header or exact supported profile'
        try:candidates=[(translate('snes',address,{'id':kind,'copier_header':prefix},None,size)['offset'],None)]
        except ValueError as exc:return [],'NOT_ROM',str(exc)
    else:return [],'UNSUPPORTED','Game Genie mapping is unsupported for this system'
    locations=[]
    with Path(path).open('rb') as stream:
        for offset,bank in candidates:
            _cancel(cancelled)
            if not 0<=offset<=size-width:continue
            # Reads crossing an explicit bank/window end are not guessed.
            if system=='nes' and (address&0x3fff)+width>0x4000:continue
            if system in ('gb','gbc') and (address&0x3fff)+width>0x4000:continue
            if system=='genesis' and address+width>0x400000:continue
            stream.seek(offset);before=stream.read(width)
            match=compare is None or int.from_bytes(before,decoded.get('endian','little'))==compare
            if compare is not None and not match:continue
            locations.append({'offset':offset,'before_hex':before.hex(),'before_value':int.from_bytes(before,decoded.get('endian','little')),'bank':bank,'compare_status':'MATCH' if compare is not None else 'UNSPECIFIED','mapping_status':status,'active_bank_known':False})
    if not locations and candidates:reason='no bounded candidate matches the compare byte or source bounds'
    return locations,status,reason


def _bound_response(result):
    """Keep every row while explicitly shortening imported prose, then parts."""
    result['response_truncated']=False
    for cap in (512,256,128,64):
        if len(json.dumps(result,ensure_ascii=True).encode())<=200*1024:return result
        for entry in result['entries']:
            shortened=set(entry.get('truncated_fields',[]))
            for key in ('game_title','label','code_text','source_url','source_location','source_path'):
                if len(entry[key])>cap:
                    # A shortened URL could identify a different page. Omit it
                    # with an explicit flag rather than fabricate a usable link.
                    entry[key]='' if key=='source_url' else entry[key][:cap];shortened.add(key)
            refs=[s[:cap] for s in entry['source_refs']]
            if refs!=entry['source_refs']:entry['source_refs']=refs;entry['source_refs_truncated']=True;shortened.add('source_refs')
            if shortened:entry['truncated_fields']=sorted(shortened);entry['full_text_retained_in_catalog']=True;result['response_truncated']=True
    while len(json.dumps(result,ensure_ascii=True).encode())>200*1024:
        removed=False
        for entry in reversed(result['entries']):
            for group in reversed(entry['alternatives']):
                if group:
                    group.pop();entry['decode_truncated']=True;entry['omitted_code_parts']+=1;removed=True;result['response_truncated']=True;break
            if removed:break
        if not removed:raise ValueError('catalog response exceeds its bounded metadata budget')
    return result


def inspect_catalog(project,row,path,*,query='',page=0,limit=20,cancelled=lambda:False):
    """Read-only source-bound research; labels are never promoted to facts."""
    from .verified_games import _resolve
    from .system_identify import identify_system
    from .cheat_decode import decode_code
    query=_text(query,240,'catalog query').casefold()
    if type(page) is not int or page<0 or page>MAX_RECORDS or type(limit) is not int or not 1<=limit<=20:raise ValueError('catalog page/limit is outside bounds')
    path=checked_path(Path(path));owned=projects.artifact(project,row['artifact_id'])
    if path!=checked_path(Path(owned['path'])) or any(row.get(k)!=owned.get(k) for k in ('sha256','size','kind')):raise ValueError('selected source identity differs from owned artifact')
    row=owned
    projects._measure(path,row,cancelled=cancelled);profile,root=_resolve(project,row,cancelled);identity=root or row
    projects._measure(identity['path'],identity,cancelled=cancelled)
    system=(profile or {}).get('system') or row.get('system_id') or ''
    game=profile['name'] if profile else Path(identity['name']).stem
    fingerprints=_fingerprints(identity['path'],cancelled)
    if fingerprints['sha256']!=identity['sha256']:raise ValueError('root source revision changed while reading')
    rows,info=_load(project,cancelled);eligible=[]
    for item in rows or []:
        _cancel(cancelled);same_system=item['system_id']==system
        if not same_system:continue
        same_title=bool(_title(item['game_title'])) and _title(item['game_title'])==_title(game)
        matches=bool(item['hashes']) and all(fingerprints[k]==v for k,v in item['hashes'].items())
        if not (matches or same_title):continue
        if query and query not in (item['game_title']+' '+item['label']+' '+item['code_text']).casefold():continue
        revision='MATCHED' if matches else ('MISMATCH' if item['hashes'] else 'UNSPECIFIED')
        eligible.append((item,revision))
    assessment=identify_system(path,expected_sha256=row['sha256'],cancelled=cancelled)
    entries=[];parts_remaining=64;locations_remaining=256
    for item,revision in eligible[page*limit:(page+1)*limit]:
        groups=[];omitted=0
        for alternative in item['alternatives']:
            parts=[]
            for code in alternative:
                if parts_remaining==0:omitted+=1;continue
                parts_remaining-=1
                _cancel(cancelled);part={'code':code,'decoded':None,'error':None,'locations':[],'mapping_status':'UNRESOLVED','mapping_reason':'','active_bank_known':False}
                if item['system_id'] not in ('nes','snes','genesis','gb','gbc'):
                    part.update(error='unsupported imported system',mapping_status='UNSUPPORTED_SYSTEM',mapping_reason='retained as source data only; no platform support inferred');parts.append(part);continue
                if item['format']!='game-genie':
                    part.update(error='unsupported imported code format: '+item['format'],mapping_status='UNSUPPORTED_FORMAT',mapping_reason='retained as source data only; not interpreted as Game Genie');parts.append(part);continue
                try:
                    decoded=decode_code(item['system_id'],code,format=item['format']);part['decoded']=decoded
                    if revision=='MISMATCH':part.update(mapping_status='REVISION_MISMATCH',mapping_reason='imported revision hash differs; no ROM locations inferred')
                    elif item['parse_status']=='INVALID':part.update(mapping_status='INVALID',mapping_reason=item['parse_reason'])
                    elif decoded.get('operation','rom-read') not in ('rom-read','rom_read','ROM_READ'):part.update(mapping_status='NOT_ROM',mapping_reason='decoded operation is not a ROM-read replacement')
                    else:
                        address=decoded.get('address',decoded.get('cpu_address'));canonical={**decoded,'address':address};locations,status,reason=_locations(system,canonical,path,assessment,profile,cancelled)
                        if len(locations)>locations_remaining:reason=(reason+'; ' if reason else '')+'candidate output budget reached; no uniqueness claim'
                        locations=locations[:locations_remaining];locations_remaining-=len(locations);part.update(locations=locations,mapping_status=status,mapping_reason=reason)
                except (ValueError,KeyError,TypeError) as exc:part.update(error=str(exc)[:512],mapping_status='INVALID_OR_UNSUPPORTED',mapping_reason=str(exc)[:512])
                parts.append(part)
            groups.append(parts)
        entries.append({**item,'source_refs':[s[:512] for s in item['source_refs'][:4]],'source_refs_truncated':len(item['source_refs'])>4 or any(len(s)>512 for s in item['source_refs']),
                        'revision_status':revision,'alternatives':groups,'decode_truncated':omitted>0,'omitted_code_parts':omitted,'gameplay_verified':False,'write_authorized':False})
    projects._measure(path,row,cancelled=cancelled);projects._measure(identity['path'],identity,cancelled=cancelled)
    # Fingerprint the complete canonical file, so changed catalogs invalidate scan caches.
    current=catalog_info(project)
    if current.get('sha256')!=(info or {}).get('sha256'):raise ValueError('catalog changed during inspection')
    return _bound_response({'ok':True,'status':'READY' if rows else 'EMPTY','source_sha256':row['sha256'],'root_sha256':identity['sha256'],'title_hint':game,'title_basis':'exact verified profile' if profile else 'source filename hint only',
            'catalog_sha256':current['sha256'],'catalog_count':len(rows or []),'total':len(eligible),'page':page,'limit':limit,'entries':entries,'gameplay_verified':False,'write_authorized':False})
