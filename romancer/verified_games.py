"""Small, sourced editing definitions; exact originals and explicit owned lineage.

Definitions describe tested locations, not whole-game compatibility. Original
game files stay local. Every write uses the existing byte planner.
"""
from pathlib import Path
import re
from . import workbench_projects as projects
from .asset_schema import fields, number


PROFILES=({'id': 'rastan-sms', 'name': 'Rastan', 'system': 'sms', 'size': 262144, 'sha256': '7e310ada1a09ace30e9dd8f5738f095c0ec7821edc225221cbba130fb8cbadb3', 'reference': '/user-guide/index.html#rastan-blobs', 'scope': 'First humanoid enemy literal graphics and one observed 16×32 assembly. The three lower-body blob frames were checked in the edited output; other enemies, collision and AI are separate.', 'offsets': [(65536, 1920, 'First humanoid enemy graphics')]}, {'id': 'ffl2-usa', 'name': 'Final Fantasy Legend II', 'system': 'gb', 'size': 262144, 'sha256': '2d89231f9e264a024d634bcf7d00de5a66d8a45f6f4ca33e1fc1602a35b9840b', 'reference': 'https://github.com/daid/FFL2-Disassembly/tree/a5c17a90d87d102a9a45d287042c9a36ffd06f97', 'scope': 'ROM-decoded opening bedroom and stool placement. Five floor positions preserve collision; exits and other room commands are protected. Test each new build.', 'offsets': [(131957, 3, 'Bedroom stool map command')]}, {'id': 'dejavu-casebooks-usa', 'name': 'Deja Vu I & II - The Casebooks of Ace Harding', 'system': 'gbc', 'size': 1048576, 'sha256': 'b3ca745829e018513eae8d760484140a031c0f031e1881fca3374a9194e3ecac', 'reference': 'https://github.com/Hoshiruna/djv1-2disasm/tree/b7ae8ca791ba31b956e015d3c87f3acc47f0fb42', 'scope': 'Startup and first Case Book 1 scene UI palette7. Later scenes use their own palettes.', 'offsets': [(164632, 8, 'Startup casebook interface colors'), (165124, 8, 'Opening scene interface colors')]}, {'id': 'castlevania-usa', 'name': 'Castlevania', 'system': 'nes', 'size': 131088, 'sha256': '55bcab0d9efc33a9d9efc90f2c3c4ab12f3221a44b1f357e6c6202a456399aa8', 'reference': 'https://github.com/rumbleminze/castlevania-snes/blob/main/src/bank7.asm', 'scope': 'Starting spare lives; both initialization constants. Verified HUD 3 to 9.', 'offsets': [(116790, 1, 'Starting spare lives'), (117051, 1, 'Mirrored initialization')]}, {'id': 'chrono-trigger-usa', 'name': 'Chrono Trigger', 'system': 'snes', 'size': 4194304, 'sha256': '06d1c2b06b716052c5596aaa0c2e5632a027fee1a9a28439e509f813c30829a9', 'reference': 'https://github.com/dscotton/ct_disassembly/blob/main/data/item_weapon_stats.asm', 'scope': 'Wood Sword weapon power. Power 3 to 30 produced displayed attack 8 to 23; the game computes final attack.', 'offsets': [(787047, 1, 'Wood Sword power')]}, {'id': 'immortal-ue', 'name': 'The Immortal', 'system': 'genesis', 'size': 1048576, 'sha256': 'b60aa52e46a199f755a1eb99daea543c468acf07d83624c85a84cdd14b786375', 'reference': 'https://github.com/sewave/translations/blob/master/smd/immortalthesmd/immortalthesmd.hex', 'scope': 'New-game menu prompt, up to nine ASCII characters. Includes the documented game-specific ROM-check adjustment.', 'offsets': [(19995, 9, 'New-game prompt'), (1048522, 2, 'Game-specific integrity adjustment')]})

