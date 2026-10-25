import copy
from contextlib import closing
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from romancer.libretro_frontend import write_rgb_png


def capture_fixture(root, *, capture_id=None):
    image = root / 'source image.png'
    rgb = bytes([255, 0, 0, 0, 255, 0])
    write_rgb_png(image, 2, 1, rgb)
    raw = image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    context = dict(captured_utc=None, game_sha256=None, core_sha256=None,
                   run_mode=None, state_derived=None, source_note=None)
    manifest = json.dumps(dict(build_id=None, declared_context=context, annotations=[]),
                          sort_keys=True, separators=(',', ':')).encode()
    manifest_hash = hashlib.sha256(manifest).hexdigest()
    record = dict(schema_version=1, canonical_version=1,
                  capture_id=capture_id or uuid.uuid4().hex,
                  created_utc='2026-09-12T12:00:00+00:00', tool_version='test',
                  origin='imported_image', natural_progress_verified=False,
                  image=dict(blob_sha256=digest, byte_size=len(raw), width=2, height=1,
                             rgb_sha256=hashlib.sha256(rgb).hexdigest(),
                             media_type='image/png', normalization='rgb24'),
                  build=None, run=None,
                  import_source=dict(path_hint=str(image), image_sha256=digest,
                                     manifest_sha256=manifest_hash,
                                     manifest_path_hint=None,
                                     manifest_kind='canonical_api_input', declared_context=context))
    blobs = {digest: dict(media_type='image/png', content=raw),
             manifest_hash: dict(media_type='application/json', content=manifest)}
    return record, blobs


class CaptureStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.capture_store'),
                             'capture store is not implemented')
        self.store = importlib.import_module('romancer.capture_store')
        self.tmp = tempfile.TemporaryDirectory(prefix='capture store ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store.init_capture_store(self.root)
        self.db = self.root / '.romancer-evidence' / 'captures.sqlite3'

    def insert(self):
        record, blobs = capture_fixture(self.root)
        self.store._insert_capture(self.root, record, blobs)
        return record, blobs

    def test_manifest_path_hint_is_required_and_kind_bound(self):
        record, _ = capture_fixture(self.root)
        missing = copy.deepcopy(record)
        missing['import_source'].pop('manifest_path_hint', None)
        with self.assertRaises(ValueError):
            self.store._validate_capture(missing)
        for kind, hint in [('original_file', None), ('original_file', ''),
                           ('original_file', 'relative.json'),
                           ('canonical_api_input', str(self.root / 'not supplied.json'))]:
            bad = copy.deepcopy(record)
            bad['import_source'].update(manifest_kind=kind, manifest_path_hint=hint)
            with self.subTest(kind=kind, hint=hint), self.assertRaises(ValueError):
                self.store._validate_capture(bad)

    def test_round_trip_deduplicates_bytes_not_capture_context(self):
        record, blobs = self.insert()
        second = copy.deepcopy(record)
        second['capture_id'] = uuid.uuid4().hex
        self.store._insert_capture(self.root, second, blobs)
        result = self.store.get_capture(self.root, record['capture_id'])
        self.assertEqual(result['record'], record)
        self.assertEqual(result['png_bytes'], (self.root / 'source image.png').read_bytes())
        self.assertEqual(result['image_integrity'], 'PASS')
        self.assertEqual(result['build_currentness'], 'NOT_CHECKED')
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM captures').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM blobs').fetchone()[0], 2)

    def test_init_preserves_legacy_and_refuses_existing_store(self):
        legacy = self.root / 'project.json'
        legacy.write_bytes(b'{"private":"original"}')
        before = self.db.read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.store.init_capture_store(self.root)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(legacy.read_bytes(), b'{"private":"original"}')

    def test_failed_blob_hash_inserts_nothing(self):
        record, blobs = capture_fixture(self.root)
        blobs[record['image']['blob_sha256']]['content'] = b'wrong'
        with self.assertRaises(ValueError):
            self.store._insert_capture(self.root, record, blobs)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM captures').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM blobs').fetchone()[0], 0)

    def test_transaction_failure_keeps_previous_capture(self):
        record, blobs = self.insert()
        second = copy.deepcopy(record)
        second['capture_id'] = uuid.uuid4().hex
        with patch.object(self.store, '_before_commit', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.store._insert_capture(self.root, second, blobs)
        self.assertEqual(self.store.get_capture(self.root, record['capture_id'])['record'], record)
        with self.assertRaises(ValueError):
            self.store.get_capture(self.root, second['capture_id'])

    def test_expired_publication_rolls_back_even_after_insert(self):
        record, blobs = capture_fixture(self.root)
        with self.assertRaises(TimeoutError):
            self.store._insert_capture(self.root, record, blobs, publication_deadline=time.monotonic()-1)
        with patch.object(self.store, '_before_commit', side_effect=lambda *args: time.sleep(0.03)):
            with self.assertRaises(TimeoutError):
                self.store._insert_capture(self.root, record, blobs, publication_deadline=time.monotonic()+0.01)
        with self.assertRaises(ValueError):
            self.store.get_capture(self.root, record['capture_id'])

    def test_aggregate_blob_budget_counts_unique_bytes(self):
        record, blobs = capture_fixture(self.root)
        total = sum(len(blob['content']) for blob in blobs.values())
        with patch.object(self.store, 'MAX_BLOB_TOTAL', total-1):
            with self.assertRaises(ValueError):
                self.store._insert_capture(self.root, record, blobs)
        with patch.object(self.store, 'MAX_BLOB_TOTAL', total):
            self.store._insert_capture(self.root, record, blobs)
            record['capture_id'] = uuid.uuid4().hex
            self.store._insert_capture(self.root, record, blobs)

    def test_capture_and_metadata_quotas(self):
        record, blobs = self.insert()
        record['capture_id'] = uuid.uuid4().hex
        for constant, limit in [('MAX_CAPTURES', 1), ('MAX_METADATA_TOTAL', 1)]:
            with patch.object(self.store, constant, limit), self.assertRaises(ValueError):
                self.store._insert_capture(self.root, record, blobs)

    def test_corrupted_image_or_metadata_never_exports(self):
        record, blobs = self.insert()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('UPDATE blobs SET content=? WHERE sha256=?',
                               (b'bad', record['image']['blob_sha256']))
        with self.assertRaises(ValueError):
            self.store.get_capture(self.root, record['capture_id'])
        with self.assertRaises(ValueError):
            self.store.export_capture(self.root, record['capture_id'], self.root / 'export.png')
        self.assertFalse((self.root / 'export.png').exists())

    def test_metadata_corruption_is_rejected(self):
        record, _ = self.insert()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE captures SET record_json='{}'")
        with self.assertRaises(ValueError):
            self.store.get_capture(self.root, record['capture_id'])

    def test_export_no_clobber_source_or_store(self):
        record, blobs = self.insert()
        out = self.root / 'new export.png'
        self.store.export_capture(self.root, record['capture_id'], out)
        self.assertEqual(out.read_bytes(), blobs[record['image']['blob_sha256']]['content'])
        for target in [out, self.root / 'source image.png', self.db, self.db.parent / 'unapproved.txt']:
            with self.subTest(target=target), self.assertRaises((ValueError, OSError)):
                self.store.export_capture(self.root, record['capture_id'], target)

    def test_retrieval_survives_source_removal(self):
        record, blobs = self.insert()
        (self.root / 'source image.png').unlink()
        self.assertEqual(self.store.get_capture(self.root, record['capture_id'])['png_bytes'],
                         blobs[record['image']['blob_sha256']]['content'])

    def test_unknown_sidecars_and_busy_lock_are_preserved(self):
        for name in ('captures.sqlite3-journal', 'unknown', 'operation.lock'):
            item = self.db.parent / name
            item.write_bytes(b'preserve')
            try:
                with patch.object(self.store, 'LOCK_TIMEOUT', 0.01):
                    with self.assertRaises((ValueError, OSError)):
                        self.store.get_capture(self.root, 'a'*32)
                self.assertEqual(item.read_bytes(), b'preserve')
            finally:
                item.unlink()

    def test_hardlinked_database_is_refused(self):
        alias = self.root / 'alias.db'
        os.link(self.db, alias)
        try:
            with self.assertRaises(ValueError):
                self.store.get_capture(self.root, 'a'*32)
        finally:
            alias.unlink()

    def test_store_owner_and_schema_are_checked(self):
        owner = self.db.parent / 'owner.json'
        data = json.loads(owner.read_text())
        data['directory_identity'] = [-1, -1]
        owner.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.store.get_capture(self.root, 'a'*32)

    def test_source_json_can_also_be_reused_as_annotation_source(self):
        from romancer.capture_ingest import add_annotations
        from test_capture_ingest import entry
        record, blobs = self.insert()
        digest = record['import_source']['manifest_sha256']
        source = self.root / 'same manifest.json'
        source.write_bytes(blobs[digest]['content'])
        add_annotations(self.root, record['capture_id'], [entry()], source)
        self.assertEqual(len(self.store.get_capture(self.root, record['capture_id'])['annotations']), 1)

    def test_metadata_budget_checked_before_materializing_sql_text(self):
        record, _ = self.insert()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('UPDATE captures SET record_json=?', ('x'*(self.store.MAX_RECORD+1),))
        with patch.object(self.store, '_decode', side_effect=AssertionError('oversize text was fetched')):
            with self.assertRaises(ValueError):
                self.store.get_capture(self.root, record['capture_id'])

    def test_lock_replacement_before_commit_rolls_back(self):
        record, blobs = capture_fixture(self.root)
        lock = self.db.parent / 'operation.lock'
        real = self.store._before_commit
        replacement = self.root / 'replacement lock'
        replacement.write_bytes(b'not owned')
        def replace_then_check(*args):
            lock.unlink()
            os.link(replacement, lock)
            real(*args)
        with patch.object(self.store, '_before_commit', side_effect=replace_then_check):
            with self.assertRaises(ValueError):
                self.store._insert_capture(self.root, record, blobs)
        self.assertEqual(lock.read_bytes(), b'not owned')
        lock.unlink()
        with self.assertRaises(ValueError):
            self.store.get_capture(self.root, record['capture_id'])

    def test_two_writers_cannot_exceed_capture_quota(self):
        record, blobs = capture_fixture(self.root)
        other = copy.deepcopy(record)
        other['capture_id'] = uuid.uuid4().hex
        barrier = threading.Barrier(3)
        results = []
        def insert(item):
            barrier.wait()
            try:
                self.store._insert_capture(self.root, item, blobs)
                results.append('inserted')
            except ValueError:
                results.append('refused')
        with patch.object(self.store, 'MAX_CAPTURES', 1):
            threads = [threading.Thread(target=insert, args=(item,)) for item in (record, other)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
        self.assertCountEqual(results, ['inserted', 'refused'])

    def test_symlink_project_and_unknown_database_schema_are_refused(self):
        alias = self.root / 'alias project'
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError:
            pass
        else:
            try:
                with self.assertRaises(ValueError):
                    self.store.get_capture(alias, 'a'*32)
            finally:
                alias.unlink()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('CREATE TABLE unexpected (value TEXT)')
        with self.assertRaises(ValueError):
            self.store.get_capture(self.root, 'a'*32)

    @unittest.skipUnless(os.name == 'nt', 'Windows drive-relative path syntax')
    def test_drive_relative_path_is_rejected_before_normalization(self):
        with self.assertRaises(ValueError):
            self.store._path('C:source image.png')

    def test_aggregate_quota_counts_actual_blob_bytes_not_stored_size_claim(self):
        record, blobs = self.insert()
        old_digest = record['image']['blob_sha256']
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('UPDATE blobs SET size=0 WHERE sha256=?', (old_digest,))
        rgb = bytes([0, 0, 255, 255, 0, 0])
        image = self.root / 'other.png'
        write_rgb_png(image, 2, 1, rgb)
        raw = image.read_bytes()
        new_digest = hashlib.sha256(raw).hexdigest()
        other = copy.deepcopy(record)
        other['capture_id'] = uuid.uuid4().hex
        other['image'].update(blob_sha256=new_digest, byte_size=len(raw), rgb_sha256=hashlib.sha256(rgb).hexdigest())
        other['import_source']['image_sha256'] = new_digest
        new_blobs = {new_digest: dict(media_type='image/png', content=raw)}
        actual_total = sum(len(b['content']) for b in blobs.values()) + len(raw)
        with patch.object(self.store, 'MAX_BLOB_TOTAL', actual_total-1), self.assertRaises(ValueError):
            self.store._insert_capture(self.root, other, new_blobs)


if __name__ == '__main__':
    unittest.main()
