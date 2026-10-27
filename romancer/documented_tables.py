"""Original bounded locators for documented GBA numeric layouts.

Minimal stat/type and move-property facts come from pinned pret/pokeemerald
731ad5bfd6e6f265508d0efcca0ba42f9dcf5881. No game code or full data table is
included. A structural match outside the exact original is a candidate.
"""
import hashlib
from .assets import digest
from .documented_names import SPECIES_NAMES,MOVE_NAMES

EMERALD_SHA256='a9dec84dfe7f62ab2220bafaef7479da0929d066ece16a6885f6226db19085af'
SOURCE='https://github.com/pret/pokeemerald/tree/731ad5bfd6e6f265508d0efcca0ba42f9dcf5881'
STAT_MARKERS=tuple(bytes(row) for row in ([45,49,49,45,65,65,12,3],[60,62,63,60,80,80,12,3],[80,82,83,80,100,100,12,3]))
MOVE_MARKERS=tuple(bytes(row) for row in ([40,0,100,35],[50,1,100,25],[15,0,85,10]))


def _plausible(raw,base,stride,count,kind):
    if base<0 or base+stride*count>len(raw):return False
    for i in range(count):
        at=base+i*stride
        if kind=='species':
            if not all(raw[at+j]>0 for j in range(6)) or raw[at+6]>17 or raw[at+7]>17:return False
        elif raw[at+2]>17 or raw[at+3]>100 or not raw[at+4]:return False
    return True


def scan(raw,sha,system,*,cancelled=lambda:False):
    if type(raw) is not bytes or len(raw)>32*1024**2 or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Documented-table source identity or size differs.')
    candidates=[];checked=0;truncated=False
    if system=='gba':
        for kind,stride,count,shift,markers,title in [('species',28,151,0,STAT_MARKERS,'Pokemon species base stats'),('moves',12,165,1,MOVE_MARKERS,'Pokemon move properties')]:
            position=0
            while (at:=raw.find(markers[0],position))>=0:
                if cancelled():raise KeyboardInterrupt
                checked+=1;position=at+1
                if checked>4096 or len(candidates)>=32:truncated=True;break
                base=at-shift
                if not all(raw[at+i*stride:at+i*stride+len(marker)]==marker for i,marker in enumerate(markers)):continue
                if not _plausible(raw,base,stride,count,kind):continue
                identifier=digest({'sha256':sha,'kind':kind,'offset':base,'stride':stride,'count':count})
                exact=sha==EMERALD_SHA256 and len(raw)==16*1024**2
                candidates.append({'candidate_id':identifier,'kind':kind,'name':title,'offset':base,'length':count*stride,'count':count,'stride':stride,
                    'exact_revision':exact,'status':'MATCHED_ORIGINAL' if exact else 'STRUCTURAL_MATCH',
                    'source':SOURCE,'matched_records':3,'validated_record_prefixes':count,
                    'note':('Matches the published Emerald original revision and the checked numeric layout.' if exact else 'Three documented opening records and all listed record prefixes match. A modified game can still use different identities or behavior.'),
                    'write_authorized':False})
    return {'ok':True,'source_sha256':sha,'candidates':candidates,'truncated':truncated,'signature_positions_checked':checked,
            'whole_file_searched':system=='gba' and not truncated,'write_authorized':False,
            'scope':'Documented first151 species / first165 moves at checked strides. No arbitrary expanded-game formats are inferred.'}


def definition(raw,sha,system,candidate_id,*,cancelled=lambda:False):
    from .data_tables import validate_definition
    found=next((r for r in scan(raw,sha,system,cancelled=cancelled)['candidates'] if r['candidate_id']==candidate_id),None)
    if found is None:raise ValueError('This table result is stale or does not match the current source.')
    if found['kind']=='species':
        columns=[('HP',0,'u8',1,255),('Attack',1,'u8',1,255),('Defense',2,'u8',1,255),('Speed',3,'u8',1,255),('Sp. attack',4,'u8',1,255),('Sp. defense',5,'u8',1,255),('Type 1',6,'u8',0,17),('Type 2',7,'u8',0,17),('Catch rate',8,'u8',0,255),('Exp. yield',9,'u8',0,255)]
        names=SPECIES_NAMES
    else:
        columns=[('Power',1,'u8',0,255),('Accuracy',3,'u8',0,100),('PP',4,'u8',1,255),('Type',2,'u8',0,17),('Effect chance',5,'u8',0,100),('Priority',7,'s8',-128,127)]
        names=MOVE_NAMES
    return validate_definition({'schema_version':1,'name':found['name']+(' (pattern)' if not found['exact_revision'] else ''),
         'offset':found['offset'],'stride':found['stride'],'count':found['count'],'row_names':list(names),'row_id_base':1,
         'fields':[{'name':name,'offset':at,'type':kind,'endian':'little','pointer_base':None,'minimum':low,'maximum':high} for name,at,kind,low,high in columns]},len(raw))


class DocumentedTableTools:
    def __init__(self,api):self.api=api
    def routes(self):
        return {'documented.scan':('project_id artifact_id',self.scan),'documented.open':('project_id artifact_id candidate_id',self.open)}
    def _source(self,p,c):
        from .workbench_files import read_bounded
        _,row,path=self.api.source(p)
        if row.get('system_id')!='gba':raise ValueError('These documented table locators currently cover GBA numeric layouts.')
        return row,path,read_bounded(path,32*1024**2,row,cancelled=c)
    def scan(self,p,c):
        row,_,raw=self._source(p,c);return {**scan(raw,row['sha256'],row['system_id'],cancelled=c),'artifact_id':row['artifact_id']}
    def open(self,p,c):
        from .data_tables import inspect_table
        row,path,raw=self._source(p,c);d=definition(raw,row['sha256'],row['system_id'],p['candidate_id'],cancelled=c)
        found=next(r for r in scan(raw,row['sha256'],row['system_id'],cancelled=c)['candidates'] if r['candidate_id']==p['candidate_id'])
        return {'ok':True,'artifact_id':row['artifact_id'],'source_sha256':row['sha256'],'definition':d,'inspection':inspect_table(path,row['sha256'],d,0,50),
                'note':found['note']+' Review stored values and test each build; battle formulas and scripts are separate.','exact_revision':found['exact_revision'],'write_authorized':False}