BYTE_NOTES={'rastan-sms': [{'storage': '60 literal 8×8 row-planar 4bpp tiles, 32 bytes each', 'meaning': 'The first humanoid enemy graphics occupy this checked range. An observed pose joins tiles 30,32,31,33,52,54,53,55 as two columns and four rows. Palette bytes, collision and AI are not in this definition.', 'example': 'Open first enemy sprites to edit the assembled pose. Stored color indices are shown in labeled grayscale until a palette is declared.', 'evidence': 'ROMancer native original/build frame comparison at frame841 changed only enemy pixels in the measured opening scene. The guide retains the source/build hashes and actual editor captures.'}], 'ffl2-usa': [{'storage': 'Three-byte packed point command', 'meaning': 'Places tile1D (stool) in map0265. 17 CE encodes (14,31); 18 0E encodes (14,32). Exit, story window and collision values are preserved.', 'example': '17 CE 1D to 18 0E 1D.', 'evidence': 'Original room header486B, map0265 and tileset0B were observed in native WRAM. Each edited build needs its own playtest.'}], 'dejavu-casebooks-usa': [{'storage': 'Four little-endian RGB555 colors', 'meaning': 'Startup palette7 used by the casebook interface. This is stored color data.', 'example': 'Original or parchment interface palette.', 'evidence': 'The 64-byte native target palette matches the original startup and first-scene ROM blocks.'}, {'storage': 'Four little-endian RGB555 colors', 'meaning': 'First Case Book 1 scene palette7. Updated with the startup copy; later scene palettes remain unchanged.', 'example': 'Original or parchment interface palette.', 'evidence': 'Scene loading replaces all64 colors, so both observed copies are changed together.'}], 'castlevania-usa': [{'storage': 'Unsigned 8-bit counter', 'meaning': 'Initialization counter includes the current life. Spare lives = stored value minus 1. Both initialization constants must agree.', 'example': '04 = 3 spare lives; 0A = 9 spare lives.', 'evidence': 'Native HUD changed from P-03 to P-09 after a new start.'}, {'storage': 'Unsigned 8-bit counter', 'meaning': 'Second guarded initialization constant for the same life counter. Keep it equal to 0x1C836.', 'example': '04 to 0A in both locations.', 'evidence': 'Both code locations were checked against the exact original and tested together.'}], 'chrono-trigger-usa': [{'storage': 'Unsigned 8-bit weapon power', 'meaning': 'Wood Sword base weapon power. This is an input to the game formula, not the final displayed attack stat.', 'example': '03 = power 3; 1E = power 30.', 'evidence': "The tested build changed displayed attack from 8 to 23 on Crono's equipment screen."}], 'immortal-ue': [{'storage': 'Fixed 9-byte ASCII text slot', 'meaning': 'New-game prompt. Shorter text is padded with spaces. The following % delimiter at 0x4E24 is preserved.', 'example': 'New game? to New hack?; neither text changes the slot length.', 'evidence': 'The changed prompt was visible after native boot with the required integrity adjustment.'}, {'storage': '68000 opcode word, 2-byte patch', 'meaning': 'Game-specific ROM check adjustment: replace the guarded instruction start with RTS (4E 75). The named plan also repairs the standard Genesis checksum.', 'example': '0C 80 to 4E 75 at this exact guarded revision.', 'evidence': 'Standard header checksum repair alone produced a black screen; the explicit adjustment allowed the tested menu edit to boot.'}]}


def _resolve(project,row,cancelled):
    current=row;seen=set()
    for _ in range(64):
        if current.get('layout_changed'):return None,None
        if current['artifact_id'] in seen:raise ValueError('cyclic game-definition ancestry')
        seen.add(current['artifact_id']);projects._measure(current['path'],current,cancelled=cancelled)
        if current['kind']=='source':
            profile=next((p for p in PROFILES if p['sha256']==current['sha256'] and p['size']==current['size']),None)
            if profile and (row['size']!=profile['size'] or row.get('system_id')!=profile['system']):return None,None
            return profile,current
        if not current.get('source_id'):return None,None
        current=projects.artifact(project,current['source_id'])
    raise ValueError('game-definition ancestry exceeds 64 builds')


