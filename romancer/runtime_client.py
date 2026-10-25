"""Owned subprocess lifecycle for a trusted local emulator worker."""
from collections import deque
import math
import os
from pathlib import Path
import queue
import secrets
import socket
import subprocess
import sys
import threading
import time

from .runtime_protocol import VERSION, REQUEST_LIMIT, RESPONSE_LIMIT, STARTUP_LIMIT, decode, encode


class RuntimeWorkerError(RuntimeError):
    pass


class RuntimeClient:
    def __init__(self, argv: list[str], timeout: float = 10, *, cancelled=None):
        if type(argv) is not list or not argv or any(type(arg) is not str or not arg or '\x00' in arg for arg in argv):
            raise ValueError('worker command must be a nonempty argv array')
        if Path(argv[0]).resolve() != Path(sys.executable).resolve():
            raise ValueError('launch the worker directly with this Python interpreter; run the client inside WSL for Linux cores')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise ValueError('worker timeout must be finite, positive and at most 120 seconds')
        self.timeout = timeout
        if cancelled is not None and not callable(cancelled):raise ValueError('cancelled must be a callable')
        self.cancelled = cancelled
        self.process = None
        self.socket = None
        self.closed = False
        self._id = 0
        self._tails = {'stdout': deque(maxlen=16), 'stderr': deque(maxlen=16)}
        self._threads = []
        self._request_lock = threading.Lock()
        self._token = secrets.token_hex(32)
        startup = queue.Queue(maxsize=1)
        try:
            # Windows venv python.exe redirects to another process. Launch the base
            # interpreter exactly as CPython's venv redirector does, retaining its
            # environment path, so PID authentication and termination own the worker.
            executable=None;environment=None
            if os.name=='nt' and sys.prefix!=sys.base_prefix:
                executable=sys._base_executable
                environment=os.environ.copy()
                environment['__PYVENV_LAUNCHER__']=sys.executable
            self.process = subprocess.Popen(
                [*argv, '--token', self._token], executable=executable,env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            for name in ('stdout', 'stderr'):
                thread = threading.Thread(target=self._drain,
                                          args=(name, startup if name == 'stdout' else None), daemon=True)
                thread.start()
                self._threads.append(thread)
            if self.cancelled is None:
                startup_data=startup.get(timeout=timeout)
            else:
                startup_deadline=time.monotonic()+timeout
                while True:
                    if self.cancelled():raise KeyboardInterrupt
                    remaining=startup_deadline-time.monotonic()
                    if remaining<=0:raise queue.Empty
                    try:startup_data=startup.get(timeout=min(.1,remaining));break
                    except queue.Empty:continue
            banner = decode(startup_data, STARTUP_LIMIT)
            if (type(banner.get('protocol_version')) is not int or banner['protocol_version'] != VERSION
                    or type(banner.get('port')) is not int or not 1 <= banner['port'] <= 65535
                    or type(banner.get('pid')) is not int or banner['pid'] != self.process.pid):
                raise ValueError('invalid worker startup handshake')
            self.socket = socket.create_connection(('127.0.0.1', banner['port']), timeout=timeout)
            self.socket.settimeout(timeout)
            hello = self.request('hello')
            if hello.get('ok') is not True or hello.get('protocol_version') != VERSION:
                raise ValueError('worker did not complete authenticated handshake')
        except (OSError, ValueError, queue.Empty, RecursionError) as exc:
            self._abort()
            raise RuntimeWorkerError(f'Worker startup failed: {exc}; {self.diagnostics()}') from exc
        except BaseException:
            self._abort()
            raise

    def _drain(self, name, startup):
        stream = getattr(self.process, name)
        try:
            if startup is not None:
                startup.put(stream.readline(STARTUP_LIMIT + 1))
            while data := stream.read(4096):
                self._tails[name].append(data)
        except (OSError, ValueError):
            if startup is not None and startup.empty():
                try:
                    startup.put_nowait(b'')
                except queue.Full:
                    pass

    def diagnostics(self):
        return {name: b''.join(tuple(chunks)).decode('utf-8', errors='replace')
                for name, chunks in self._tails.items()}

    def request(self, operation: str, **parameters):
        if self.closed or self.socket is None:
            raise RuntimeWorkerError('Worker is closed')
        if type(operation) is not str or not operation:
            raise ValueError('operation must be a nonempty string')
        with self._request_lock:
            self._id += 1
            packet = {'protocol_version': VERSION, 'id': self._id, 'token': self._token,
                      'operation': operation, 'timeout': self.timeout, 'parameters': parameters}
            payload = encode(packet, REQUEST_LIMIT)
            try:
                deadline = time.monotonic() + self.timeout
                self.socket.settimeout(self.timeout)
                self.socket.sendall(payload)
                data = bytearray()
                while True:
                    if self.cancelled is not None and self.cancelled():raise KeyboardInterrupt
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('worker request deadline exceeded')
                    self.socket.settimeout(min(.1,remaining) if self.cancelled is not None else remaining)
                    try:chunk = self.socket.recv(min(65536, RESPONSE_LIMIT + 1 - len(data)))
                    except socket.timeout:
                        if self.cancelled is not None:continue
                        raise
                    if not chunk:
                        raise ValueError('worker closed before a complete response')
                    data.extend(chunk)
                    if len(data) > RESPONSE_LIMIT:
                        raise ValueError('worker response exceeds protocol limit')
                    if b'\n' in chunk:
                        if data.find(b'\n') != len(data) - 1:
                            raise ValueError('unexpected traffic after worker response')
                        break
                if time.monotonic() > deadline:
                    raise TimeoutError('worker request deadline exceeded')
                reply = decode(bytes(data), RESPONSE_LIMIT)
                if (type(reply.get('protocol_version')) is not int or reply['protocol_version'] != VERSION
                        or type(reply.get('id')) is not int or reply['id'] != self._id
                        or type(reply.get('result')) is not dict or type(reply['result'].get('ok')) is not bool):
                    raise ValueError('worker response identity or shape mismatch')
                return reply['result']
            except (OSError, ValueError, RecursionError) as exc:
                self._abort()
                raise RuntimeWorkerError(f'Worker request failed: {exc}; {self.diagnostics()}') from exc
            except BaseException:
                self._abort()
                raise

    def _abort(self):
        self.closed = True
        if self.socket is not None:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.socket is not None:
            self.socket.close()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)
            for thread in self._threads:
                thread.join(timeout=1)
            for stream in (self.process.stdout, self.process.stderr):
                stream.close()

    def close(self):
        if self.closed:
            return
        try:
            self.request('close')
            self.process.wait(timeout=self.timeout)
        except (RuntimeWorkerError, subprocess.TimeoutExpired):
            pass
        finally:
            self._abort()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
