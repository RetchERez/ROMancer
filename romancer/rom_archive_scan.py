"""Offline bounded ROM-archive survey. Release output contains measured facts only."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib,io,json,math,os,re,tempfile,zipfile,zlib
from pathlib import Path,PurePosixPath
from . import rom_sample_db as db
from .release_scope import SYSTEMS
from .system_identify import identify_system
from .rom_health import check_rom
from .resource_compression import compression_candidates,decode_stream,ALLOCATION_LIMIT
from .compression_oracle import verify_encoded
from .graphics_discovery import SYSTEM_CODECS
from .asset_codecs import cell_size

EXTENSIONS={'.nes','.sfc','.smc','.md','.gen','.bin','.gb','.gbc','.sms','.rom'}
MAX_ROM=64*1024**2
MAX_ARCHIVE=2*1024**3
WINDOW=1024**2
LIMIT=32
_RESUME={}

def _safe_member(info):
    name=info.filename.replace('\\','/')
    p=PurePosixPath(name)
    return not (p.is_absolute() or any(x in ('..','') for x in p.parts) or ':' in name or info.flag_bits&1 or (info.external_attr>>16)&0o170000==0o120000)

def _label(name):
    name=PurePosixPath(name.replace('\\','/')).name
    name=Path(name).stem
    name=''.join(c for c in name if ord(c)>=32 and c not in '/\\:').strip()
    return name[:80] or 'Unnamed sample'

def _collect(paths):
    tasks=[];issues=[]
    for source in paths:
        source=Path(source).absolute()
        try:
            stat=source.stat()
            if not source.is_file() or source.is_symlink() or stat.st_size>MAX_ARCHIVE:raise ValueError('Archive is linked, missing or over the size limit.')
            with zipfile.ZipFile(source) as outer:
                if len(outer.infolist())>20000:raise ValueError('Archive has too many members.')
                total=0
                for outer_index,item in enumerate(outer.infolist()):
                    if item.is_dir():continue
                    total+=item.file_size
                    if total>MAX_ARCHIVE:raise ValueError('Archive expansion exceeds the work budget.')
                    if not _safe_member(item) or item.file_size>MAX_ROM:
                        issues.append({'archive':source.name,'member':item.filename,'reason':'Unsafe, encrypted or oversized member.'});continue
                    if Path(item.filename).suffix.lower()=='.zip':
                        try:
                            with zipfile.ZipFile(io.BytesIO(outer.read(item))) as inner:
                                if len(inner.infolist())>1000 or sum(i.file_size for i in inner.infolist())>MAX_ARCHIVE:raise ValueError('Nested archive exceeds limits.')
                                for inner_index,member in enumerate(inner.infolist()):
                                    if member.is_dir():continue
                                    if not _safe_member(member) or not 1<=member.file_size<=MAX_ROM:
                                        issues.append({'archive':source.name,'member':item.filename,'reason':'Unsafe, encrypted or oversized nested member.'});continue
                                    if Path(member.filename).suffix.lower() in EXTENSIONS:tasks.append((str(source),outer_index,inner_index,stat.st_size,stat.st_mtime_ns))
                                    elif Path(member.filename).suffix.lower()=='.zip':issues.append({'archive':source.name,'member':item.filename,'reason':'Nesting beyond one level is unsupported.'})
                        except (ValueError,OSError,zipfile.BadZipFile,RuntimeError,zlib.error,EOFError) as error:issues.append({'archive':source.name,'member':item.filename,'reason':str(error)[:240]})
                    elif Path(item.filename).suffix.lower() in EXTENSIONS:tasks.append((str(source),outer_index,None,stat.st_size,stat.st_mtime_ns))
        except (ValueError,OSError,zipfile.BadZipFile,RuntimeError,zlib.error,EOFError) as error:issues.append({'archive':source.name,'reason':str(error)[:240]})
    return tasks,issues

def _init(resume):
    global _RESUME
    _RESUME=resume

def _found(kind,offset,length,format,confidence,decoded=None):
    return {'kind':kind,'offset':offset,'length':length,'format':format,'confidence':confidence,
        'decoded_size':len(decoded) if decoded is not None else None,'decoded_sha256':hashlib.sha256(decoded).hexdigest() if decoded is not None else None}

def _record(raw,label,path):
    sha=hashlib.sha256(raw).hexdigest()
    assessed=identify_system(path,expected_sha256=sha)
    if assessed['status']!='IDENTIFIED' or assessed['system_id'] not in SYSTEMS:raise ValueError('No unique supported six-system cartridge layout.')
    system=assessed['system_id'];selected=next(c for c in assessed['candidates'] if c['layout_valid'])
    if sha in _RESUME:
        record=_RESUME[sha]
        if record['size']!=len(raw) or record['system_id']!=system or record['format']!=selected['format']:raise ValueError('Resume record differs from freshly identified source.')
        return record,True
    health=check_rom(path,expected_sha256=sha)
    checks=[]
    for item in health['checks']:
        locations=[{k:loc[k] for k in ('offset','length')} for loc in item.get('locations',[]) if type(loc.get('offset')) is int and type(loc.get('length')) is int and 0<=loc['offset']<len(raw) and 1<=loc['length']<=len(raw)-loc['offset']][:16]
        def numeric(key):
            value=item.get(key)
            return value.upper() if type(value) is str and re.fullmatch('[0-9a-fA-F]{1,16}',value) else None
        checks.append({'id':re.sub('[^a-z0-9]+','-',item['name'].lower()).strip('-')[:96],'status':item['status'],'stored':numeric('stored'),'computed':numeric('computed'),'locations':locations})
    text=[];total_text=0
    for match in re.finditer(rb'[\x20-\x7e]{5,}',raw):
        total_text+=1
        if len(text)<LIMIT:text.append(_found('text',match.start(),len(match.group()),'ascii-run','candidate'))
    unit=cell_size(SYSTEM_CODECS[system],8,8);block=unit*16
    stride=max(block,math.ceil(len(raw)/4096/unit)*unit);graphics=[];samples=0;graphics_total=0
    for offset in range(0,max(0,len(raw)-block+1),stride):
        samples+=1
        # This observes storage patterns, never object/level identity.
        chunk=raw[offset:offset+block]
        if 2<len(set(chunk))<=128:
            graphics_total+=1
            if len(graphics)<LIMIT:graphics.append(_found('graphics',offset,block,SYSTEM_CODECS[system],'candidate'))
    if system=='nes':
        region=next((r for r in selected['regions'] if r['id']=='chr-rom'),None)
        if region:
            graphics=[_found('graphics',region['offset'],min(region['length'],block),SYSTEM_CODECS[system],'format-derived')]+graphics[:LIMIT-1]
    compressed=[];compression_total=0;work_limited=False;windows=0
    for start in range(0,len(raw),WINDOW):
        windows+=1;budget={};chunk=raw[start:start+WINDOW+ALLOCATION_LIMIT]
        found=compression_candidates(chunk,start,budget=budget);work_limited|=budget.get('partial',False)
        for item in found:
            offset=item['offset']
            if offset>=start+WINDOW:continue
            compression_total+=1
            if len(compressed)>=LIMIT:continue
            decoded=decode_stream(raw[offset:offset+ALLOCATION_LIMIT],item['format'],65536)
            encoded=raw[offset:offset+decoded['consumed']]
            if not verify_encoded(encoded,item['format'],decoded['data'])['verified']:raise ValueError('Independent compression parser disagrees.')
            compressed.append(_found('compression',offset,decoded['consumed'],item['format'],'validated-encoding',decoded['data']))
    record={'sha256':sha,'crc32':f'{zlib.crc32(raw):08X}','size':len(raw),'system_id':system,'format':selected['format'],'labels':[label],
        'header_offset':selected['header_offset'],'regions':[{k:r[k] for k in ('id','kind','offset','length')} for r in selected['regions']],
        'header_numbers':{k:v for k,v in selected['metadata'].items() if type(v) in (int,bool) and v>=0},'checks':checks,
        'discoveries':sorted(text+graphics+compressed,key=lambda r:(r['offset'],r['kind'])),
        'coverage':{'whole_file_read':True,'bytes_read':len(raw),'text_runs':total_text,'graphics_stride':stride,'graphics_samples':samples,
            'compression_windows':windows,'compression_work_limited':bool(work_limited),'text_truncated':total_text>LIMIT,
            'graphics_truncated':graphics_total>LIMIT,'compression_truncated':compression_total>LIMIT}}
    return db.validate_record(record),False

def _scan_task(task):
    source,outer_index,inner_index,size,mtime=task
    outer_name=inner_name=None
    try:
        path=Path(source);stat=path.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(size,mtime):raise ValueError('Archive changed since enumeration.')
        with zipfile.ZipFile(path) as outer:
            info=outer.infolist()[outer_index];outer_name=info.filename
            if not _safe_member(info) or not 1<=info.file_size<=MAX_ROM:raise ValueError('Member changed or exceeds limits.')
            raw=outer.read(info)
        if inner_index is not None:
            with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                info=inner.infolist()[inner_index];inner_name=info.filename
                if not _safe_member(info) or not 1<=info.file_size<=MAX_ROM:raise ValueError('Nested member changed or exceeds limits.')
                raw=inner.read(info)
        name=inner_name or outer_name;label=_label(name)
        if not 1<=len(raw)<=MAX_ROM:raise ValueError('ROM exceeds the byte budget.')
        with tempfile.TemporaryDirectory(prefix='romancer-fact-scan-') as temporary:
            owned=Path(temporary)/('input'+Path(name).suffix.lower());owned.write_bytes(raw)
            record,resumed=_record(raw,label,owned)
        after=path.stat()
        if (after.st_size,after.st_mtime_ns)!=(size,mtime):raise ValueError('Archive changed during analysis.')
        return {'record':record,'label':label,'resumed':resumed}
    except (ValueError,OSError,zipfile.BadZipFile,KeyError,IndexError,RuntimeError,zlib.error,EOFError) as error:
        return {'issue':{'archive':Path(source).name,'member':inner_name or outer_name,'reason':str(error)[:240]}}

def _resume(path):
    result={}
    if path and Path(path).is_file():
        if Path(path).stat().st_size>2*db.MAX_DATABASE:raise ValueError('Resume journal exceeds the byte budget.')
        with Path(path).open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row=json.loads(line);record=db.validate_record(row['record'])
                    if row['scanner_version']==db.VERSION and row['record_sha256']==hashlib.sha256(canonical(record)).hexdigest():result[record['sha256']]=record
                except (ValueError,KeyError,TypeError):continue
    return result

def canonical(record):return json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()

def _atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.romancer-facts-',suffix='.tmp',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
    try:temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)

def scan_archives(paths,output,report,*,jobs=2,journal=None,progress=None):
    if type(jobs) is not int or not 1<=jobs<=4:raise ValueError('Use 1–4 bounded scanner workers.')
    if not paths or len(paths)>32:raise ValueError('Choose 1–32 archives.')
    output=Path(output).resolve();report=Path(report).resolve()
    journal=Path(journal).resolve() if journal else None
    protected=[Path(p).resolve() for p in paths]
    destinations=[output,report]+([journal] if journal else [])
    for index,destination in enumerate(destinations):
        for other in protected+destinations[:index]:
            if destination==other or destination.exists() and other.exists() and destination.samefile(other):
                raise ValueError('Outputs must be separate from archives and each other.')
    tasks,issues=_collect(paths);resume=_resume(journal);records={};duplicates=0;resumed=0;processed=0
    if journal:Path(journal).parent.mkdir(parents=True,exist_ok=True)
    stream=Path(journal).open('a',encoding='utf-8') if journal else None
    pool=None
    try:
        if jobs==1:_init(resume);results=map(_scan_task,tasks)
        else:pool=ProcessPoolExecutor(max_workers=jobs,initializer=_init,initargs=(resume,));results=pool.map(_scan_task,tasks,chunksize=1)
        for item in results:
            processed+=1
            if 'issue' in item:issues.append(item['issue'])
            else:
                row=item['record'];sha=row['sha256'];resumed+=bool(item['resumed'])
                if sha in records:
                    duplicates+=1;row=records[sha];row['labels']=sorted(set(row['labels']+[item['label']]))[:8]
                else:
                    row={**row,'labels':sorted(set(row['labels']+[item['label']]))[:8]};records[sha]=row
                    if stream:
                        stream.write(json.dumps({'scanner_version':db.VERSION,'record_sha256':hashlib.sha256(canonical(row)).hexdigest(),'record':row},ensure_ascii=False)+'\n');stream.flush()
            if progress:progress({'processed':processed,'total':len(tasks),'unique':len(records),'excluded':len(issues),'resumed':resumed})
    finally:
        if stream:stream.close()
        if pool:pool.shutdown(wait=True,cancel_futures=True)
    data={'schema_version':1,'scanner_version':db.VERSION,'facts_only':True,'label_origin':'supplied_filename','records':sorted(records.values(),key=lambda r:r['sha256'])}
    db.validate_database(data);encoded=(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    if len(encoded)>db.MAX_DATABASE:raise ValueError('Factual database exceeds its byte limit.')
    _atomic(output,encoded);db.load_database(output)
    result={'ok':True,'complete':not issues,'archives':len(paths),'candidate_entries':len(tasks),'processed':processed,'records':len(records),'duplicates':duplicates,'resumed':resumed,
        'excluded':len(issues),'systems':dict(sorted(Counter(r['system_id'] for r in records.values()).items())),'database_sha256':hashlib.sha256(encoded).hexdigest(),
        'rom_payloads_distributed':False,'canonical_revisions_certified':False,'gameplay_semantics_inferred':False,'issues':issues}
    _atomic(report,(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    return {k:v for k,v in result.items() if k!='issues'}

