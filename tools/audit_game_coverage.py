"""Report the fixed revision acceptance gate. Exit 1 means acceptance is unmet."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romancer.game_coverage import status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Create a new JSON report; existing reports are never overwritten.')
    args=parser.parse_args()
    try:
        report=status(limit=100)
        report.pop('revisions')
        encoded=json.dumps(report,indent=2)+'\n'
        if args.output:
            with args.output.open('x',encoding='utf-8',newline='\n') as stream:stream.write(encoded)
        else:print(encoded,end='')
        return 0 if report['release_ready'] else 1
    except (ValueError,OSError) as error:
        print(str(error),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
