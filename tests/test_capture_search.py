import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from romancer import capture_store as store
from romancer.capture_ingest import import_capture, add_annotations
from romancer.history import init_history, register_build
from test_capture_ingest import entry
from test_capture_store import capture_fixture


class CaptureSearchTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(store, 'search_captures', None)), 'capture search is not implemented')
        self.tmp = tempfile.TemporaryDirectory(prefix='capture search ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        store.init_capture_store(self.root)
        init_history(self.root)
        self.game = self.root / 'game.bin'
        self.game.write_bytes(b'ABCD')
        config = dict(inputs=[dict(role='original', path=str(self.game))], output=str(self.game),
                      adapter=dict(name='generic', version='1'), profile=dict(name='test', version='1'), settings={})
        self.build = register_build(self.root, config, self.root)
        config['settings'] = {'different': True}
        self.other = register_build(self.root, config, self.root)
        self.record, self.blobs = capture_fixture(self.root)
        self.record['build'] = dict(build_id=self.build['build_id'], identity=self.build['identity'],
                                    locations=self.build['locations'], association='imported_claim')
        store._insert_capture(self.root, self.record, self.blobs)
        self.capture_id = self.record['capture_id']

    def search(self, **query):
        return store.search_captures(self.root, query)

    def test_combined_text_scene_and_build_filters_keep_import_labels(self):
        add_annotations(self.root, self.capture_id, [entry('The gate opens'), entry('Courtyard', 'scene')])
        found = self.search(text='GATE', scene='courtyard', build_id=self.build['build_id'])
        self.assertEqual([r['capture_id'] for r in found['matches']], [self.capture_id])
        hit = found['matches'][0]
        self.assertEqual(hit['origin'], 'imported_image')
        self.assertEqual(hit['association'], 'imported_claim')
        self.assertFalse(hit['natural_progress_verified'])
        self.assertEqual(hit['image_integrity'], 'NOT_CHECKED')
        self.assertEqual(hit['build_currentness'], 'NOT_CHECKED')
        self.assertEqual(self.search(text='gate', scene='Elsewhere')['matches'], [])
        self.assertEqual(self.search(build_id=self.other['build_id'])['matches'], [])

    def test_unicode_and_sql_looking_text_are_literals(self):
        add_annotations(self.root, self.capture_id, [entry('\u9580\u304c\u958b\u304f Stra\u00dfe 100%_ \' OR 1=1 --')])
        for text in ('\u9580\u304c', 'STRASSE', '100%_', "' OR 1=1 --"):
            self.assertEqual(len(self.search(text=text)['matches']), 1)
        self.assertEqual(self.search(text='100XX')['matches'], [])

    def test_scene_only_matches_scene_annotations(self):
        add_annotations(self.root, self.capture_id, [entry('Courtyard')])
        self.assertEqual(self.search(scene='Courtyard')['matches'], [])

    def test_only_annotations_are_searchable_not_source_or_serialized_metadata(self):
        source = self.root / 'secret text.txt'
        source.write_bytes(b'UNANNOTATED_SECRET')
        add_annotations(self.root, self.capture_id, [entry('public supplied label')], source)
        for text in ('UNANNOTATED_SECRET', 'imported_image', self.capture_id):
            self.assertEqual(self.search(text=text)['matches'], [])

    def test_superseded_labels_require_explicit_inclusion(self):
        old = add_annotations(self.root, self.capture_id, [entry('closed')])['annotation_ids'][0]
        add_annotations(self.root, self.capture_id, [entry('opened', supersedes=old)])
        self.assertEqual(self.search(text='closed')['matches'], [])
        self.assertEqual(len(self.search(text='opened')['matches']), 1)
        self.assertEqual(len(self.search(text='closed', include_superseded=True)['matches']), 1)

    def test_resource_search_requires_full_build_identity(self):
        resource = dict(build_id=self.build['build_id'], artifact_role='output',
                        artifact_sha256=hashlib.sha256(b'ABCD').hexdigest(), resource_id='dialogue', offset=1, length=2)
        add_annotations(self.root, self.capture_id, [entry(kind='resource', resource=resource)])
        self.assertEqual(len(self.search(build_id=self.build['build_id'], resource_id='dialogue')['matches']), 1)
        self.assertEqual(self.search(build_id=self.other['build_id'], resource_id='dialogue')['matches'], [])
        with self.assertRaises(ValueError):
            self.search(resource_id='dialogue')

    def test_corrupt_metadata_is_not_silently_skipped_even_outside_filter(self):
        db = self.root / store.STORE_NAME / store.DB_NAME
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute("UPDATE captures SET record_json='{}'")
        with self.assertRaises(ValueError):
            self.search(build_id=self.other['build_id'])

    def test_orphan_annotations_block_even_empty_filtered_search(self):
        add_annotations(self.root, self.capture_id, [entry('orphaned label')])
        db = self.root / store.STORE_NAME / store.DB_NAME
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute('PRAGMA foreign_keys=OFF')
            connection.execute('DELETE FROM captures')
            self.assertEqual(connection.execute('SELECT count(*) FROM annotations').fetchone()[0], 1)
            self.assertEqual(connection.execute('PRAGMA quick_check').fetchall(), [('ok',)])
        for query in ({}, {'text': 'unrelated'}, {'build_id': self.other['build_id']}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                store.search_captures(self.root, query)

    def test_search_does_not_read_or_claim_image_integrity(self):
        db = self.root / store.STORE_NAME / store.DB_NAME
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute('UPDATE blobs SET content=? WHERE sha256=?', (b'broken', self.record['image']['blob_sha256']))
        self.assertEqual(self.search()['matches'][0]['image_integrity'], 'NOT_CHECKED')
        with self.assertRaises(ValueError):
            store.get_capture(self.root, self.capture_id)

    def test_pagination_is_deterministic_and_exclusive(self):
        expected = [self.capture_id]
        for _ in range(3):
            record = copy.deepcopy(self.record)
            record['capture_id'] = uuid.uuid4().hex
            store._insert_capture(self.root, record, self.blobs)
            expected.append(record['capture_id'])
        seen = []
        query = dict(limit=2)
        while True:
            page = store.search_captures(self.root, query)
            seen += [r['capture_id'] for r in page['matches']]
            if not page['has_more']:
                break
            query['after_id'] = page['next_after_id']
        self.assertEqual(seen, sorted(expected))

    def test_invalid_query_types_and_budgets_are_rejected(self):
        for query in ([], {'limit': True}, {'limit': 0}, {'limit': 101}, {'text': 'x'*257},
                      {'include_superseded': 1}, {'origin': 'verified'}, {'run_mode': 'natural'}, {'unknown': 1}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                store.search_captures(self.root, query)

    def test_annotation_retrieval_has_bounded_pages(self):
        added = add_annotations(self.root, self.capture_id, [entry(str(i)) for i in range(40)])['annotation_ids']
        first = store.get_capture(self.root, self.capture_id, limit=32)
        second = store.get_capture(self.root, self.capture_id, limit=32,
                                    after_annotation_id=first['next_after_annotation_id'])
        self.assertEqual([a['annotation_id'] for a in first['annotations']+second['annotations']], sorted(added))
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])

    def test_identical_pixels_do_not_promote_imports_to_native(self):
        # Internal synthetic record exercises filtering only; native acceptance is separate.
        native = copy.deepcopy(self.record)
        native['capture_id'] = uuid.uuid4().hex
        native['origin'] = 'native_worker'
        native['import_source'] = None
        native['build']['association'] = 'measured_run_output'
        native['run'] = dict(run_id=uuid.uuid4().hex, worker_tool_version='test', core_sha256='a'*64,
                            game_sha256=self.build['identity']['output']['sha256'], core_info={}, av={}, core_options={},
                            game_dependencies=[], frame=dict(index=1, width=2, height=1, pitch=6,
                            pixel_format='RGB24', sha256=native['image']['rgb_sha256']), run_mode='cold_boot',
                            provenance=dict(origin='cold_boot', state_derived=False, ancestor_state_sha256=None,
                                            parent_checkpoint_sha256=None, trust='current_worker'),
                            dependency_coverage='supplied_paths_only', steps=[dict(frames=1, buttons=[], port=0, frame_index=1)],
                            initial_state_sha256=None, initial_game_save_sha256=None,
                            build_checks=dict(before='b'*32, after='c'*32))
        store._insert_capture(self.root, native, self.blobs)
        self.assertEqual([r['capture_id'] for r in self.search(origin='native_worker', run_mode='cold_boot')['matches']], [native['capture_id']])
        self.assertEqual(self.search(origin='imported_image', run_mode='cold_boot')['matches'], [])
        for changes in [dict(run_mode='imported_save_state'),
                        dict(provenance=dict(native['run']['provenance'], ancestor_state_sha256='d'*64)),
                        dict(steps=[]), dict(frame=dict(native['run']['frame'], index=True))]:
            bad = copy.deepcopy(native)
            bad['capture_id'] = uuid.uuid4().hex
            bad['run'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                store._insert_capture(self.root, bad, self.blobs)


if __name__ == '__main__':
    unittest.main()
