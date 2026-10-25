"""Format-derived resource descriptors; actual edits retain normal plan preconditions."""
from pathlib import Path
from .assets import checked_path
from .system_identify import identify_system


def describe_nes_chr(path:Path,*,expected_sha256:str,first_tile:int=0,count:int=16,cancelled=lambda:False)->dict:
    result={'schema_version':1,'operation':'systems-nes-chr','ok':False,'status':'BLOCKED','written':False,
        'write_authorized':False,'runtime_verified':False}
    try:
        if cancelled():raise KeyboardInterrupt
        if type(first_tile) is not int or first_tile<0 or type(count) is not int or not 1<=count<=64:
            raise ValueError('CHR tile page requires a nonnegative first tile and count 1..64')
        path=checked_path(Path(path))
        if path.stat().st_size>64*1024**2:raise ValueError('Flat asset editing is limited to 64 MiB sources; use a bounded container resource workflow.')
        assessment=identify_system(path,expected_sha256=expected_sha256,cancelled=cancelled)
        if assessment['status']=='CANCELLED':raise KeyboardInterrupt
        if assessment['status']!='IDENTIFIED' or assessment['system_id']!='nes':
            raise ValueError(assessment.get('error') or 'A unique validated NES file layout is required')
        chr_region=next((r for r in assessment['regions'] if r['id']=='chr-rom'),None)
        if chr_region is None:raise ValueError('This image has no stored CHR-ROM; CHR-RAM contents require a runtime or declared resource.')
        total=chr_region['length']//16
        if chr_region['length']%16 or first_tile>=total or count>total-first_tile:raise ValueError('CHR tile page extends outside the stored CHR-ROM')
        provenance={'origin':'profile_assertion','note':'NES file-format CHR-ROM page; runtime palettes and consumers are not inferred.',
            'reference':'https://www.nesdev.org/wiki/INES'}
        schema={'schema_version':1,'id':'nes-chr-'+str(first_tile),'version':'1','source':assessment['source'],
            'provenance':provenance,'bitmaps':[{'id':'nes-chr-page','offset':chr_region['offset']+first_tile*16,
                'length':count*16,'codec':'tile8-planar2-msb-v1','width':8,'height':8,'count':count,'palette_id':None,'provenance':provenance}],
            'palettes':[],'tilemaps':[],'fonts':[]}
        return {**result,'ok':True,'status':'DESCRIBED','source':assessment['source'],'system_id':'nes',
            'first_tile':first_tile,'count':count,'total_tiles':total,'schema':schema,
            'warnings':['Display colors are an inspection aid. Stored palette values and tile consumers have not been mapped.']}
    except (ValueError,OSError,KeyboardInterrupt) as exc:
        return {**result,'status':'CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED','error':str(exc)[:1024] or 'CHR investigation cancelled'}
