"""Fetch the pinned, build-only NSIS compiler; the app never downloads it."""
import argparse
from pathlib import Path
import sys

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.fetch_runtime import fetch_pin
from tools.package_installer import NSIS_PIN

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--downloads',type=Path,required=True)
    args=parser.parse_args();print(fetch_pin(args.downloads,NSIS_PIN,allowed_hosts=('downloads.sourceforge.net',)))
