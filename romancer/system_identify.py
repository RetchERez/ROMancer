"""Investigate all supported header candidates without first-match authority."""
from pathlib import Path
import re
from .system_reader import SystemReader
from .system_registry import REGISTRY_VERSION
from .system_formats import nes,snes,genesis,gb,gba,segacd


def identify_system(path:Path,*,expected_sha256=None,cancelled=lambda:False)->dict:
    report={'schema_version':1,'operation':'systems-identify','ok':False,'status':'BLOCKED','source':None,
        'registry_version':REGISTRY_VERSION,'system_id':None,'candidates':[],'container':None,'regions':[],
        'warnings':[],'write_authorized':False,'runtime_verified':False}
    try:
        with SystemReader(path,expected_sha256=expected_sha256,cancelled=cancelled) as reader:
            report['source']=dict(reader.identity);size=reader.identity['size']
            prefix=reader.read_at(0,min(size,4096)) if size else b''
            if re.search(rb'(?im)^\s*FILE\s+(?:"[^"\r\n]+"|\S+)\s+(?:BINARY|WAVE|MP3|AIFF)\s*\r?$',prefix):
                report.update(ok=True,status='UNKNOWN',container={'format':'cue','dependency_state':'UNRESOLVED'},
                    warnings=['CUE container recognized; referenced tracks were not opened. Import and validate dependencies explicitly.'])
            else:
                found=[]
                for parser in (nes,snes,genesis,gb,gba,segacd):found.extend(parser.candidates(reader))
                valid=[c for c in found if c['layout_valid']]
                report['candidates']=found;report['warnings']=list(dict.fromkeys(w for c in found for w in c['warnings']))
                if len(valid)==1:
                    selected=valid[0];report.update(ok=True,status='IDENTIFIED',system_id=selected['system_id'],
                        container={'format':selected['format']},regions=selected['regions'])
                elif len(valid)>1:report.update(ok=True,status='AMBIGUOUS')
                elif found:report.update(status='BLOCKED',error='Recognized header has an invalid or unsupported layout.')
                else:report.update(ok=True,status='UNKNOWN')
        return report
    except (ValueError,OSError,KeyboardInterrupt) as exc:
        report.update(ok=False,status='CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'BLOCKED',
            system_id=None,regions=[],error=str(exc)[:1024] or 'System investigation cancelled')
        return report
