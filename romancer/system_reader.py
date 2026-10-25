"""Stable streaming identity and small ranges for console-header investigation."""
import hashlib
import os
from pathlib import Path
import re
from .assets import checked_path,identity

MAX_SOURCE=8*1024**3
CHUNK=65536
MAX_HEADER_BYTES=65536


class SystemReader:
    def __init__(self,path:Path,*,expected_sha256=None,cancelled=lambda:False):
        if expected_sha256 is not None and (type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',expected_sha256)):
            raise ValueError('expected source SHA-256 is malformed')
        self.path=checked_path(Path(path));self.expected=expected_sha256;self.cancelled=cancelled
        self.stream=None;self.header_bytes=0;self.identity=None;self.initial=None

    def _cancel(self):
        if self.cancelled():raise KeyboardInterrupt('system investigation cancelled')

    def _stable(self):
        checked_path(self.path)
        current=self.path.stat();opened=os.fstat(self.stream.fileno())
        if (current.st_nlink!=1 or opened.st_nlink!=1 or identity(current)!=identity(self.initial)
                or identity(opened)!=identity(self.initial)):raise ValueError('source changed during system investigation')

    def _hash(self):
        self._stable();self.stream.seek(0);digest=hashlib.sha256();total=0
        while True:
            self._cancel();chunk=self.stream.read(CHUNK)
            if not chunk:break
            total+=len(chunk)
            if total>MAX_SOURCE:raise ValueError('source exceeds 8 GiB budget')
            digest.update(chunk)
        self._stable()
        if total!=self.initial.st_size:raise ValueError('source size changed')
        return digest.hexdigest()

    def __enter__(self):
        self._cancel();self.initial=self.path.stat()
        if not self.path.is_file() or self.initial.st_nlink!=1 or self.initial.st_size>MAX_SOURCE:
            raise ValueError('source must be an ordinary single-link file within 8 GiB')
        # Revalidation must reach the file again, not a BufferedReader's cached bytes.
        self.stream=self.path.open('rb',buffering=0)
        try:
            sha=self._hash()
            if self.expected is not None and sha!=self.expected:raise ValueError('source revision changed')
            self.identity={'sha256':sha,'size':self.initial.st_size};return self
        except BaseException:self.stream.close();raise

    def read_at(self,offset:int,length:int)->bytes:
        if (type(offset) is not int or type(length) is not int or offset<0 or not 1<=length<=CHUNK
                or offset>self.initial.st_size or length>self.initial.st_size-offset):
            raise ValueError('header range is outside supported source bounds')
        if self.header_bytes+length>MAX_HEADER_BYTES:raise ValueError('aggregate header read budget exceeded')
        self._cancel();self._stable();self.stream.seek(offset);raw=self.stream.read(length)
        if len(raw)!=length:raise ValueError('source changed during range read')
        self.header_bytes+=length;self._stable();return raw

    def verify(self)->None:
        if self._hash()!=self.identity['sha256']:raise ValueError('source content changed during system investigation')

    def __exit__(self,exc_type,exc,tb):
        try:
            if exc_type is None:self.verify()
        finally:
            if self.stream is not None:self.stream.close()
