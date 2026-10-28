"""Bounded, read-only discovery of known local libretro library names."""
import os
from pathlib import Path
from .runtime_profiles import _binary,save_profile,load_profile
from .assets import checked_path,digest

NAMES={'fceumm': ['nes'], 'nestopia': ['nes'], 'snes9x': ['snes'], 'genesis_plus_gx': ['genesis'], 'picodrive': ['genesis'], 'gambatte': ['gb', 'gbc'], 'sameboy': ['gb', 'gbc']}
KEYS={'up':'ArrowUp','down':'ArrowDown','left':'ArrowLeft','right':'ArrowRight','a':'z','b':'x','start':'Enter','select':'Shift'}


def scan_core_library(workspace,directories):
    if type(directories) is not list or not 1<=len(directories)<=8 or any(type(d) is not str or len(d)>4096 for d in directories):raise ValueError('choose1..8 local core folders')
    candidates=[];issues=[];seen=set();entries=0;total=0;partial=False
    for directory in directories:
        root=checked_path(Path(directory))
        if not root.is_dir():issues.append({'folder':str(root),'reason':'Folder is missing.'});continue
        queue=[(root,0)]
        while queue:
            parent,depth=queue.pop(0)
            with os.scandir(parent) as scan:
                for entry in scan:
                    entries+=1
                    if entries>2048:partial=True;break
                    if entry.is_symlink():continue
                    if entry.is_dir(follow_symlinks=False):
                        if depth<2:queue.append((Path(entry.path),depth+1))
                        continue
                    path=Path(entry.path);name=path.name.lower();stem=name.removesuffix('.dll').removesuffix('.so').removesuffix('_libretro')
                    if stem not in NAMES or path.suffix.lower() not in ('.dll','.so') or str(path) in seen:continue
                    seen.add(str(path));size=entry.stat(follow_symlinks=False).st_size
                    if size>256*1024**2 or total+size>512*1024**2 or len(candidates)>=32:partial=True;continue
                    total+=size
                    try:identity=_binary(path)
                    except (ValueError,OSError) as error:issues.append({'folder':str(path),'reason':str(error)});continue
                    row={'core':str(checked_path(path)),'identity':identity,'systems':NAMES[stem]};row['candidate_id']=digest(row);candidates.append(row)
            if entries>2048:break
        if entries>2048:break
    return {'ok':True,'candidates':candidates,'issues':issues[:64],'partial':partial,'runtime_verified':False}


def configure_local_core(workspace,system_id,candidate):
    if type(candidate) is not dict or set(candidate)!={'candidate_id','core','identity','systems'} or candidate['candidate_id']!=digest({k:candidate[k] for k in ('core','identity','systems')}):raise ValueError('choose a measured core candidate')
    stem=Path(candidate['core']).name.lower().removesuffix('.dll').removesuffix('.so').removesuffix('_libretro')
    if system_id not in NAMES.get(stem,[]) or candidate['systems']!=NAMES[stem]:raise ValueError('selected core does not match this system')
    if _binary(candidate['core'])!=candidate['identity']:raise ValueError('selected core changed; scan the folder again')
    saved=load_profile(workspace,system_id)['profile']
    if saved:raise ValueError('a setup already exists; use advanced setup to replace it')
    options={'gambatte_gb_colorization':'disabled','gambatte_gb_hwmode':'GBC' if system_id=='gbc' else 'GB'} if stem=='gambatte' else {}
    return save_profile(workspace,system_id,candidate['core'],options,None,KEYS)
