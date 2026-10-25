"""Package only the reviewed engines, their sources and required notices."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romancer.bundled_cores import core_members


def package_cores(root,output):
    output=Path(output)
    if output.exists():raise ValueError('engine archive already exists')
    files=core_members(root)
    with output.open('xb') as stream:
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name,raw in sorted(files.items()):
                info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                info.create_system=3;info.external_attr=0o100644<<16;z.writestr(info,raw)
    with output.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'ok':True,'path':str(output),'sha256':sha,'files':len(files)}


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--cores',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(package_cores(args.cores,args.output)))
