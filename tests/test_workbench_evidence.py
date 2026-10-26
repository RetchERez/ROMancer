"""Application evidence-key initialization and existing-file trust boundaries."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import nullcontext
import multiprocessing
import os
from pathlib import Path
from queue import Empty
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from romancer import workbench_evidence as evidence


def _key_process(project, results, *, waiting=None, release=None, started=None):
    """Spawn-safe worker; hold the visible-empty-key race open in one process."""
    project = Path(project)
    real_open = Path.open

    class PausedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def write(self, raw):
            waiting.set()
            if not release.wait(10):
                raise AssertionError('process writer was not released')
            return self.stream.write(raw)

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

    def pause_key_creation(path, mode='r', *args, **kwargs):
        stream = real_open(path, mode, *args, **kwargs)
        return PausedWriter(stream) if path == project/'.evidence-key' and mode == 'xb' else stream

    try:
        if started is not None:
            started.set()
        with patch.object(Path, 'open', pause_key_creation) if waiting is not None else nullcontext():
            results.put(('ok', evidence._key(project)))
    except BaseException as exc:
        results.put(('error', type(exc).__name__, str(exc)))


class EvidenceKeyTests(unittest.TestCase):
    def test_separate_process_reader_cannot_observe_unfinished_first_key(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            results = context.Queue()
            waiting, release, started = context.Event(), context.Event(), context.Event()
            first = context.Process(target=_key_process, args=(folder, results), kwargs={'waiting': waiting, 'release': release})
            second = context.Process(target=_key_process, args=(folder, results), kwargs={'started': started})
            first.start()
            try:
                self.assertTrue(waiting.wait(10))
                self.assertEqual((project/'.evidence-key').stat().st_size, 0)
                second.start()
                self.assertTrue(started.wait(10))
                with self.assertRaises(Empty):
                    results.get(timeout=.2)
            finally:
                release.set()
                for process in (first, second):
                    if process.pid is not None:
                        process.join(10)
                        if process.is_alive():
                            process.terminate()
                            process.join(5)
            answers = [results.get(timeout=5), results.get(timeout=5)]
            self.assertEqual(answers[0][0], 'ok', answers)
            self.assertEqual(answers[1][0], 'ok', answers)
            self.assertEqual(answers[0][1], answers[1][1])
            self.assertEqual(first.exitcode, 0)
            self.assertEqual(second.exitcode, 0)
            self.assertEqual(len((project/'.evidence-key').read_bytes()), 32)
            results.close()
            results.join_thread()

    def test_concurrent_reader_cannot_observe_unfinished_first_key(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            key_path = project/'.evidence-key'
            writer_waiting, allow_write, reader_started = threading.Event(), threading.Event(), threading.Event()
            real_open = Path.open

            class PausedWriter:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def write(self, raw):
                    writer_waiting.set()
                    if not allow_write.wait(5):
                        raise AssertionError('test writer was not released')
                    return self.stream.write(raw)

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

            def pause_key_creation(path, mode='r', *args, **kwargs):
                stream = real_open(path, mode, *args, **kwargs)
                return PausedWriter(stream) if path == key_path and mode == 'xb' else stream

            def read_key():
                reader_started.set()
                return evidence._key(project)

            with patch.object(Path, 'open', pause_key_creation), ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(evidence._key, project)
                try:
                    self.assertTrue(writer_waiting.wait(5))
                    self.assertEqual(key_path.stat().st_size, 0)  # Deliberately hold the prior race window open.
                    second = pool.submit(read_key)
                    self.assertTrue(reader_started.wait(5))
                    with self.assertRaises(TimeoutError):
                        second.result(timeout=.15)
                finally:
                    allow_write.set()
                self.assertEqual(first.result(timeout=5), second.result(timeout=5))
            self.assertEqual(len(key_path.read_bytes()), 32)
            self.assertEqual(key_path.stat().st_nlink, 1)

    def test_existing_invalid_key_is_rejected_and_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            path = project/'.evidence-key'
            for length in (0, 1, 31, 33):
                with self.subTest(length=length):
                    raw = bytes(length)
                    path.write_bytes(raw)
                    with patch.object(evidence.secrets, 'token_bytes', side_effect=AssertionError('must not regenerate')):
                        with self.assertRaisesRegex(ValueError, 'invalid evidence key'):
                            evidence._key(project)
                    self.assertEqual(path.read_bytes(), raw)

    def test_existing_hardlink_or_symlink_key_remains_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            original = project/'other-key'
            original.write_bytes(b's'*32)
            key = project/'.evidence-key'
            os.link(original, key)
            with self.assertRaisesRegex(ValueError, 'invalid evidence key'):
                evidence._key(project)
            key.unlink()
            try:
                key.symlink_to(original)
            except OSError:
                return  # Windows installations may not grant symlink creation.
            with self.assertRaisesRegex(ValueError, 'linked path'):
                evidence._key(project)

    def test_coordination_file_rejects_links_without_touching_their_target(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            original = project/'other-lock'
            original.write_bytes(b'unchanged')
            lock = project/'.evidence-key.lock'
            os.link(original, lock)
            with self.assertRaisesRegex(ValueError, 'invalid evidence key lock'):
                evidence._key(project)
            self.assertEqual(original.read_bytes(), b'unchanged')
            self.assertFalse((project/'.evidence-key').exists())
            lock.unlink()
            try:
                lock.symlink_to(original)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, 'linked path'):
                evidence._key(project)
            self.assertEqual(original.read_bytes(), b'unchanged')

    def test_coordination_file_persists_but_is_not_exported_in_private_backup(self):
        from romancer import workbench_projects as projects
        from romancer.project_portability import backup_project
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = Path(projects.create_project(root/'projects', 'Key lock')['path'])
            key = evidence._key(project)
            self.assertEqual(evidence._key(project), key)
            self.assertTrue((project/'.evidence-key.lock').is_file())
            archive = root/'private.zip'
            backup_project(project, archive, ['reports'])
            with zipfile.ZipFile(archive) as saved:
                self.assertIn('.evidence-key', saved.namelist())
                self.assertNotIn('.evidence-key.lock', saved.namelist())

    @unittest.skipIf(os.name == 'nt', 'POSIX mode bits do not describe Windows ACLs')
    def test_new_key_keeps_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence._key(folder)
            self.assertEqual((Path(folder)/'.evidence-key').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
