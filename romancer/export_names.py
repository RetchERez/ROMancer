"""Safe user-facing download names; stored export identities stay unchanged."""
from pathlib import PurePosixPath
import re
import unicodedata

EXTENSIONS=frozenset('txt html bps zip pcm wav json png sav csv tsv'.split())
RESERVED=re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$',re.I)

def readable_name(title,suffix):
    if suffix not in EXTENSIONS:raise ValueError('Unsupported download extension')
    title=unicodedata.normalize('NFKD',str(title)).encode('ascii','ignore').decode('ascii')
    stem=re.sub(r'[^A-Za-z0-9_-]+','-',title).strip('-_')[:96].rstrip('-_') or 'ROMancer'
    if RESERVED.fullmatch(stem):stem='ROMancer-'+stem
    return stem+'.'+suffix

def download_name(row):
    stored=row['name'];name=row.get('download_name','');suffix=PurePosixPath(stored).suffix
    if (isinstance(name,str) and len(name)<=104 and re.fullmatch(r'[A-Za-z0-9_-]+\.[a-z]+',name)
            and PurePosixPath(name).suffix==suffix and suffix[1:] in EXTENSIONS
            and not RESERVED.fullmatch(PurePosixPath(name).stem)):
        return name
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.[a-z]+',stored) or suffix[1:] not in EXTENSIONS:
        raise ValueError('Invalid stored export name')
    return stored
