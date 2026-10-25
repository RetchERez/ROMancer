"""Bounded stereo PCM checks and independently readable canonical WAV exports."""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile
from .asset_schema import fields, number, provenance, label
from .assets import checked_path, hash_stream, identity, digest, failure
from .cd_patch import check_output_paths
from .script_schema import canonical_bytes

MAX_PCM=1048576


def validate_baseline(baseline):
    baseline=json.loads(canonical_bytes(baseline,max_bytes=1024*1024))
    fields(baseline,'schema_version id version sample_rate expected_duration tolerance_samples expected_pcm_sha256 provenance')
    number(baseline['schema_version'],1,1);label(baseline['id']);label(baseline['version']);provenance(baseline['provenance'])
    number(baseline['sample_rate'],1,192000);number(baseline['tolerance_samples'],0,262144)
    duration=baseline['expected_duration'];fields(duration,'numerator denominator')
    p=number(duration['numerator'],1,10**9);q=number(duration['denominator'],1,10**9)
    if math.gcd(p,q)!=1:raise ValueError('duration must be a reduced positive rational')
    waveform=baseline['expected_pcm_sha256']
    if waveform is not None and (type(waveform) is not str or not re.fullmatch('[0-9a-f]{64}',waveform)):
        raise ValueError('invalid expected waveform SHA-256')
    return baseline


def validate_descriptor(descriptor):
    descriptor=json.loads(canonical_bytes(descriptor,max_bytes=1024*1024))
    fields(descriptor,'schema_version source format channels sample_rate provenance')
    number(descriptor['schema_version'],1,1);number(descriptor['channels'],2,2);number(descriptor['sample_rate'],1,192000)
    if descriptor['format']!='s16le':raise ValueError('only signed stereo PCM16 little-endian is supported')
    fields(descriptor['source'],'sha256 size');number(descriptor['source']['size'],4,MAX_PCM)
    if descriptor['source']['size']%4:raise ValueError('PCM must contain whole stereo sample frames')
    sha=descriptor['source']['sha256']
    if type(sha) is not str or not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('invalid PCM hash')
    p=descriptor['provenance'];fields(p,'origin note reference')
    if p['origin']!='supplied_pcm':raise ValueError('supplied PCM cannot claim runtime origin')
    label(p['note'],512,blank=True)
    if p['reference'] is not None:label(p['reference'],256)
    return descriptor