def _read(path,offset,length):
    with Path(path).open('rb') as stream:stream.seek(offset);raw=stream.read(length)
    if len(raw)!=length:raise ValueError('verified game location exceeds the selected ROM')
    return raw


def _model(profile,root,path):
    identifier=profile['id']
    if identifier=='rastan-sms':return []
    if identifier=='ffl2-usa':
        from .verified_room import room_visual
        visual=room_visual(path,root['path'])
        return [{'id':'room_layout','label':'Opening-bedroom stool','type':'choice','value':visual['value'],'options':visual['options']}]
    if identifier=='dejavu-casebooks-usa':
        rows=[_read(path,o,n) for o,n,_ in profile['offsets']]
        original=bytes.fromhex('0000027e1e007f03');parchment=bytes.fromhex('0000285695155d5f')
        if rows not in ([original,original],[parchment,parchment]):raise ValueError('opening interface palette guard differs; inspect this build')
        return [{'id':'palette_style','label':'Opening casebook interface','type':'choice','value':'original' if rows[0]==original else 'parchment','options':[['original','Original colors'],['parchment','Parchment colors']]}]
    if identifier=='castlevania-usa':
        constants=[]
        for offset,_,_ in profile['offsets']:
            raw=_read(path,offset-1,4)
            if raw[0]!=0xa9 or raw[2:]!=b'\x85\x2a':raise ValueError('starting-lives code guard differs; inspect the selected build')
            constants.append(raw[1])
        if constants[0]!=constants[1]:raise ValueError('mirrored starting-lives constants differ; inspect both locations')
        number(constants[0],2,100)
        return [{'id':'spare_lives','label':'Starting spare lives','type':'integer','min':1,'max':99,'value':constants[0]-1}]
    if identifier=='chrono-trigger-usa':
        return [{'id':'weapon_attack','label':'Wood Sword power','type':'integer','min':1,'max':255,'value':_read(path,0xc0267,1)[0]}]
    if identifier=='immortal-ue':
        slot=_read(path,0x4e1b,10);check=_read(path,0xfffca,10)
        if slot[-1]!=37 or any(c<32 or c>126 or c==37 for c in slot[:-1]):raise ValueError('menu text or protected terminator differs')
        if check not in (bytes.fromhex('0c80fede808566024e75'),bytes.fromhex('4e75fede808566024e75')):raise ValueError('game-specific integrity code guard differs')
        return [{'id':'menu_text','label':'New-game menu text','type':'text','max_length':9,'value':slot[:-1].decode('ascii').rstrip()}]
    raise ValueError('no enabled verified editor for this game definition')


def palette_visuals(profile,root,path):
    if profile['id']=='ffl2-usa':
        from .verified_room import room_visual
        return room_visual(path,root['path'])
    if profile['id'] not in ('dejavu-casebooks-usa',):return None
    def colors(raw):
        return [[round(((int.from_bytes(raw[i:i+2],'little')>>shift)&31)*255/31) for shift in (0,5,10)] for i in range(0,len(raw),2)]
    rows=[]
    for offset,length,label in profile['offsets']:
        original=_read(root['path'],offset,length);current=_read(path,offset,length)
        variant={'parchment':colors(bytes.fromhex('0000285695155d5f'))}
        rows.append({'name':label,'offset':offset,'current':colors(current),'original':colors(original),**variant})
    return {'kind':'rgb555-palettes','palettes':rows,'scope':'Literal stored colors; native scene rendering is not predicted.'}


