"""Offline, revision-bound edit recipes. No commands, paths or executable hooks."""

import json
import re
from pathlib import Path
from .asset_schema import fields,label,number
from .script_schema import canonical_bytes
from .workbench_projects import _measure
from .assets import digest


def validate_recipe(recipe):
    recipe=json.loads(canonical_bytes(recipe,max_bytes=256*1024));fields(recipe,'format name source operations')
    if recipe['format']!='romancer-recipe-v1':raise ValueError('unsupported recipe format')
    label(recipe['name'],80);fields(recipe['source'],'sha256 size');number(recipe['source']['size'],1,64*1024**2)
    if type(recipe['source']['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',recipe['source']['sha256']):raise ValueError('invalid recipe source SHA-256')
    if type(recipe['operations']) is not list or not 1<=len(recipe['operations'])<=1024:raise ValueError('recipe needs1..1024 supported operations')
    for operation in recipe['operations']:
        if type(operation) is not dict:raise ValueError('invalid recipe operation')
        kind=operation.get('kind')
        if kind=='bytes':fields(operation,'kind offset before after')
        elif kind=='table':fields(operation,'kind definition changes')
        elif kind=='text':fields(operation,'kind config changes')
        else:raise ValueError('unknown recipe operation; commands and code are not supported')
    return recipe


def preview_recipe(path,recipe,*,cancelled=lambda:False):
    if cancelled():raise KeyboardInterrupt
    recipe=validate_recipe(recipe);source=_measure(path,recipe['source'],cancelled=cancelled);edits=[]
    for operation in recipe['operations']:
        if cancelled():raise KeyboardInterrupt
        kind=operation['kind']
        if kind=='bytes':edits.append({k:operation[k] for k in ('offset','before','after')})
        elif kind=='table':
            from .data_tables import table_edits
            edits.extend(table_edits(path,source['sha256'],operation['definition'],operation['changes']))
        else:
            from .resource_forms import script_schema
            from .script import inspect_script,plan_script
            schema=script_schema(path,source['sha256'],operation['config']);document=inspect_script(path,schema)
            if not document['ok']:raise ValueError('text recipe declaration cannot decode this source')
            if type(operation['changes']) is not list or len(operation['changes'])>256:raise ValueError('text recipe changes exceed the budget')
            changes=[];records={row['id']:row for row in document['records']}
            for change in operation['changes']:
                fields(change,'record_id segment before after');record=records.get(change['record_id']);number(change['segment'],0,4095)
                if record is None or change['segment']>=len(record['segments']) or record['segments'][change['segment']]['text']!=change['before']:raise ValueError('text recipe old-value precondition failed')
                changes.append({'record_id':change['record_id'],'segment':change['segment'],'text':change['after']})
            result=plan_script(path,schema,{**{k:document[k] for k in ('document_id','source_sha256','schema_sha256')},'schema_version':1,'changes':changes})
            if not result['ok']:raise ValueError(str(result.get('error','text recipe refused')))
            edits.extend({'offset':row['offset'],'before':row['before_hex'],'after':row['after_hex']} for row in result['hunks'])
    if not 1<=len(edits)<=1024:raise ValueError('recipe must change1..1024 fixed ranges')
    end=-1;total=0
    with Path(path).open('rb') as stream:
        for edit in sorted(edits,key=lambda row:row['offset']):
            if cancelled():raise KeyboardInterrupt
            number(edit['offset'],0,source['size'])
            for key in ('before','after'):
                if type(edit[key]) is not str or not re.fullmatch('(?:[0-9a-f]{2}){1,4096}',edit[key]):raise ValueError('recipe byte ranges use1..4096 lowercase hex bytes')
            length=len(edit['before'])//2
            if len(edit['before'])!=len(edit['after']) or edit['before']==edit['after']:raise ValueError('recipe edits must change bytes without resizing')
            if edit['offset']<end:raise ValueError('recipe operations overlap')
            end=edit['offset']+length;total+=length
            if end>source['size'] or total>65536:raise ValueError('recipe exceeds source or edit budget')
            stream.seek(edit['offset'])
            if stream.read(length).hex()!=edit['before']:raise ValueError('recipe old-byte precondition failed')
    _measure(path,source,cancelled=cancelled)
    if cancelled():raise KeyboardInterrupt
    return {'ok':True,'status':'PREVIEW','source':source,'recipe_id':digest(recipe),'edits':sorted(edits,key=lambda row:row['offset']),'changed_bytes':total}


def definition_document(path,sha,kind,definition):
    source=_measure(path)
    if source['sha256']!=sha:raise ValueError('definition source revision changed')
    # Run the actual inspector; imported statements gain no runtime authority.
    if kind=='tables':
        from .data_tables import inspect_table
        checked=inspect_table(path,sha,definition,0,1);definition=checked['definition']
    elif kind=='assets':
        from .assets import inspect_assets
        checked=inspect_assets(path,definition)
    elif kind=='script':
        from .script import inspect_script
        checked=inspect_script(path,definition)
    elif kind in ('levels','sound','commands'):
        from .workbench_files import read_bounded
        raw=read_bounded(path,64*1024**2,source)
        if kind=='levels':
            from .level_design import inspect_level
            checked=inspect_level(raw,definition,sha)
        elif kind=='commands':
            from .command_editor import inspect_commands
            checked=inspect_commands(raw,definition,sha)
        else:
            from .sound_studio import inspect_sound
            checked=inspect_sound(raw,definition,sha)
        definition=checked['definition']
    else:raise ValueError('choose text, graphics, tables, levels or sound definitions')
    if not checked['ok']:raise ValueError(str(checked.get('error','definition cannot inspect this revision')))
    return json.loads(canonical_bytes({'format':'romancer-definition-v1','source':source,'kind':kind,'definition':definition},max_bytes=1024**2))


def import_definition(path,sha,document):
    document=json.loads(canonical_bytes(document,max_bytes=1024**2));fields(document,'format source kind definition')
    if document['format']!='romancer-definition-v1':raise ValueError('unsupported definition format')
    _measure(path,document['source'])
    return definition_document(path,sha,document['kind'],document['definition'])


def omit_checksum_ranges(path,system,edits):
    spans={'gb': [(333, 336)], 'gbc': [(333, 336)], 'genesis': [(398, 400)]}.get(system,[])
    if system in ('snes','sms'):
        from .system_identify import identify_system
        assessment=identify_system(path);valid=[c for c in assessment['candidates'] if c['layout_valid']]
        if len(valid)!=1:raise ValueError('a unique cartridge layout is required')
        start=valid[0]['header_offset']+(28 if system=='snes' else 10)
        spans=[(start,start+(4 if system=='snes' else 2))]
    result=[]
    for edit in edits:
        before=bytes.fromhex(edit['before']);after=bytes.fromhex(edit['after']);run=None
        for i in range(len(before)+1):
            keep=i<len(before) and not any(a<=edit['offset']+i<b for a,b in spans)
            if keep and run is None:run=i
            if run is not None and (not keep or i-run==4096):
                if before[run:i]!=after[run:i]:result.append({'offset':edit['offset']+run,'before':before[run:i].hex(),'after':after[run:i].hex()})
                run=i if keep else None
    return result