def check_pcm(raw,rate,baseline,*,complete=True):
    baseline=validate_baseline(baseline)
    if type(raw) is not bytes or not raw or len(raw)>MAX_PCM or len(raw)%4:raise ValueError('invalid bounded stereo PCM data')
    rate=number(rate,1,192000);frames=len(raw)//4;sha=hashlib.sha256(raw).hexdigest()
    duration=baseline['expected_duration'];p,q=duration['numerator'],duration['denominator']
    difference=frames*q-rate*p
    timing=('BLOCKED' if not complete else 'PASS' if rate==baseline['sample_rate'] and abs(difference)<=baseline['tolerance_samples']*q else 'FAIL')
    waveform='NOT_RUN' if baseline['expected_pcm_sha256'] is None else ('PASS' if sha==baseline['expected_pcm_sha256'] else 'FAIL')
    return {'schema_version':1,'operation':'audio-check','ok':timing=='PASS' and waveform in ('PASS','NOT_RUN'),
            'status':'PASS' if timing=='PASS' and waveform in ('PASS','NOT_RUN') else ('BLOCKED' if timing=='BLOCKED' else 'FAIL'),
            'pcm_sha256':sha,'pcm_bytes':len(raw),'sample_frames':frames,'sample_rate':rate,
            'observed_duration':{'numerator':frames//math.gcd(frames,rate),'denominator':rate//math.gcd(frames,rate)},
            'expected_duration':duration,'sample_discrepancy':{'numerator':difference,'denominator':q},
            'timing_status':timing,'waveform_status':waveform,'baseline_sha256':digest(baseline),
            'complete':complete,'native_playback_verified':False,'natural_progress_verified':False}


@contextmanager
def checked_pcm(source,descriptor):
    descriptor=validate_descriptor(descriptor);source=checked_path(source);initial=source.stat()
    if not source.is_file() or initial.st_nlink!=1 or initial.st_size!=descriptor['source']['size']:raise ValueError('PCM file identity or size mismatch')
    with source.open('rb') as stream:
        pieces=[];remaining=initial.st_size
        while remaining:
            piece=stream.read(min(65536,remaining))
            if not piece:raise ValueError('PCM truncated')
            pieces.append(piece);remaining-=len(piece)
        raw=b''.join(pieces)
        if stream.read(1) or hashlib.sha256(raw).hexdigest()!=descriptor['source']['sha256']:raise ValueError('PCM revision mismatch')
        yield raw,descriptor
        checked_path(source)
        if identity(source.stat())!=identity(initial) or identity(os.fstat(stream.fileno()))!=identity(initial) or hash_stream(stream)!=descriptor['source']['sha256']:
            raise ValueError('PCM changed during operation')


def check_audio(source: Path, descriptor: dict, baseline: dict) -> dict:
    try:
        with checked_pcm(source,descriptor) as (raw,descriptor):
            result={**check_pcm(raw,descriptor['sample_rate'],baseline),'capture_origin':'supplied_pcm'}
        return result
    except (ValueError,OSError,KeyboardInterrupt) as exc:return failure('audio-check',exc)


def wav_bytes(raw,rate):
    return (b'RIFF'+struct.pack('<I',36+len(raw))+b'WAVEfmt '+struct.pack('<IHHIIHH',16,1,2,rate,rate*4,4,16)
            +b'data'+struct.pack('<I',len(raw))+raw)


def publish_pcm(raw,destination,rate,output_format,protected_inputs=(),before_publish=None):
    if output_format not in ('pcm','wav'):raise ValueError('output format must be pcm or wav')
    destination=checked_path(destination)
    if destination.suffix.lower()!='.'+output_format:raise ValueError('output suffix must match the selected format')
    for source in protected_inputs:check_output_paths(source,[destination])
    if destination.exists() or not destination.parent.is_dir():raise ValueError('output must be new in an existing directory')
    parent=destination.parent.stat();data=raw if output_format=='pcm' else wav_bytes(raw,rate)
    descriptor,name=tempfile.mkstemp(prefix='.romancer-audio-',dir=destination.parent);temporary=Path(name)
    info=temporary.stat()
    try:
        with os.fdopen(descriptor,'wb') as output:output.write(data);output.flush();os.fsync(output.fileno())
        # Independent RIFF field checks; the audio bytes are never transformed.
        actual=temporary.read_bytes()
        if output_format=='wav':
            if (actual[:4]!=b'RIFF' or actual[8:16]!=b'WAVEfmt ' or actual[36:40]!=b'data'
                    or struct.unpack('<IHHIIHH',actual[16:36])!=(16,1,2,rate,4*rate,4,16)
                    or struct.unpack('<I',actual[4:8])[0]!=len(actual)-8 or struct.unpack('<I',actual[40:44])[0]!=len(raw)
                    or actual[44:]!=raw):raise ValueError('WAV independent verification failed')
        elif actual!=raw:raise ValueError('PCM independent verification failed')
        if not os.path.samestat(temporary.stat(),info) or not os.path.samestat(destination.parent.stat(),parent):raise ValueError('output identity changed')
        if before_publish:before_publish()
        os.link(temporary,destination)
        return {'written':True,'publication_status':'PUBLISHED','output_path':str(destination),
                'output_sha256':hashlib.sha256(actual).hexdigest(),'output_format':output_format}
    finally:
        try:
            if os.path.samestat(temporary.stat(),info):temporary.unlink()
        except OSError:pass


def export_audio(source: Path, destination: Path, descriptor: dict, baseline: dict,
                 *, output_format: str, protected_inputs: tuple[Path,...]=()) -> dict:
    result={'written':False,'publication_status':'NOT_PUBLISHED'}
    try:
        with checked_pcm(source,descriptor) as (raw,descriptor):
            result.update(check_pcm(raw,descriptor['sample_rate'],baseline),operation='audio-export',capture_origin='supplied_pcm')
            if not result['ok']:return result
            # Reopen/rehash is required before the single publication operation.
            def recheck():
                with checked_pcm(source,descriptor):pass
            result.update(publish_pcm(raw,destination,descriptor['sample_rate'],output_format,(source,*protected_inputs),recheck))
        return result
    except (ValueError,OSError,KeyboardInterrupt) as exc:
        return {**failure('audio-export',exc),**{k:v for k,v in result.items() if k not in ('ok','status')},'ok':False}