def resource_definitions(profile):
    if profile['id']=='rastan-sms':return [{'id':'first-enemy-sprites','name':'first enemy sprites','kind':'assets',
        'reference':profile['reference'],'scope':profile['scope'],
        'config':{'system_id':'sms','offset':0x10000,'count':60,'codec':'tile8-rowplanar4-msb-v1','width':8,'height':8},
        'sprite_layout':{'first':0,'columns':2,'rows':4,'order':'rows','indices':[30,32,31,33,52,54,53,55]}}]
    if profile['id']!='chrono-trigger-usa':return []
    from .chrono_tables import resource_definitions as named_definitions
    resources=named_definitions()
    # Preserve the public legacy resource ID and its original numeric indexing.
    return [r for r in resources if r.get('legacy')]+[r for r in resources if not r.get('legacy')]


def maps(api,parameters,operation,*,cancelled=lambda:False):
    from . import ffl2_maps
    from .asset_schema import number
    project,row,path=api.source(parameters);profile,root=_resolve(project,row,cancelled)
    if profile is None or profile['id']!='ffl2-usa':
        raise ValueError('game maps require the exact supported source or an owned build descended from it')
    identity={'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],
              'verified_original_sha256':root['sha256'],'profile_id':profile['id']}
    if operation=='catalog':
        number(parameters['limit'],1,24)
        result=ffl2_maps.catalog(path,root['path'],offset=parameters['offset'],limit=parameters['limit'],
                                 query=parameters['query'],cancelled=cancelled)
    elif operation=='inspect':
        result=ffl2_maps.inspect_room(path,root['path'],parameters['header'],state=parameters['state'],cancelled=cancelled)
    else:
        result=ffl2_maps.plan_edits(path,root['path'],parameters['header'],parameters['changes'],state=parameters.get('state'),cancelled=cancelled)
        planned=api._integrity_plan({'project_id':parameters['project_id'],'artifact_id':row['artifact_id'],
                                     'edits':result['edits']},cancelled)
        result={**result,**planned}
    projects._measure(path,row,cancelled=cancelled);projects._measure(root['path'],root,cancelled=cancelled)
    return {**result,**identity,'ok':True}


def configure_resource(api,parameters,*,cancelled=lambda:False):
    project,row,path=api.source(parameters);profile,root=_resolve(project,row,cancelled)
    if profile is None:raise ValueError('no verified resource definitions for this exact source revision')
    resource=next((r for r in resource_definitions(profile) if r['id']==parameters['resource_id']),None)
    if resource is None:raise ValueError('unknown verified resource definition')
    if resource.get('kind')=='assets':
        result=api._declare_resource({'project_id':parameters['project_id'],'artifact_id':row['artifact_id'],'config':resource['config']},cancelled,'assets')
        return {**result,'resource_kind':'assets','sprite_layout':resource['sprite_layout'],'reference':resource['reference'],'definition_scope':resource['scope']}
    result=api._tables_save({'project_id':parameters['project_id'],'artifact_id':row['artifact_id'],'definition':resource['definition']},cancelled)
    return {**result,'reference':resource['reference'],'definition_scope':resource['scope']}


