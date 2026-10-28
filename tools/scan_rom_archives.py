"""Scan supplied ROM ZIPs into ROMancer's payload-free measured-facts database."""
import argparse,json,sys
from pathlib import Path
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romancer.rom_archive_scan import scan_archives

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True,help='Measured facts JSON; no ROM bytes.')
    parser.add_argument('--report',type=Path,required=True,help='Private exclusions and completion report.')
    parser.add_argument('--journal',type=Path,help='Private resumable facts journal.')
    parser.add_argument('--jobs',type=int,default=2)
    args=parser.parse_args()
    def progress(row):
        if row['processed']==1 or row['processed']%25==0 or row['processed']==row['total']:print(json.dumps({'progress':row}),flush=True)
    result=scan_archives(args.archives,args.output,args.report,jobs=args.jobs,journal=args.journal,progress=progress)
    print(json.dumps({'result':result}),flush=True)
    return 0 if result['records'] else 1

if __name__=='__main__':raise SystemExit(main())

