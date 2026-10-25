"""Read-only cases bound to a stored build, exact source, and imported trace."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import BinaryIO
from . import history,capture_store
from .assets import checked_path,hash_stream,identity,failure,_bounded
from .debug_schema import validate_debug_case,validate_debug_trace
from .debug_trace import resolve_probe,select_trace_candidates


def _role(identity,role):
    matches=[row for row in identity['inputs'] if row['role']==role]
    if role=='output':matches.append(identity['output'])
    if len(matches)!=1:raise ValueError('source role is missing or ambiguous in selected build')
    return matches[0]


@dataclass
class DebugInputs:
    path:Path
    stream:BinaryIO
    initial:os.stat_result
    case:dict
    trace:dict
    build:dict
    report:dict

    def recheck(self):
        checked_path(self.path)
        if (identity(self.path.stat())!=identity(self.initial) or identity(os.fstat(self.stream.fileno()))!=identity(self.initial)
                or hash_stream(self.stream)!=self.case['source']['sha256']):raise ValueError('case source changed')


@contextmanager
def _debug_inputs(project:Path,source:Path,case:dict,trace:dict):
    checked=validate_debug_case(case);case=checked['normalized']
    traced=validate_debug_trace(trace,case);trace=traced['normalized']
    build=history.get_build(project,case['build_id']);member=_role(build['identity'],case['source']['role'])
    if any(member[key]!=case['source'][key] for key in ('sha256','size')):raise ValueError('case source is not the declared build resource')
    path=checked_path(source);initial=path.stat()
    if not path.is_file() or initial.st_nlink!=1 or initial.st_size!=case['source']['size']:raise ValueError('invalid case source size or identity')
    with path.open('rb') as stream:
        if hash_stream(stream)!=case['source']['sha256'] or identity(os.fstat(stream.fileno()))!=identity(initial):raise ValueError('case source revision mismatch')
        probes=[]
        for probe in case['probes']:
            resolved=resolve_probe(probe,case);row={**resolved,'address':probe['address'],'length':probe['length'],'source':None}
            if resolved['file_offset'] is not None:
                stream.seek(resolved['file_offset']);raw=stream.read(probe['length'])
                if len(raw)!=probe['length']:raise ValueError('source truncated during probe')
                row['source']={'offset':resolved['file_offset'],'raw_hex':raw.hex(),'sha256':hashlib.sha256(raw).hexdigest()}
            probes.append(row)
        captures=[]
        for selector in case['captures']:
            result=capture_store.get_capture(project,selector['capture_id']);record=result['record']
            if record['origin']!='native_worker' or record.get('build',{}).get('association')!='measured_run_output':
                raise ValueError('imported captures cannot satisfy native capture selectors')
            if (selector['build_id']!=case['build_id'] or record['build']['build_id']!=case['build_id']
                    or record['image']['blob_sha256']!=selector['png_sha256'] or record['image']['rgb_sha256']!=selector['rgb_sha256']):
                raise ValueError('stored capture binding mismatch')
            selected=_role(record['build']['identity'],selector['source_role'])
            if any(selected[key]!=case['source'][key] for key in ('sha256','size')):raise ValueError('capture selected resource differs')
            x,y,width,height=selector['region']
            if x+width>record['image']['width'] or y+height>record['image']['height']:raise ValueError('capture selector outside image')
            captures.append({'selector_id':selector['id'],'capture_id':record['capture_id'],'image':record['image'],
                             'run':record['run'],'region':selector['region'],'pixel_decode_status':'NOT_RUN','alignment':'UNKNOWN'})
        report={'schema_version':1,'operation':'debug-case','ok':True,'status':'INSPECTED','build_id':case['build_id'],
                'case_sha256':checked['sha256'],'trace_sha256':traced['sha256'],'source_sha256':case['source']['sha256'],
                'source_size':case['source']['size'],'build_currentness':'NOT_CHECKED','probes':probes,
                'trace_candidates':select_trace_candidates(trace,case),'captures':captures,'links':case['links'],
                'mutation_evidence':'NOT_RUN','causation':'NOT_RUN','natural_progress_verified':False}
        held=DebugInputs(path,stream,initial,case,trace,build,_bounded(report));held.recheck()
        yield held
        held.recheck()


def inspect_debug_case(project:Path,source:Path,case:dict,trace:dict)->dict:
    try:
        with _debug_inputs(project,source,case,trace) as inputs:result=inputs.report
        return result
    except (ValueError,OSError,KeyError,TypeError,KeyboardInterrupt) as exc:return failure('debug-case',exc)
