"""Bounded exact encoded-pointer candidates, never completeness or ownership proof."""
from .asset_schema import number

def survey_references(raw,target_offset,width,endian,base,alignment,*,start=0,cancelled=lambda:False):
    if type(raw) is not bytes or not 1<=len(raw)<=1024**2:raise ValueError('Survey at most1MiB of source bytes at a time.')
    number(target_offset,0,64*1024**2);number(width,2,4);number(base,-0xffffffff,0xffffffff);number(start,0,64*1024**2)
    if type(alignment) is not int or alignment not in (1,2,4):raise ValueError('Choose pointer alignment1,2 or4.')
    if endian not in ('little','big'):raise ValueError('Choose little or big endian.')
    encoded=target_offset+base
    if not 0<=encoded<1<<(width*8):raise ValueError('The target cannot be encoded with this pointer width and adjustment.')
    value=encoded.to_bytes(width,endian);matches=[];total=0;tested=0
    for at in range((-start)%alignment,len(raw)-width+1,alignment):
        if tested%4096==0 and cancelled():raise KeyboardInterrupt
        tested+=1
        if raw[at:at+width]!=value:continue
        total+=1
        if len(matches)<256:matches.append({'offset':start+at,'width':width,'endian':endian,'base':base,'target_delta':0,'encoded_hex':value.hex(),'confidence':'numeric_candidate'})
    return {'ok':True,'candidates':matches,'total_matches':total,'truncated':total>len(matches),
        'tested_range':{'offset':start,'length':len(raw)},'tested_positions':tested,'alignment':alignment,
        'target_offset':target_offset,'width':width,'endian':endian,'base':base,
        'references_complete':False,'game_use_observed':False,'write_authorized':False,
        'scope':'Exact numeric matches for the selected encoding only. Other encodings, banks, embedded references and consumers outside this window are untested.'}

class ReferenceSurveyTools:
    def __init__(self,api):self.api=api
    def routes(self):return {'references.survey':('project_id artifact_id target_offset width endian base offset length alignment',self.survey)}
    def survey(self,p,c):
        from .workbench_projects import _measure
        _,row,path=self.api.source(p);number(p['target_offset'],0,row['size']-1);number(p['length'],1,1024**2);number(p['offset'],0,row['size']-p['length'])
        with path.open('rb') as stream:stream.seek(p['offset']);raw=stream.read(p['length'])
        if len(raw)!=p['length']:raise ValueError('Source changed during the pointer survey.')
        result=survey_references(raw,p['target_offset'],p['width'],p['endian'],p['base'],p['alignment'],start=p['offset'],cancelled=c)
        _measure(path,row,cancelled=c)
        return {**result,'source_sha256':row['sha256'],'artifact_id':row['artifact_id']}
