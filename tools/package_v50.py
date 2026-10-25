"""Build a source distribution using the reviewed positive source inventory."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.package_source import package
from romancer import ROMANCER_VERSION


def package_v50(root:Path,output:Path)->dict:
    result=package(Path(root),Path(output))
    return {**result,'product':'ROMancer','version':ROMANCER_VERSION,
            'credit':'By RetchEWretched','release_status':'RELEASE',
            'runtime_bundled':False,'requirements':'Python >=3.13 and Pillow; matching native core for emulation.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--manifest',type=Path);args=parser.parse_args()
    result=package_v50(args.root,args.output);text=json.dumps(result,indent=2)+'\n'
    if args.manifest:
        from romancer.release import publish_bytes
        publish_bytes(args.manifest,text.encode('utf-8'))
    print(json.dumps({k:v for k,v in result.items() if k!='members'},indent=2))


if __name__=='__main__':main()
