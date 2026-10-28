"""Source-bound game resource graph. Explicit relationships never imply game AI."""
from .assets import digest
from .asset_schema import label,number,fields
from .research_tools import _resources,_definition,notes_for
from . import workbench_projects as projects

MAX_NODES=32768  # Complete index of individually bounded source categories; page after filtering.
RELATIONS=('uses_graphics','uses_palette','uses_script','uses_sound','uses_table','uses_collision','uses_animation','triggers','destination','reference')
CATEGORIES=('all','known','known_resource','assets','script','tables','record','levels','room','actor','sound','song','music_event','collision','commands','command','animation','note','trace','candidate','verification','verified_source','object','graphics_capture')


def user_links(row):
    value=row.get('connected_links')
    if value is None:return []
    fields(value,'source_sha256 links')
    if value['source_sha256']!=row['sha256'] or type(value['links']) is not list or len(value['links'])>128:raise ValueError('Declared links belong to another source or exceed the budget.')
    for link in value['links']:
        fields(link,'id from to relation note')
        for key in ('id','from','to'):projects.identifier(link[key])
        label(link['note'],256,blank=True)
        if link['relation'] not in RELATIONS:raise ValueError('Unsupported declared relationship.')
    return value['links']


def graph(row,path,cancelled=lambda:False,project=None):
    resources,issues,total=_resources(row,path,cancelled,maximum=8192);nodes=[];edges=[];definitions={};by_key={}
    def add(kind,name,offset,length,editor=None,locator=None,confidence='checked_declaration'):
        if offset is not None:number(offset,0,row['size']-1);number(length,1,row['size']-offset)
        ident=digest({'sha':row['sha256'],'kind':kind,'name':name,'offset':offset,'length':length,'locator':locator})[:32]
        if ident in by_key:return by_key[ident]
        node={'id':ident,'name':str(name)[:160],'kind':kind,'offset':offset,'length':length,'editor':editor,'locator':locator,'confidence':confidence}
        if len(nodes)>=MAX_NODES:raise ValueError('Combined source metadata exceeds the connected-index budget. Use a focused editor.')
        nodes.append(node);by_key[ident]=node
        return node
    def connect(a,b,relation):
        if a['id'] in by_key and b['id'] in by_key:
            if len(edges)>=65536:raise ValueError('Combined relationship index exceeds its budget.')
            edges.append({'from':a['id'],'to':b['id'],'relation':relation})
    if project is not None:
        from .verified_games import inspect
        try:known=inspect(project,row,path,cancelled=cancelled)
        except (ValueError,OSError,KeyError):known={};issues.append({'kind':'known','message':'The existing game definition could not inspect this revision. Open its editor to check the changed data.'})
        if known.get('profile'):
            confidence='checked_revision' if known['status']=='MATCHED' else 'checked_source_history'
            for location in known.get('locations',[])[:64]:add('known',location['label'],location['offset'],location['length'],'overview',{'location':location},confidence)
            for resource in known.get('resources',[])[:32]:
                if resource.get('legacy'):continue
                if resource['kind']!='assets' and row.get('descriptors',{}).get('tables',{}).get('definition')==resource.get('definition'):continue
                if resource['kind']=='assets':
                    from .asset_codecs import cell_size
                    cfg=resource['config'];offset=cfg['offset'];length=cfg['count']*cell_size(cfg['codec'],cfg.get('width',8),cfg.get('height',8))
                else:
                    d=resource['definition'];offset=d['offset'];length=d['count']*d['stride']
                add('known_resource',resource['name'],offset,length,'assets' if resource['kind']=='assets' else 'tables',{'resource_id':resource['id']},confidence)
    for r in resources:
        if cancelled():raise KeyboardInterrupt
        add(r['kind'],r['name'],r['offset'],r['length'],r['editor'])
    for kind in ('assets','tables','levels','sound','commands'):
        if not row.get('descriptors',{}).get(kind) or any(i['kind']==kind for i in issues):continue
        try:definitions[kind]=_definition(row,path,kind)
        except (ValueError,KeyError,TypeError):continue
    assets=definitions.get('assets')
    if assets:
        def asset_node(group,r):return next((n for n in nodes if n['kind']=='assets' and n['name']==r['id']+' / '+group),None)
        for tilemap in assets['tilemaps']:
            a=asset_node('tilemaps',tilemap)
            for group,key,relation in [('bitmaps','bitmap_id','uses_tiles'),('palettes','palette_id','uses_palette')]:
                r=next((r for r in assets[group] if r['id']==tilemap[key]),None);b=asset_node(group,r) if r else None
                if a and b:connect(a,b,relation)
    d=definitions.get('tables')
    if d:
        from .data_tables import inspect_table
        inspected=inspect_table(path,row['sha256'],d,0,1);catalog={r['index']:r for r in inspected['row_catalog']}
        parent=next(n for n in nodes if n['kind']=='tables')
        for index in range(len(catalog) if catalog else min(d['count'],256)):
            name=catalog.get(index,{}).get('label','Record '+str(index))
            child=add('record',name,d['offset']+index*d['stride'],d['stride'],'tables',{'row':index})
            connect(parent,child,'contains_record')
    levels=definitions.get('levels')
    if levels:
        from .studio_discovery import resource_relationships
        from .workbench_files import read_bounded
        doc=resource_relationships(read_bounded(path,64*1024**2,row,cancelled=cancelled),{'levels':levels},row['sha256'])
        mapping={r['id']:next((n for n in nodes if n['kind']=='levels' and n['name']==r['name']),None) for r in doc['nodes']}
        for edge in doc['edges']:
            if mapping.get(edge['from']) and mapping.get(edge['to']):connect(mapping[edge['from']],mapping[edge['to']],edge['relation'])
        from .level_design import inspect_level
        level=inspect_level(read_bounded(path,64*1024**2,row,cancelled=cancelled),levels,row['sha256'])
        for room,storage in zip(level['rooms'],levels['rooms']):
            parent=add('room',room['name'],storage['terrain']['offset'],room['width']*room['height']*storage['terrain']['entry_bytes'],'levels',{'room_id':room['id']})
            terrain=mapping.get('level:'+room['id']+' terrain')
            if terrain:connect(parent,terrain,'uses_terrain')
            object_def=storage['objects']
            if object_def:
                metadata={r['index']:r for r in room.get('object_metadata',[])}
                for index,obj in enumerate(room['objects'][:64]):
                    child=add('actor',metadata.get(index,{}).get('name','Object '+str(index)),object_def['offset']+index*object_def['stride'],object_def['stride'],'levels',{'room_id':room['id'],'object':index})
                    connect(parent,child,'contains_object')
    from .connected_details import extend_graph
    extra_partial=extend_graph(row,path,definitions,nodes,add,connect,cancelled)
    from .animation_layouts import animations_for
    for animation in animations_for(row,path):
        bitmap=next(b for b in animation['schema']['bitmaps'] if b['id']==animation['bitmap_id'])
        n=add('animation',animation['name'],bitmap['offset'],bitmap['length'],'assets',{'animation_id':animation['id']})
        for other in nodes[:]:
            if other['kind']=='assets' and other['offset']==bitmap['offset']:connect(n,other,'uses_graphics')
    for note in notes_for(row):add('note',note['title'],note['offset'],note['length'],'resources',{'note_id':note['id']},'user_note')
    if project is not None:
        from .gameplay_traces import saved_traces
        try:traces=saved_traces(project,row)
        except (ValueError,OSError,KeyError):traces=[];issues.append({'kind':'trace','message':'Saved traces could not be authenticated. Capture a fresh trace.'})
        for item in reversed(traces):
            r=item['report'];trace=add('trace',r['name'],None,0,'playtest',{'trace_id':item['trace_id']},'native_frame' if item['runtime_trusted'] else 'historical_frame')
            for index,match in enumerate(r['matches']):
                candidate=add('candidate','Tile at '+hex(match['offset'])+' / '+str(match['x'])+', '+str(match['y']),match['offset'],match['length'],'assets',{'trace_id':item['trace_id'],'match':index},'pixel_candidate')
                connect(trace,candidate,'pixel_match')
    if project is not None:
        from .visual_source_tools import saved_verifications
        try:verifications=saved_verifications(project,row)
        except (ValueError,OSError,KeyError):verifications=[];issues.append({'kind':'verification','message':'Source verification could not be authenticated. Run a fresh verification.'})
        for item in reversed(verifications):
            r=item['report']
            trusted=item['runtime_trusted'];confidence='causal_replay' if trusted and r['verified_matches'] else 'verification_result' if trusted else 'historical_frame'
            proof=add('verification','Source check / '+r['status'],None,0,'playtest',{'verification_id':item['verification_id'],'trace_id':r['trace_id']},confidence)
            trace=next((n for n in nodes if n['kind']=='trace' and n['locator']['trace_id']==r['trace_id']),None)
            if trace:connect(trace,proof,'source_verification')
            for m in r['verified_matches']:
                source=add('verified_source','Verified tile at '+hex(m['offset'])+' / '+str(m['x'])+', '+str(m['y']),m['offset'],m['length'],'assets',{'verification_id':item['verification_id'],'match_id':m['match_id'],'trace_id':r['trace_id']},confidence)
                connect(proof,source,'verified_visual_source')
    from .object_workbench import objects_for
    from .asset_codecs import cell_size
    for obj in objects_for(row):
        objdef=obj['definition'];cfg=objdef['config'];b=add('object',obj['name'],cfg['offset'],cfg['count']*cell_size(cfg['codec'],8,8),'assets',{'object_id':obj['id']},'checked_declaration')
        for ref in obj['parts']:
            source=next((n for n in nodes if n['kind']=='verified_source' and n['locator']['verification_id']==ref['verification_id'] and n['locator']['match_id']==ref['match_id']),None)
            if source:connect(b,source,'uses_verified_part')
    if project is not None:
        from .graphics_access import capture_ids
        from .workbench_evidence import load_evidence
        for ident in capture_ids(row):
            r=load_evidence(project,ident,'runtime');report=r['report']
            if report.get('source_sha256')!=row['sha256'] or report.get('artifact_id')!=row['artifact_id']:raise ValueError('Graphics capture index belongs to another source.')
            if report.get('graphics_snapshot'):
                access=add('graphics_capture','Native graphics / '+ident[:8],None,0,'playtest',{'evidence_id':ident},'native_accesses' if r['runtime_trusted'] else 'historical_frame')
                tid=report.get('investigation_link',{}).get('graphics_trace_id')
                trace=next((n for n in nodes if n['kind']=='trace' and n['locator']['trace_id']==tid),None)
                if trace:connect(trace,access,'replayed_graphics_accesses')
    try:
        for link in user_links(row):
            if link['from'] not in by_key or link['to'] not in by_key:issues.append({'kind':'link','message':'A declared link refers to a changed resource. Recreate it for the current layout.'});continue
            edges.append({'from':link['from'],'to':link['to'],'relation':link['relation'],'confidence':'user_declared','link_id':link['id'],'note':link['note']})
    except (ValueError,KeyError,TypeError):issues.append({'kind':'link','message':'Declared links could not be validated for this source.'})
    projects._measure(path,row,cancelled=cancelled)
    return {'nodes':nodes,'edges':edges,'issues':issues,'partial':extra_partial or total>len(resources) or (d is not None and not catalog and d['count']>256),'game_semantics_inferred':False}