def inspect(project,row,path,*,cancelled=lambda:False):
    profile,root=_resolve(project,row,cancelled)
    if profile is None:return {'ok':True,'status':'UNSUPPORTED','profile':None,'artifact_id':row['artifact_id'],'source_sha256':row['sha256']}
    availability=None
    try:model=_model(profile,root,path);visual=palette_visuals(profile,root,path)
    except ValueError as error:
        if profile['id']!='ffl2-usa':raise
        # Broader map edits can invalidate the deliberately narrow stool widget.
        # Keep the exact identity visible; the separate map service applies its
        # own structural guards rather than treating this as an unknown game.
        model=[];visual=None;availability=str(error)
    from .game_knowledge import reference_knowledge
    knowledge=reference_knowledge(profile['id'],root['sha256'],row['kind']!='source')
    projects._measure(path,row,cancelled=cancelled)
    if visual:projects._measure(root['path'],root,cancelled=cancelled)
    return {'ok':True,'status':'MATCHED' if row['kind']=='source' else 'DERIVED','artifact_id':row['artifact_id'],
            'source_sha256':row['sha256'],'verified_original_sha256':root['sha256'],'gameplay_verified':False,
            'profile':{k:profile[k] for k in ('id','name','system','reference','scope')},'fields':model,'visual':visual,'resources':resource_definitions(profile),
            'knowledge':knowledge,'map_workbench':profile['id']=='ffl2-usa','simple_editor_unavailable':availability,
            'locations':[{'offset':o,'length':n,'label':label,**BYTE_NOTES[profile['id']][i]} for i,(o,n,label) in enumerate(profile['offsets'])],
            'note':'Definition locations were tested on the matched original. A new build still needs playtesting.'}


def plan(api,parameters,*,cancelled=lambda:False):
    project,row,path=api.source(parameters);profile,root=_resolve(project,row,cancelled)
    if profile is None or profile['id']!=parameters['profile_id']:raise ValueError('no matching verified game definition for this exact revision')
    model=_model(profile,root,path)
    if not model:raise ValueError('Use the verified Graphics resource to review and build this edit.')
    values=parameters['values'];fields(values,' '.join(f['id'] for f in model))
    edits=[];preview=[];additional=[]
    def edit(offset,after):
        before=_read(path,offset,len(after))
        if before!=after:edits.append({'offset':offset,'before':before.hex(),'after':after.hex()})
    identifier=profile['id'];field=model[0];value=values[field['id']]
    if field['type']=='integer':number(value,field['min'],field['max'])
    if identifier=='ffl2-usa':
        from .verified_room import encode_move
        edit(0x20375,encode_move(path,root['path'],value));name='Bedroom stool - '+value
    elif identifier=='dejavu-casebooks-usa':
        if type(value) is not str or value not in ('original','parchment'):raise ValueError('choose a verified opening interface palette')
        for offset,_,_ in profile['offsets']:edit(offset,bytes.fromhex('0000027e1e007f03' if value=='original' else '0000285695155d5f'))
        name='Opening casebook colors - '+value
    elif identifier=='castlevania-usa':
        for offset,_,_ in profile['offsets']:edit(offset,bytes([value+1]))
        name=f'{value} starting spare lives'
    elif identifier=='chrono-trigger-usa':
        edit(0xc0267,bytes([value]));name=f'Wood Sword power {value}'
    elif identifier=='immortal-ue':
        if type(value) is not str or not value.strip() or re.fullmatch(r'[A-Za-z0-9 ?]{1,9}',value) is None:raise ValueError('use 1 to 9 letters, digits, spaces or ?; game control characters are protected')
        edit(0x4e1b,value.ljust(9).encode('ascii'))
        if _read(path,0xfffca,2)!=b'\x4e\x75':
            edit(0xfffca,b'\x4e\x75');additional.append('Game-specific ROM check: documented 2-byte adjustment at 0xFFFCA.')
        name='Menu text - '+value
    else:raise ValueError('no enabled verified editor for this game definition')
    if not edits:raise ValueError('no changes to build; choose a different value')
    preview.append({'label':field['label'],'before':field['value'],'after':value})
    result=api._integrity_plan({'project_id':parameters['project_id'],'artifact_id':row['artifact_id'],'edits':edits},cancelled)
    existing=next((b for b in projects.read_project(project)['builds'] if b.get('plan_id')==result['plan_id']),None)
    if existing is not None:projects._measure(existing['path'],existing,cancelled=cancelled)
    return {**result,'profile_id':identifier,'build_name':name,'preview':preview,'additional_changes':additional,
            'existing_build_id':existing['artifact_id'] if existing else None,
            'definition_reference':profile['reference'],'note':'Separate build. Test the result before sharing a patch.'}
