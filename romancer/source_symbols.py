"""Bounded original readers for RGBDS .sym and GNU nm BSD symbol listings.

Symbols name addresses. They do not prove a matching ROM or authorize writes.
"""
import re
from .asset_schema import label,number
from .assets import digest
from . import workbench_projects as projects
from .workbench_files import input_file,read_bounded

LIMIT=2*1024**2


def parse(text,format,system,size):
    if type(text) is not str or len(text.encode('utf-8'))>LIMIT:raise ValueError('Symbol text exceeds 2 MiB.')
    if (format=='rgbds' and system not in ('gb','gbc')) or (format=='gnu-nm' and system!='gba') or format not in ('rgbds','gnu-nm'):raise ValueError('Choose RGBDS for Game Boy / Color or GNU nm for GBA.')
    number(size,1,64*1024**2);rows=[];seen=set();ignored=0
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith((';','#')):continue
        pattern=r'\s*([0-9a-fA-F]{1,4}):([0-9a-fA-F]{4})\s+([^\s;]+)\s*(?:;.*)?' if format=='rgbds' else r'\s*([0-9a-fA-F]{8})\s+([A-Za-z?])\s+(\S+)\s*'
        match=re.fullmatch(pattern,line)
        if not match:ignored+=1;continue
        first,second,name=match.groups();label(name,160)
        address=int(second,16) if format=='rgbds' else int(first,16);bank=int(first,16) if format=='rgbds' else None
        offset=None;reason='Address is not a mapped ROM location.';domain='cpu'
        if format=='rgbds':
            if address<0x4000 and bank==0:offset=address
            elif 0x4000<=address<0x8000 and bank>0:offset=bank*0x4000+address-0x4000
            elif address>=0x8000:domain='ram-or-io';reason='CPU RAM or I/O; no ROM file offset.'
            else:reason='Bank and CPU address do not establish a ROM file location.'
        elif 0x08000000<=address<=0x0dffffff:
            if second in 'Tt' and address&1:reason='Odd code address; resolve Thumb entry semantics before navigation.'
            else:offset=address&0x01ffffff
        elif 0x02000000<=address<0x08000000:domain='ram-or-io';reason='CPU RAM or I/O; no ROM file offset.'
        if offset is not None:
            if offset>=size:offset=None;reason='Mapped location falls outside this source.'
            else:domain='rom';reason='Explicit address mapping; source relationship is user acknowledged.'
        identity=(name,address,bank)
        if identity in seen:continue
        seen.add(identity);rows.append({'name':name,'address':address,'bank':bank,'file_offset':offset,'domain':domain,'reason':reason})
        if len(rows)>65536:raise ValueError('Symbol input exceeds 65,536 entries.')
    if not rows:raise ValueError('No supported symbol records found. Use RGBDS .sym or GNU nm address/type/name output.')
    return {'symbols':rows,'ignored_lines':ignored,'rom_match_proven':False,'write_authorized':False}


class SymbolTools:
    def __init__(self,api):self.api=api
    def routes(self):
        return {'symbols.preview':('project_id artifact_id input_id format',self.preview),
                'symbols.import':('project_id artifact_id input_id format review_id acknowledged',self.apply),
                'symbols.search':('project_id artifact_id query page',self.search)}
    def _read(self,project,row,input_id,format,c):
        item,path=input_file(project,input_id,'symbols');raw=read_bounded(path,LIMIT,item,cancelled=c)
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:raise ValueError('Symbol files must use UTF-8 text.') from None
        result=parse(text,format,row['system_id'],row['size'])
        return item,result
    def _preview(self,p,c):
        project,row,path=self.api.source(p);item,result=self._read(project,row,p['input_id'],p['format'],c)
        projects._measure(path,row,cancelled=c)
        review=digest({'source':row['sha256'],'input':item['sha256'],'format':p['format'],'previous':row.get('source_symbols')})
        return project,row,item,result,review
    def preview(self,p,c):
        _,row,_,result,review=self._preview(p,c)
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'review_id':review,'symbols':result['symbols'][:50],
                'total':len(result['symbols']),'ignored_lines':result['ignored_lines'],'rom_match_proven':False,'write_authorized':False,
                'note':'This file has no ROM hash. Confirm it was generated for this exact build. RAM labels never become ROM offsets.'}
    def apply(self,p,c):
        if p['acknowledged'] is not True:raise ValueError('Confirm that these symbols belong to this exact ROM build.')
        project,row,item,result,review=self._preview(p,c)
        if review!=p['review_id']:raise ValueError('Symbol input or saved setup changed. Review it again.')
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id'])
            if owned.get('source_symbols')!=row.get('source_symbols'):raise ValueError('Symbol setup changed. Review again.')
            if c():raise KeyboardInterrupt
            owned['source_symbols']={'source_sha256':row['sha256'],'input_id':item['input_id'],'input_sha256':item['sha256'],'format':p['format'],'relationship':'user-acknowledged'}
            projects.write_json(project/'project.json',store)
        return {'ok':True,'total':len(result['symbols']),'rom_match_proven':False,'write_authorized':False}
    def search(self,p,c):
        project,row,_=self.api.source(p);label(p['query'],128,blank=True);number(p['page'],0,1311)
        saved=row.get('source_symbols')
        if not saved:return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'symbols':[],'total':0,'page':p['page'],'configured':False}
        if saved.get('source_sha256')!=row['sha256']:raise ValueError('Symbols belong to another source revision.')
        item,result=self._read(project,row,saved['input_id'],saved['format'],c)
        if item['sha256']!=saved['input_sha256']:raise ValueError('Symbol input changed. Review it again.')
        rows=[r for r in result['symbols'] if p['query'].casefold() in r['name'].casefold()];start=p['page']*50
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'symbols':rows[start:start+50],'total':len(rows),'page':p['page'],'configured':True,'rom_match_proven':False,'write_authorized':False}