def neighbors(model,node):
    """Compute byte overlap only around a requested node, avoiding a quadratic graph."""
    edges=[e for e in model['edges'] if node['id'] in (e['from'],e['to'])];seen={(min(e['from'],e['to']),max(e['from'],e['to']),e['relation']) for e in edges}
    if node['offset'] is not None:
        for other in model['nodes']:
            if other['id']==node['id'] or other['offset'] is None or other['kind']==node['kind'] or 'record' in (node['kind'],other['kind']):continue
            if node['offset']<other['offset']+other['length'] and other['offset']<node['offset']+node['length']:
                candidate=node if node['kind']=='candidate' else other if other['kind']=='candidate' else None
                storage=other if candidate is node else node
                contains=candidate is not None and storage['offset']<=candidate['offset'] and candidate['offset']+candidate['length']<=storage['offset']+storage['length']
                relation='located_in' if contains else 'shares_storage';key=(min(node['id'],other['id']),max(node['id'],other['id']),relation)
                start,end=(candidate['id'],storage['id']) if contains else (min(node['id'],other['id']),max(node['id'],other['id']))
                if key not in seen:edges.append({'from':start,'to':end,'relation':relation});seen.add(key)
    return edges


class ConnectedGameTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'gameview.graph':('project_id artifact_id query kind page',self.graph),'gameview.detail':('project_id artifact_id node_id',self.detail),'gameview.link':('project_id artifact_id from_id to_id relation note',self.link),'gameview.unlink':('project_id artifact_id link_id',self.unlink)}
    def link(self,p,c):
        project,row,_=self.api.source(p);_,_,model=self._graph(p,c)
        if p['relation'] not in RELATIONS:raise ValueError('Choose a supported declared relationship.')
        label(p['note'],256,blank=True);ids={n['id'] for n in model['nodes']}
        if p['from_id'] not in ids or p['to_id'] not in ids or p['from_id']==p['to_id']:raise ValueError('Choose two different current resources.')
        value={'from':p['from_id'],'to':p['to_id'],'relation':p['relation'],'note':p['note']};value['id']=digest({'sha':row['sha256'],**value})[:32]
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);links=[r for r in user_links(owned) if r['id']!=value['id']]
            if len(links)>=128:raise ValueError('This source already has 128 declared links.')
            if c():raise KeyboardInterrupt
            owned['connected_links']={'source_sha256':row['sha256'],'links':links+[value]};projects.write_json(project/'project.json',store)
        return {'ok':True,'link_id':value['id'],'confidence':'user_declared','rom_written':False}
    def unlink(self,p,c):
        project,row,_=self.api.source(p);projects.identifier(p['link_id'])
        with projects.locked(project) as store:
            owned=next(r for r in store['sources']+store['builds'] if r['artifact_id']==row['artifact_id']);links=user_links(owned);kept=[r for r in links if r['id']!=p['link_id']]
            if len(kept)==len(links):raise ValueError('This declared link no longer exists.')
            if c():raise KeyboardInterrupt
            owned['connected_links']={'source_sha256':row['sha256'],'links':kept};projects.write_json(project/'project.json',store)
        return {'ok':True,'rom_written':False}
    def _graph(self,p,c):
        project,row,path=self.api.source(p);from .release_scope import require_supported
        require_supported(row);return row,path,graph(row,path,c,project)
    def graph(self,p,c):
        label(p['query'],128,blank=True);number(p['page'],0,1024)
        if p['kind'] not in CATEGORIES:raise ValueError('Choose an available resource category.')
        row,_,model=self._graph(p,c);query=p['query'].casefold();rows=[r for r in model['nodes'] if p['kind'] in ('all',r['kind']) and query in r['name'].casefold()];start=p['page']*50
        selected=rows[start:start+50];page_edges={}
        for node in selected:
            if c():raise KeyboardInterrupt
            for edge in neighbors(model,node)[:32]:page_edges[(edge['from'],edge['to'],edge['relation'])]=edge
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'system_id':row['system_id'],**model,'nodes':selected,'edges':list(page_edges.values())[:256],'connections_truncated':len(page_edges)>256,'total':len(rows),'page':p['page'],'write_authorized':False}
    def detail(self,p,c):
        projects.identifier(p['node_id']);row,path,model=self._graph(p,c);node=next((r for r in model['nodes'] if r['id']==p['node_id']),None)
        if node is None:raise ValueError('This resource changed or is unavailable. Refresh the Game view.')
        all_related=neighbors(model,node);related=all_related[:32];ids={e['from'] for e in related}|{e['to'] for e in related};preview={}
        if node['kind'] in ('commands','command','collision','song','music_event','animation'):
            from .connected_details import detail_preview
            preview=detail_preview(row,path,node,c)
        if node['kind']=='record':
            from .data_tables import inspect_table
            d=_definition(row,path,'tables');doc=inspect_table(path,row['sha256'],d,node['locator']['row'],1)
            preview={'fields':[{'name':r['field'],'value':r['value'],'offset':r['offset']} for r in doc['rows'][0]['cells']]}
        if node['kind']=='script':
            from .script import inspect_script
            doc=inspect_script(path,_definition(row,path,'script'));record=next(r for r in doc['records'] if r['offset']==node['offset'] and r['id']==node['name'])
            preview={'text':''.join(s.get('text','['+s.get('kind','control')+']') for s in record['segments'])[:2000],'caption':'Decoded declared text. Control codes remain protected in the text editor.'}
        if node['kind']=='assets':preview=self._asset_preview(row,path,node)
        if node['kind'] in ('room','actor'):preview=self._room_preview(row,path,node,c)
        if node['kind']=='note':preview={'text':next(n['text'] for n in notes_for(row) if n['id']==node['locator']['note_id'])}
        if node['kind']=='known':
            location=node['locator']['location'];preview={'text':location.get('meaning',''),'caption':location.get('storage',''),'fields':[{'name':'Stored example','value':location.get('example','')}]}
        if node['kind'] in ('trace','candidate'):
            trace=self.api.traces.get({**p,'trace_id':node['locator']['trace_id']},c)
            preview={'png_base64':trace['crop_png_base64'],'caption':'Measured gameplay region. Pixel matches are candidates; source transfers were not observed.','runtime_trusted':trace['runtime_trusted'],'trace_id':trace['trace_id'],'frame':trace['frame'],'region':trace['region'],'coverage':trace['coverage']}
        if node['kind'] in ('verification','verified_source'):
            proof=self.api.visual_sources.get({**p,'verification_id':node['locator']['verification_id']},c)
            chosen=next((m for m in proof['verified_matches'] if m['match_id']==node['locator'].get('match_id')),proof['verified_matches'][0] if proof['verified_matches'] else None)
            preview={'runtime_trusted':proof['runtime_trusted'],'text':proof['reason'],'caption':'Authenticated causal source test. CPU/DMA transfers were not observed.','fields':[{'name':'Result','value':proof['status']}]}
            if chosen:preview.update(png_base64=chosen['visual'][0]['original_png_base64'],fields=preview['fields']+[{'name':'Verified opaque pixels','value':str(chosen['verified_pixels'])+' / '+str(chosen['opaque_pixels'])},{'name':'Complete opaque placement','value':str(chosen['complete_placement'])}])
        if node['kind']=='object':
            obj=self.api.objects.get({**p,'object_id':node['locator']['object_id']},c)
            preview={'object_id':obj['object_id'],'text':'Saved multi-part layout. '+('Verified in its recorded replay.' if obj['source_dependency_verified'] else 'Author-checked declaration; fresh execution proof is unavailable.'),'source_dependency_verified':obj['source_dependency_verified']}
            trace_id=obj['object'].get('trace_id')
            if trace_id:
                try:
                    trace=self.api.traces.get({**p,'trace_id':trace_id},c)
                    preview.update(png_base64=trace['crop_png_base64'],caption='Captured scene; selected object layout opens with source-tile uses.')
                except (ValueError,OSError):preview['caption']='Captured scene unavailable; the saved exact-revision layout can still be opened.'
        if node['kind']=='graphics_capture':
            capture=self.api.graphics_access.get({**p,'evidence_id':node['locator']['evidence_id'],'offset':0,'limit':1},c)
            preview={'evidence_id':capture['evidence_id'],'png_base64':capture.get('scene',{}).get('png_base64'),'caption':'Recorded native accesses and end-of-capture video memory; read/write adjacency is not dataflow.','runtime_trusted':capture['runtime_trusted'],'fields':[{'name':'Recorded events','value':capture['total_events']}]}
        raw=b''
        if node['offset'] is not None:
            with path.open('rb') as f:f.seek(node['offset']);raw=f.read(min(node['length'],128))
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'node':node,'connections':related,'connections_total':len(all_related),'connections_truncated':len(all_related)>32,'neighbors':[r for r in model['nodes'] if r['id'] in ids and r['id']!=node['id']],'preview':preview,'hex_preview':raw.hex(),'preview_bytes':len(raw),'write_authorized':False}
    def _room_preview(self,row,path,node,c):
        from .level_design import inspect_level
        from .workbench_files import read_bounded
        from .visual_checks import _png
        from PIL import Image
        d=_definition(row,path,'levels');doc=inspect_level(read_bounded(path,64*1024**2,row,cancelled=c),d,row['sha256']);room=next(r for r in doc['rooms'] if r['id']==node['locator']['room_id'])
        bw,bh=doc['block_width'],doc['block_height'];width,height=room['width']*bw*8,room['height']*bh*8;image=Image.new('RGB',(width,height));pixels=image.load()
        for i,value in enumerate(room['terrain']):
            if c():raise KeyboardInterrupt
            for part,tile_id in enumerate(doc['metatiles'][value]):
                for pos,color in enumerate(doc['tiles'][tile_id]):pixels[(i%room['width'])*bw*8+(part%bw)*8+pos%8,(i//room['width'])*bh*8+(part//bw)*8+pos//8]=tuple(doc['palette'][color])
        selected=node['locator'].get('object');fields=[]
        if selected is not None:
            from PIL import ImageDraw
            obj=room['objects'][selected];fields=[{'name':k,'value':v} for k,v in obj.items()]
            if 'x' in obj and 'y' in obj:ImageDraw.Draw(image).rectangle((obj['x']*bw*8,obj['y']*bh*8,(obj['x']+1)*bw*8-1,(obj['y']+1)*bh*8-1),outline=(255,220,40),width=2)
        image.thumbnail((480,320),Image.Resampling.NEAREST)
        return {'png_base64':_png(image.tobytes(),image.width,image.height),'caption':'Decoded declared room layout'+(' · selected object outlined' if selected is not None else ''),'fields':fields}
    def _asset_preview(self,row,path,node):
        from .assets import inspect_assets
        from .visual_checks import _png
        doc=inspect_assets(path,_definition(row,path,'assets'))
        if not doc.get('ok'):raise ValueError(doc.get('error','Graphics could not be inspected.'))
        bitmap=next((r for r in doc['bitmaps'] if r['offset']==node['offset'] and r['id']+' / bitmaps'==node['name']),None)
        if bitmap:
            cells=bitmap['cells'][:32];w,h=bitmap['width'],bitmap['height'];columns=min(8,len(cells));rows=(len(cells)+columns-1)//columns;pixels=bytearray(columns*w*rows*h*3)
            maximum=max(1,max(v for cell in cells for v in cell['pixels']))
            for i,cell in enumerate(cells):
                for pos,v in enumerate(cell['pixels']):
                    at=(((i//columns)*h+pos//w)*columns*w+(i%columns)*w+pos%w)*3;shade=round(v*255/maximum);pixels[at:at+3]=bytes([shade]*3)
            return {'png_base64':_png(bytes(pixels),columns*w,rows*h),'caption':'Decoded stored tiles, grayscale preview; open the editor to choose the declared palette.','displayed_cells':len(cells),'total_cells':bitmap['count']}
        palette=next((r for r in doc['palettes'] if r['offset']==node['offset']),None)
        if palette:return {'colors':[r['rgb'] for r in palette['entries'][:64]],'caption':'Decoded stored palette colors.'}
        return {'caption':'Open the graphics editor for the assembled map preview.'}
