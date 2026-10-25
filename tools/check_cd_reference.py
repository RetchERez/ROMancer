"""Create synthetic vectors and validate them with an external edccchk process.

Run in WSL with a separately compiled edccchk executable. The measured binary
hash is checked around both runs, but no source commit or trusted pin is inferred.
This detects ordinary concurrent changes, not hostile executable replacement.
This tool does not include the checker's source or executable in a release.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from romancer.cdrom import repair_mode1
from romancer.cd_patch import _identity, check_output_paths


def _checker_snapshot(path):
    with path.open('rb') as stream:
        identity = _identity(os.fstat(stream.fileno()))
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if (_identity(os.fstat(stream.fileno())) != identity
                or _identity(path.stat()) != identity):
            raise ValueError('checker identity changed while hashing')
    return identity, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checker')
    parser.add_argument('output')
    args = parser.parse_args()
    checker = Path(args.checker).resolve()
    destination = Path(args.output)
    check_output_paths(checker, [destination])
    checker_identity = _checker_snapshot(checker)

    def check_identity():
        if _checker_snapshot(checker) != checker_identity:
            raise ValueError('checker identity/content changed during reference checks')

    vectors = []
    track = bytearray()
    for seed in (0, 1, 17, 255):
        header = b'\x00' + b'\xff' * 10 + b'\x00\x00\x02\x00\x01'
        payload = bytes((index * 17 + seed) % 256 for index in range(2048))
        repaired = repair_mode1(header + payload + bytes(288))
        vectors.append({'seed': seed, 'header_hex': header.hex(),
                        'integrity_hex': repaired[2064:].hex(),
                        'sector_sha256': hashlib.sha256(repaired).hexdigest()})
        track.extend(repaired)
    with tempfile.TemporaryDirectory(prefix='romancer_reference_') as directory:
        path = Path(directory) / 'synthetic.bin'
        path.write_bytes(track)
        check_identity()
        good = subprocess.run([str(checker), str(path)], capture_output=True, text=True, timeout=30)
        check_identity()
        print(good.stdout, good.stderr)
        damaged = bytearray(track)
        damaged[123] ^= 1
        path.write_bytes(damaged)
        check_identity()
        bad = subprocess.run([str(checker), str(path)], capture_output=True, text=True, timeout=30)
        check_identity()
        print('CORRUPTED CONTROL:', bad.stdout, bad.stderr)
    def count(result, label):
        match = re.search(r'^' + re.escape(label) + r'\.+\s+(\d+)$', result.stdout, re.M)
        if match is None or result.returncode != 0:
            raise RuntimeError('reference checker did not produce a valid summary')
        return int(match[1])
    if (count(good, 'Mode 1 sectors') != 4 or count(good, 'Total errors') != 0
            or count(good, 'Total warnings') != 0 or count(bad, 'Total errors') != 1):
        raise RuntimeError('independent positive/negative controls did not match')
    output = {'checker_commit': None,
              'checker_sha256': checker_identity[1],
              'checker_identity_status': 'MEASURED_UNPINNED',
              'generator': 'ROMancer; independently checked, not independently generated',
              'good': {'exit_code': good.returncode, 'stdout': good.stdout, 'stderr': good.stderr},
              'bad': {'exit_code': bad.returncode, 'stdout': bad.stdout, 'stderr': bad.stderr},
              'vectors': vectors}
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.romancer-reference-', suffix='.tmp', dir=destination.parent)
    temporary = Path(name)
    owned_stat = os.fstat(fd)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(output, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        check_identity()
        # No fallback to a truncating write if the filesystem cannot link.
        os.link(temporary, destination)
    finally:
        try:
            if os.path.samestat(temporary.lstat(), owned_stat):
                temporary.unlink()
        except FileNotFoundError:
            pass


if __name__ == '__main__':
    main()
