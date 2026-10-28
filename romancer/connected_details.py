"""Additional graph structure from decoded declarations, never inferred behavior."""
from .workbench_files import read_bounded

def extend_graph(row,path,definitions,nodes,add,connect,cancelled):
    if not any(definitions.get(k) for k in ('commands','levels','sound')):return False
    raw=read_bounded(path,64*1024**2,row,cancelled=cancelled);partial=False
    if definitions.get('commands'):
        from .command_editor import inspect_commands
        doc=inspect_commands(raw,definitions['commands'],row['sha256'],cancelled=cancelled)
        for script in doc['scripts']:
            parent=next((n for n in nodes if n['kind']=='commands' and n['name']==script['name'] and n['offset']==script['offset'] and n['length']==script['length']),None);previous=None
            if parent:parent['locator']={'script_id':script['id']}
            for cmd in script['commands']:
                n=add('command',script['name']+' / '+cmd['name']+' #'+str(cmd['index']),cmd['offset'],cmd['length'],'debug',{'script_id':script['id'],'command_index':cmd['index']})
                if parent:connect(parent,n,'contains_command')
                if previous:connect(previous,n,'next_stored_command')
                previous=n
                for f in cmd['fields']:
                    target=f['target_offset']
                    if target is None:continue
                    for resource in nodes[:]:
                        if resource['id']!=n['id'] and resource['offset'] is not None and resource['offset']<=target<resource['offset']+resource['length']:
                            connect(n,resource,'declared_operand_target')
    if definitions.get('levels'):
        from .level_design import inspect_level
        doc=inspect_level(raw,definitions['levels'],row['sha256'])
        for r,stored in zip(doc['rooms'],definitions['levels']['rooms']):
            collision=stored['collision']
            if collision is None:continue
            n=add('collision',r['name']+' / collision',collision['offset'],r['width']*r['height']*collision['entry_bytes'],'levels',{'room_id':r['id']})
            parent=next((n for n in nodes if n['kind']=='room' and n['locator']['room_id']==r['id']),None)
            if parent:connect(parent,n,'uses_collision')
    if definitions.get('sound'):
        from .sound_studio import inspect_sound
        doc=inspect_sound(raw,definitions['sound'],row['sha256'])
        for song in doc['songs']:
            length=song['count']*song['stride']
            parent=add('song',song['name'],song['offset'],length,'sound',{'song_id':song['id']})
            for index,event in enumerate(song['events'][:128]):
                at=event.get('offset',song['offset']+index*song['stride']);length=song['stride']
                n=add('music_event',song['name']+' / '+event.get('kind','note')+' #'+str(index),at,length,'sound',{'song_id':song['id'],'event':index});connect(parent,n,'contains_music_event')
            partial|=len(song['events'])>128
    return partial

def detail_preview(row,path,node,cancelled):
    from .research_tools import _definition
    raw=read_bounded(path,64*1024**2,row,cancelled=cancelled)
    if node['kind']=='animation':
        from .animation_layouts import animations_for
        animation=next(a for a in animations_for(row,path) if a['id']==node['locator']['animation_id'])
        return {'fields':[{'name':'Frame '+str(i+1),'value':str(f['columns'])+'×'+str(f['rows'])+' tiles · '+str(f['duration'])+' ms'} for i,f in enumerate(animation['frames'])],
            'text':'Saved exact-source arrangement. Timing is author-declared; this does not identify the game’s animation script.'}
    if node['kind'] in ('commands','command'):
        from .command_editor import inspect_commands
        doc=inspect_commands(raw,_definition(row,path,'commands'),row['sha256'],cancelled=cancelled)
        script=next(s for s in doc['scripts'] if s['id']==node['locator']['script_id']) if node.get('locator') else next(s for s in doc['scripts'] if s['name']==node['name'])
        commands=[script['commands'][node['locator']['command_index']]] if node['kind']=='command' else script['commands'][:16]
        return {'text':' · '.join(c['name'] for c in commands),'fields':[{'name':c['name']+' / '+f['name'],'value':f['value'],'offset':f['offset']} for c in commands for f in c['fields']],
            'caption':'Declared command grammar; runtime behavior is separate.','read_only':not script['editable'],'issues':script['issues']}
    if node['kind']=='collision':
        from collections import Counter
        from .level_design import inspect_level
        doc=inspect_level(raw,_definition(row,path,'levels'),row['sha256']);room=next(r for r in doc['rooms'] if r['id']==node['locator']['room_id']);names={v['value']:v['name'] for v in room.get('collision_types',[])}
        return {'fields':[{'name':names.get(value,'Raw collision '+str(value)),'value':str(count)+' cells'} for value,count in sorted(Counter(room['collision']).items())],
            'text':'Collision values are independent of the visible terrain. Named meanings come from the definition; test the resulting game behavior.'}
    if node['kind'] in ('song','music_event'):
        from .sound_studio import inspect_sound
        doc=inspect_sound(raw,_definition(row,path,'sound'),row['sha256']);song=next(s for s in doc['songs'] if s['id']==node['locator']['song_id'])
        events=[song['events'][node['locator']['event']]] if node['kind']=='music_event' else song['events'][:8]
        return {'fields':[{'name':'Event '+str(i)+' / '+k,'value':e[k]} for i,e in enumerate(events) for k in ('note','duration','volume','channel','instrument','pan') if e.get(k) is not None],
            'text':song['driver_scope'],'read_only':song.get('sequence_edit_supported') is False,'issues':song.get('issues',[])}
    return {}
