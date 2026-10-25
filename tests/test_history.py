import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch


def service():
    return importlib.import_module('romancer.history')


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ROMancer history ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.source = self.root / 'original.bin'
        self.output = self.root / 'translated.bin'
        self.source.write_bytes(b'original synthetic bytes')
        self.output.write_bytes(b'translated synthetic bytes')
        self.store = self.project / '.romancer-history'
        self.db = self.store / 'history.sqlite3'
        self.config = {'inputs': [{'role': 'original', 'path': 'original.bin'}],
                       'output': 'translated.bin',
                       'adapter': {'name': 'generic', 'version': '1'},
                       'profile': {'name': 'custom', 'version': '1'}, 'settings': {}}

    def init(self):
        return service().init_history(self.project)

    def register(self, config=None, base=None):
        return service().register_build(self.project, self.config if config is None else config,
                                        self.root if base is None else base)

    def rows(self, table):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            return connection.execute(f'SELECT * FROM {table}').fetchall()

    def test_service_interfaces_exist(self):
        module = service()
        for name in ('init_history', 'register_build', 'get_build', 'check_build', 'evaluate_build'):
            self.assertTrue(callable(getattr(module, name, None)), name)

    def test_get_build_roundtrip_preserves_database_bytes_and_all_rows(self):
        (self.project / 'project.json').write_text('{"name":"synthetic"}', encoding='ascii')
        self.init()
        build = self.register()
        service().check_build(self.project, build['build_id'])
        tables = ('store_meta', 'builds', 'evidence', 'legacy_metadata')
        rows = {table: self.rows(table) for table in tables}
        files = {path.name: path.read_bytes() for path in self.store.iterdir()}
        result = service().get_build(self.project, build['build_id'])
        expected = {key: build[key] for key in ('schema_version', 'build_id', 'identity', 'locations')}
        self.assertEqual(result, expected)
        self.assertEqual(result, json.loads(rows['builds'][0][1]))
        self.assertEqual({table: self.rows(table) for table in tables}, rows)
        self.assertEqual({path.name: path.read_bytes() for path in self.store.iterdir()}, files)

    def test_get_build_detaches_nested_caller_mutation(self):
        self.init()
        self.config['settings'] = {'nested': [{'enabled': True}]}
        build = self.register()
        expected = {key: build[key] for key in ('schema_version', 'build_id', 'identity', 'locations')}
        before = self.db.read_bytes()
        first = service().get_build(self.project, build['build_id'])
        first['identity']['settings']['nested'][0]['enabled'] = False
        first['identity']['inputs'][0]['sha256'] = '0' * 64
        first['locations']['inputs'][0]['path'] = 'caller changed'
        first['locations']['output'] = 'caller output'
        first['build_id'] = 'caller ID'
        self.assertEqual(service().get_build(self.project, build['build_id']), expected)
        self.assertEqual(self.db.read_bytes(), before)

    def test_get_build_does_not_measure_changed_or_missing_artifacts(self):
        self.init()
        build = self.register()
        before = self.db.read_bytes()
        self.source.write_bytes(b'changed after registration')
        self.output.unlink()
        real_read = service()._read_stable
        def read(path, *args, **kwargs):
            if path in (self.source, self.output):
                self.fail('get_build must not read artifact content')
            return real_read(path, *args, **kwargs)
        with patch.object(service(), '_read_stable', side_effect=read):
            result = service().get_build(self.project, build['build_id'])
        self.assertEqual(result['identity'], build['identity'])
        self.assertEqual(result['locations'], build['locations'])
        self.assertEqual(set(result), {'schema_version', 'build_id', 'identity', 'locations'})
        self.assertEqual(self.rows('evidence'), [])
        self.assertEqual(self.db.read_bytes(), before)

    def test_get_build_rejects_invalid_and_missing_ids_without_mutation(self):
        self.init()
        self.register()
        before = self.db.read_bytes()
        for identifier in (None, 1, [], '', 'g' * 64, 'A' * 64, '0' * 63, '0' * 65):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(ValueError, 'invalid.*identifier'):
                service().get_build(self.project, identifier)
        with self.assertRaisesRegex(ValueError, 'build ID not found'):
            service().get_build(self.project, '0' * 64)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertFalse((self.store / 'operation.lock').exists())

    def test_get_build_rejects_corrupt_record_hash_identity_and_locations(self):
        self.init()
        build = self.register()
        original = json.loads(self.rows('builds')[0][1])
        for fault in ('checksum', 'identity', 'locations', 'extra-field'):
            with self.subTest(fault=fault):
                record = copy.deepcopy(original)
                if fault == 'identity':
                    record['identity']['output']['sha256'] = '0' * 64
                elif fault == 'locations':
                    record['locations']['output'] = 'relative.bin'
                elif fault == 'extra-field':
                    record['status'] = 'PASS'
                raw = service().canonical_json(record)
                digest = '0' * 64 if fault == 'checksum' else hashlib.sha256(raw.encode('utf-8')).hexdigest()
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    connection.execute('UPDATE builds SET record_json=?, record_sha256=?', (raw, digest))
                before = self.db.read_bytes()
                with self.assertRaises(ValueError):
                    service().get_build(self.project, build['build_id'])
                self.assertEqual(self.db.read_bytes(), before)
                self.assertFalse((self.store / 'operation.lock').exists())

    def test_get_build_rejects_corrupt_database_without_mutation(self):
        self.init()
        build = self.register()
        self.db.write_bytes(b'not a SQLite database')
        with self.assertRaises((ValueError, sqlite3.Error)):
            service().get_build(self.project, build['build_id'])
        self.assertEqual(self.db.read_bytes(), b'not a SQLite database')
        self.assertFalse((self.store / 'operation.lock').exists())

    def test_get_build_honors_existing_lock_without_mutation(self):
        self.init()
        build = self.register()
        before = self.db.read_bytes()
        lock = self.store / 'operation.lock'
        lock.write_bytes(b'other operation')
        with patch.object(service(), 'LOCK_TIMEOUT', 0.03):
            with self.assertRaisesRegex(OSError, 'lock busy or abandoned'):
                service().get_build(self.project, build['build_id'])
        self.assertEqual(lock.read_bytes(), b'other operation')
        self.assertEqual(self.db.read_bytes(), before)

    def test_init_and_register_synthetic_artifacts(self):
        result = self.init()
        self.assertTrue(result['ok'])
        self.assertEqual(result['schema_version'], 1)
        build = self.register()
        self.assertTrue(build['ok'])
        self.assertEqual(len(build['build_id']), 64)
        self.assertEqual(build['scope'], 'artifact_identity')
        self.assertEqual(len(self.rows('builds')), 1)
        self.assertEqual(len(self.rows('evidence')), 0)
        self.assertEqual({p.name for p in self.store.iterdir()}, {'owner.json', 'history.sqlite3'})
        self.assertEqual(self.source.read_bytes(), b'original synthetic bytes')

    def test_identity_ignores_locations_and_object_key_order(self):
        self.init()
        first = self.register()
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        (elsewhere / 'original.bin').write_bytes(self.source.read_bytes())
        (elsewhere / 'translated.bin').write_bytes(self.output.read_bytes())
        config = dict(reversed(list(self.config.items())))
        second = self.register(config, elsewhere)
        self.assertEqual(first['build_id'], second['build_id'])
        self.assertEqual(len(self.rows('builds')), 1)

    def test_identity_includes_inputs_output_settings_profile_adapter_and_version(self):
        self.init()
        original_id = self.register()['build_id']
        for key in ('settings', 'profile', 'adapter'):
            config = copy.deepcopy(self.config)
            config[key] = {'mode': 2} if key == 'settings' else {'name': key, 'version': '2'}
            with self.subTest(key=key):
                self.assertNotEqual(self.register(config)['build_id'], original_id)
        for path in (self.source, self.output):
            before = path.read_bytes()
            path.write_bytes(before + b'!')
            self.assertNotEqual(self.register()['build_id'], original_id)
            path.write_bytes(before)
        with patch.object(service(), 'ROMANCER_VERSION', 'test-version'):
            self.assertNotEqual(self.register()['build_id'], original_id)

    def test_ordered_distinct_input_roles_affect_identity(self):
        self.init()
        config = copy.deepcopy(self.config)
        config['inputs'].append({'role': 'second', 'path': 'translated.bin'})
        first = self.register(config)['build_id']
        config['inputs'].reverse()
        self.assertNotEqual(first, self.register(config)['build_id'])

    def test_strict_configuration_rejects_missing_unknown_and_malformed_fields(self):
        self.init()
        invalid = []
        for key in self.config:
            config = copy.deepcopy(self.config)
            del config[key]
            invalid.append(config)
        for key, value in [('extra', 1), ('settings', {'x': float('nan')}),
                           ('settings', {'x': float('inf')}), ('settings', {1: 'value'}),
                           ('settings', {'x': (1, 2)}), ('inputs', []), ('output', ''),
                           ('adapter', {'name': 'generic', 'version': 1}),
                           ('profile', {'name': 'custom', 'version': '1', 'extra': 0})]:
            config = copy.deepcopy(self.config)
            config[key] = value
            invalid.append(config)
        config = copy.deepcopy(self.config)
        config['inputs'] *= 2
        invalid.append(config)
        config = copy.deepcopy(self.config)
        config['inputs'][0]['role'] = ' '
        invalid.append(config)
        for config in invalid:
            with self.subTest(config=repr(config)):
                with self.assertRaises(ValueError):
                    self.register(config)
        self.assertEqual(self.rows('builds'), [])

    def test_strict_json_rejects_duplicates_nonfinite_and_oversized_records(self):
        for text in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}', 'null trailing'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                service().strict_json_loads(text)
        with self.assertRaises(ValueError):
            service().canonical_json({'large': 'x' * (8 * 1024 * 1024 + 1)})

    def test_migration_preserves_bytes_and_does_not_promote_legacy_pass(self):
        project_raw = b'{ "name" : "synthetic" }\r\n'
        evidence_raw = b'[ {"status":"PASS", "claim":"legacy assertion"} ]\n'
        (self.project / 'project.json').write_bytes(project_raw)
        (self.project / 'evidence').mkdir()
        (self.project / 'evidence/evidence.json').write_bytes(evidence_raw)
        self.init()
        backups = {row[0]: row for row in self.rows('legacy_metadata')}
        for name, raw in [('project.json', project_raw), ('evidence/evidence.json', evidence_raw)]:
            self.assertEqual((self.project / name).read_bytes(), raw)
            self.assertEqual(backups[name][1], hashlib.sha256(raw).hexdigest())
            self.assertEqual(backups[name][2], raw)
            self.assertEqual(backups[name][3], 'imported_legacy_metadata')
        self.assertEqual(self.rows('evidence'), [])

    def test_malformed_legacy_json_is_unchanged_and_no_store_is_published(self):
        path = self.project / 'project.json'
        for raw in (b'{bad', b'{"x":1,"x":2}', b'{"x":NaN}', b'[]'):
            path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.init()
            self.assertEqual(path.read_bytes(), raw)
            self.assertFalse(self.store.exists())

    def test_existing_store_is_never_replaced(self):
        self.init()
        before = self.db.read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.init()
        self.assertEqual(self.db.read_bytes(), before)

    def test_preexisting_footprint_and_sidecars_are_preserved(self):
        self.store.mkdir()
        journal = self.store / 'history.sqlite3-journal'
        journal.write_bytes(b'unrelated bytes')
        with self.assertRaises((ValueError, OSError)):
            self.init()
        self.assertEqual(journal.read_bytes(), b'unrelated bytes')
        self.assertFalse(self.db.exists())

    def test_measured_check_and_fresh_evaluation_do_not_insert_status_evidence(self):
        self.init()
        build = self.register()
        check = service().check_build(self.project, build['build_id'])
        self.assertTrue(check['ok'])
        self.assertEqual(check['status'], 'PASS')
        self.assertEqual(check['origin'], 'measured')
        self.assertEqual(check['scope'], 'artifact_identity')
        result = service().evaluate_build(self.project, build['build_id'], [check['evidence_id']])
        self.assertTrue(result['ok'])
        self.assertEqual(len(self.rows('evidence')), 1)
        self.output.write_bytes(b'changed')
        result = service().evaluate_build(self.project, build['build_id'], [check['evidence_id']])
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(len(self.rows('evidence')), 1)

    def test_changed_and_missing_artifacts_save_failed_or_blocked_checks(self):
        self.init()
        build_id = self.register()['build_id']
        self.source.write_bytes(b'changed')
        failed = service().check_build(self.project, build_id)
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['status'], 'FAIL')
        self.assertFalse(service().evaluate_build(self.project, build_id, [failed['evidence_id']])['ok'])
        self.source.unlink()
        blocked = service().check_build(self.project, build_id)
        self.assertEqual(blocked['status'], 'BLOCKED')
        self.assertEqual(len(self.rows('evidence')), 2)

    def test_evaluation_rejects_empty_duplicate_missing_and_cross_build_evidence(self):
        self.init()
        first = self.register()['build_id']
        check = service().check_build(self.project, first)
        config = copy.deepcopy(self.config)
        config['settings'] = {'different_build': True}
        second = self.register(config)['build_id']
        for ids in ([], [check['evidence_id']] * 2):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                service().evaluate_build(self.project, first, ids)
        self.assertFalse(service().evaluate_build(self.project, first, ['0' * 32])['ok'])
        self.assertFalse(service().evaluate_build(self.project, second, [check['evidence_id']])['ok'])

    def test_every_access_rejects_future_schema_without_mutation(self):
        self.init()
        build_id = self.register()['build_id']
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('PRAGMA user_version=99')
        before = self.db.read_bytes()
        for action in (self.register, lambda: service().check_build(self.project, build_id),
                       lambda: service().get_build(self.project, build_id),
                       lambda: service().evaluate_build(self.project, build_id, ['0' * 32])):
            with self.assertRaises(ValueError):
                action()
            self.assertEqual(self.db.read_bytes(), before)

    def test_corrupt_build_record_cannot_be_used(self):
        self.init()
        build_id = self.register()['build_id']
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('UPDATE builds SET record_json=?', ('{}',))
        with self.assertRaises(ValueError):
            service().check_build(self.project, build_id)

    def test_imported_pass_cannot_be_forged_into_measured_scope(self):
        self.init()
        build_id = self.register()['build_id']
        check = service().check_build(self.project, build_id)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            record = json.loads(connection.execute('SELECT record_json FROM evidence').fetchone()[0])
            record['origin'] = 'imported'
            text = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            connection.execute('UPDATE evidence SET record_json=?, record_sha256=?', (text, digest))
        with self.assertRaises(ValueError):
            service().evaluate_build(self.project, build_id, [check['evidence_id']])

    def test_store_artifacts_and_external_hardlink_aliases_are_refused(self):
        self.init()
        before = self.db.read_bytes()
        for path in (self.db, self.store / 'history.sqlite3-journal', self.store / 'owner.json',
                     self.store / 'nested/file.bin'):
            config = copy.deepcopy(self.config)
            config['output'] = str(path)
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.register(config)
            self.assertEqual(self.db.read_bytes(), before)
        alias = self.root / 'database-alias.bin'
        os.link(self.db, alias)
        config = copy.deepcopy(self.config)
        config['inputs'][0]['path'] = str(alias)
        with self.assertRaises(ValueError):
            self.register(config)
        self.assertEqual(alias.read_bytes(), before)

    def test_sidecar_collisions_after_init_block_all_operations_and_preserve_external_original(self):
        self.init()
        build_id = self.register()['build_id']
        before = self.db.read_bytes()
        for suffix in ('-journal', '-wal', '-shm', '.unowned'):
            collision = self.store / ('history.sqlite3' + suffix)
            os.link(self.source, collision)
            for action in (self.register, lambda: service().check_build(self.project, build_id),
                           lambda: service().get_build(self.project, build_id),
                           lambda: service().evaluate_build(self.project, build_id, ['0' * 32])):
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    action()
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(collision.read_bytes(), b'original synthetic bytes')
            collision.unlink()

    def test_abandoned_lock_is_preserved_and_wait_is_bounded(self):
        self.init()
        lock = self.store / 'operation.lock'
        lock.write_bytes(b'abandoned lock')
        with patch.object(service(), 'LOCK_TIMEOUT', 0.03):
            with self.assertRaises((ValueError, OSError)):
                self.register()
        self.assertEqual(lock.read_bytes(), b'abandoned lock')

    def test_concurrent_insertions_preserve_all_unique_builds(self):
        self.init()
        def insert(index):
            config = copy.deepcopy(self.config)
            config['settings'] = {'index': index}
            return self.register(config)['build_id']
        with ThreadPoolExecutor(max_workers=4) as executor:
            ids = list(executor.map(insert, range(8)))
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(len(self.rows('builds')), 8)
        self.assertEqual({p.name for p in self.store.iterdir()}, {'owner.json', 'history.sqlite3'})

    def test_failed_commit_rolls_back_build_insertion(self):
        self.init()
        real_connect = sqlite3.connect
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            def authorize(action, arg1, arg2, database, trigger):
                return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and arg1 == 'COMMIT' else sqlite3.SQLITE_OK
            connection.set_authorizer(authorize)
            return connection
        with patch('romancer.history.sqlite3.connect', side_effect=connect):
            with self.assertRaises(sqlite3.Error):
                self.register()
        self.assertEqual(self.rows('builds'), [])
        self.assertEqual({p.name for p in self.store.iterdir()}, {'owner.json', 'history.sqlite3'})

    def test_metadata_rewrite_during_capture_aborts_and_preserves_new_bytes(self):
        path = self.project / 'project.json'
        path.write_bytes(b'{"name":"old"}')
        real_read = service()._read_stable
        changed = []
        def read(candidate, *args, **kwargs):
            result = real_read(candidate, *args, **kwargs)
            if Path(candidate) == path and not changed:
                changed.append(True)
                previous = path.stat()
                path.write_bytes(b'{"name":"new"}')
                os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            return result
        with patch.object(service(), '_read_stable', side_effect=read):
            with self.assertRaises(ValueError):
                self.init()
        self.assertEqual(path.read_bytes(), b'{"name":"new"}')
        self.assertFalse(self.store.exists())

    def test_failure_between_metadata_captures_leaves_no_store(self):
        (self.project / 'project.json').write_bytes(b'{}')
        (self.project / 'evidence').mkdir()
        evidence = self.project / 'evidence/evidence.json'
        evidence.write_bytes(b'[]')
        real_read = service()._read_stable
        def read(path, *args, **kwargs):
            if Path(path) == evidence:
                raise OSError('injected capture failure')
            return real_read(path, *args, **kwargs)
        with patch.object(service(), '_read_stable', side_effect=read):
            with self.assertRaises(OSError):
                self.init()
        self.assertFalse(self.store.exists())
        self.assertEqual(evidence.read_bytes(), b'[]')
        self.assertEqual((self.project / 'project.json').read_bytes(), b'{}')

    def test_metadata_replacement_creation_and_disappearance_abort_initialization(self):
        metadata = self.project / 'project.json'
        for change in ('replacement', 'creation', 'disappearance'):
            with self.subTest(change=change):
                metadata.write_bytes(b'{}')
                real_capture = service()._capture_metadata
                def capture(root):
                    result = real_capture(root)
                    if change == 'replacement':
                        other = self.root / 'replacement.json'
                        other.write_bytes(b'{}')
                        previous = metadata.stat()
                        os.utime(other, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                        os.replace(other, metadata)
                    elif change == 'creation':
                        (self.project / 'evidence').mkdir(exist_ok=True)
                        (self.project / 'evidence/evidence.json').write_bytes(b'[]')
                    else:
                        metadata.unlink()
                    return result
                with patch.object(service(), '_capture_metadata', side_effect=capture):
                    with self.assertRaises((ValueError, OSError)):
                        self.init()
                self.assertFalse(self.store.exists())
                (self.project / 'evidence/evidence.json').unlink(missing_ok=True)

    def test_metadata_over_limit_is_rejected_before_store_creation(self):
        path = self.project / 'project.json'
        data = b' ' * (8 * 1024 * 1024) + b'{}'
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            self.init()
        self.assertEqual(path.read_bytes(), data)
        self.assertFalse(self.store.exists())

    def test_initialization_commit_failure_rolls_back_and_allows_retry(self):
        metadata = self.project / 'project.json'
        metadata.write_bytes(b'{}')
        real_connect = sqlite3.connect
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_authorizer(lambda action, arg1, *rest:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and arg1 == 'COMMIT' else sqlite3.SQLITE_OK)
            return connection
        with patch('romancer.history.sqlite3.connect', side_effect=connect):
            with self.assertRaises(sqlite3.Error):
                self.init()
        self.assertEqual(metadata.read_bytes(), b'{}')
        self.assertFalse(self.store.exists())
        self.assertTrue(self.init()['ok'])

    def test_initialization_does_not_overwrite_competing_database(self):
        real_link = os.link
        def link(source, destination):
            Path(destination).write_bytes(b'other process')
            real_link(source, destination)
        with patch('romancer.history.os.link', side_effect=link):
            with self.assertRaises(FileExistsError):
                self.init()
        self.assertEqual(self.db.read_bytes(), b'other process')

    def test_initialization_temp_content_changed_after_verification_is_not_published(self):
        real_recheck = service()._recheck_metadata
        def recheck(*args):
            real_recheck(*args)
            temporary, = self.store.glob('.init-*.sqlite3')
            with temporary.open('r+b') as stream:
                stream.seek(100)
                stream.write(b'corrupt')
        with patch.object(service(), '_recheck_metadata', side_effect=recheck):
            with self.assertRaises(ValueError):
                self.init()
        self.assertFalse(self.db.exists())
        self.assertFalse(self.store.exists())

    def test_artifact_changed_while_other_artifact_is_hashed_blocks_registration(self):
        self.init()
        real_read = service()._read_stable
        changed = []
        def read(path, *args, **kwargs):
            result = real_read(path, *args, **kwargs)
            if path == self.output and not changed:
                changed.append(True)
                self.source.write_bytes(b'new original bytes')
            return result
        with patch.object(service(), '_read_stable', side_effect=read):
            with self.assertRaises(ValueError):
                self.register()
        self.assertEqual(self.rows('builds'), [])
        self.assertEqual(self.source.read_bytes(), b'new original bytes')

    def test_input_change_during_final_registration_sweep_blocks_insert(self):
        self.init()
        original = self.source.read_bytes()
        for change in ('rewrite', 'replacement', 'disappearance'):
            with self.subTest(change=change):
                self.source.write_bytes(original)
                real_read = service()._read_stable
                output_reads = []
                def read(path, *args, **kwargs):
                    if path == self.output:
                        output_reads.append(path)
                        if len(output_reads) == 2:
                            if change == 'rewrite':
                                self.source.write_bytes(b'changed during final sweep')
                            elif change == 'replacement':
                                other = self.root / 'replacement.bin'
                                previous = self.source.stat()
                                other.write_bytes(original)
                                os.utime(other, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                                os.replace(other, self.source)
                            else:
                                self.source.unlink()
                    return real_read(path, *args, **kwargs)
                with patch.object(service(), '_read_stable', side_effect=read):
                    with self.assertRaises((ValueError, OSError)):
                        self.register()
                self.assertEqual(self.rows('builds'), [])
                self.assertEqual(len(output_reads), 2)

    def test_input_change_during_output_hash_cannot_pass_check_or_status(self):
        self.init()
        build_id = self.register()['build_id']
        evidence_id = service().check_build(self.project, build_id)['evidence_id']
        original = self.source.read_bytes()
        for action in ('check', 'evaluate'):
            for change in ('rewrite', 'replacement', 'disappearance'):
                with self.subTest(action=action, change=change):
                    self.source.write_bytes(original)
                    real_read = service()._read_stable
                    artifact_reads = []
                    def read(path, *args, **kwargs):
                        if path in (self.source, self.output):
                            artifact_reads.append(path)
                        if path == self.output:
                            if change == 'rewrite':
                                self.source.write_bytes(b'changed during output hash')
                            elif change == 'replacement':
                                other = self.root / 'replacement.bin'
                                previous = self.source.stat()
                                other.write_bytes(original)
                                os.utime(other, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                                os.replace(other, self.source)
                            else:
                                self.source.unlink()
                        return real_read(path, *args, **kwargs)
                    count_before = len(self.rows('evidence'))
                    with patch.object(service(), '_read_stable', side_effect=read):
                        result = (service().check_build(self.project, build_id) if action == 'check'
                                  else service().evaluate_build(self.project, build_id, [evidence_id]))
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['status'], 'BLOCKED')
                    self.assertEqual(artifact_reads, [self.source, self.output])
                    observation = result['observations'][0]
                    self.assertEqual(observation['status'], 'BLOCKED')
                    self.assertIsNone(observation['sha256'])
                    self.assertIsNone(observation['size'])
                    if action == 'check':
                        rows = self.rows('evidence')
                        self.assertEqual(len(rows), count_before + 1)
                        stored, = [json.loads(row[2]) for row in rows if row[0] == result['evidence_id']]
                        self.assertEqual(stored['status'], 'BLOCKED')
                    else:
                        self.assertEqual(len(self.rows('evidence')), count_before)

    def test_metadata_change_during_final_database_hash_aborts_initialization(self):
        metadata = self.project / 'project.json'
        for change in ('rewrite', 'creation', 'replacement', 'disappearance'):
            with self.subTest(change=change):
                # Isolate faults even if an earlier RED subtest published a store.
                if self.store.exists():
                    self.db.unlink()
                    (self.store / 'owner.json').unlink()
                    self.store.rmdir()
                metadata.write_bytes(b'{"name":"old"}')
                evidence = self.project / 'evidence/evidence.json'
                real_read = service()._read_stable
                database_reads = []
                def read(path, *args, **kwargs):
                    if path.name.startswith('.init-'):
                        database_reads.append(path)
                        if len(database_reads) == 2:
                            if change == 'rewrite':
                                metadata.write_bytes(b'{"name":"new value"}')
                            elif change == 'creation':
                                evidence.parent.mkdir(exist_ok=True)
                                evidence.write_bytes(b'[]')
                            elif change == 'replacement':
                                other = self.root / 'replacement.json'
                                previous = metadata.stat()
                                other.write_bytes(metadata.read_bytes())
                                os.utime(other, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                                os.replace(other, metadata)
                            else:
                                metadata.unlink()
                    return real_read(path, *args, **kwargs)
                with patch.object(service(), '_read_stable', side_effect=read):
                    with self.assertRaises((ValueError, OSError)):
                        self.init()
                self.assertFalse(self.store.exists())
                self.assertEqual(len(database_reads), 2)
                if change == 'rewrite':
                    self.assertEqual(metadata.read_bytes(), b'{"name":"new value"}')
                elif change == 'creation':
                    self.assertEqual(evidence.read_bytes(), b'[]')
                elif change == 'disappearance':
                    self.assertFalse(metadata.exists())
                else:
                    self.assertEqual(metadata.read_bytes(), b'{"name":"old"}')
                retry = self.init()
                self.assertTrue(retry['ok'])
                # Each iteration owns this synthetic store and its exact two files.
                self.db.unlink()
                (self.store / 'owner.json').unlink()
                self.store.rmdir()
                evidence.unlink(missing_ok=True)

    def test_lock_initialization_io_failure_releases_owned_lock_and_allows_retry(self):
        self.init()
        for operation in ('write', 'flush'):
            for error in (OSError, KeyboardInterrupt):
                with self.subTest(operation=operation, error=error):
                    (self.store / 'operation.lock').unlink(missing_ok=True)
                    before = self.db.read_bytes()
                    descriptors = []
                    real_fdopen = os.fdopen
                    class FailingStream:
                        def __init__(self, stream):
                            self.stream = stream
                        def __enter__(self):
                            return self
                        def __exit__(self, *args):
                            self.close()
                        def fileno(self):
                            return self.stream.fileno()
                        def write(self, data):
                            if operation == 'write':
                                raise error('injected lock write failure')
                            return self.stream.write(data)
                        def flush(self):
                            if operation == 'flush':
                                raise error('injected lock flush failure')
                            return self.stream.flush()
                        def close(self):
                            self.stream.close()
                    def fdopen(fd, *args, **kwargs):
                        descriptors.append(fd)
                        return FailingStream(real_fdopen(fd, *args, **kwargs))
                    with patch('romancer.history.os.fdopen', side_effect=fdopen):
                        with self.assertRaises(error):
                            self.register()
                    self.assertFalse((self.store / 'operation.lock').exists())
                    self.assertEqual(self.db.read_bytes(), before)
                    with self.assertRaises(OSError):
                        os.fstat(descriptors[0])
                    self.assertTrue(self.register()['ok'])

    def test_lock_fdopen_failure_closes_descriptor_and_cleans_owned_path(self):
        self.init()
        before = self.db.read_bytes()
        descriptors = []
        def fdopen(fd, *args, **kwargs):
            descriptors.append(fd)
            raise OSError('injected fdopen failure')
        with patch('romancer.history.os.fdopen', side_effect=fdopen):
            try:
                with self.assertRaises(OSError):
                    self.register()
                with self.assertRaises(OSError):
                    os.fstat(descriptors[0])
            finally:
                # Keep a failed regression from leaking a raw descriptor on Windows.
                for fd in descriptors:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
        self.assertFalse((self.store / 'operation.lock').exists())
        self.assertEqual(self.db.read_bytes(), before)
        self.assertTrue(self.register()['ok'])

    def test_lock_initialization_failure_preserves_replacement_lock(self):
        self.init()
        before = self.db.read_bytes()
        lock = self.store / 'operation.lock'
        other = self.root / 'another-lock'
        other.write_bytes(b'other operation')
        real_fdopen = os.fdopen
        class ReplacingStream:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()
            def fileno(self):
                return self.stream.fileno()
            def write(self, data):
                self.stream.close()
                os.replace(other, lock)
                raise OSError('lock replaced during initialization')
            def close(self):
                self.stream.close()
        with patch('romancer.history.os.fdopen', side_effect=lambda *args, **kwargs:
                   ReplacingStream(real_fdopen(*args, **kwargs))):
            with self.assertRaises(OSError):
                self.register()
        self.assertEqual(lock.read_bytes(), b'other operation')
        self.assertEqual(self.db.read_bytes(), before)

    def test_collision_after_hashing_is_rejected_before_writable_connection(self):
        self.init()
        before = self.db.read_bytes()
        collision = self.store / 'history.sqlite3-journal'
        real_read = service()._read_stable
        def read(path, *args, **kwargs):
            result = real_read(path, *args, **kwargs)
            if path == self.output and not collision.exists():
                os.link(self.source, collision)
            return result
        with patch.object(service(), '_read_stable', side_effect=read):
            with self.assertRaises(ValueError):
                self.register()
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(collision.read_bytes(), b'original synthetic bytes')

    def test_check_rejects_recorded_artifact_now_aliasing_store(self):
        self.init()
        build_id = self.register()['build_id']
        before = self.db.read_bytes()
        self.output.unlink()
        os.link(self.db, self.output)
        with self.assertRaises(ValueError):
            service().check_build(self.project, build_id)
        self.assertEqual(self.output.read_bytes(), before)

    def test_failed_historical_check_remains_failed_after_artifact_restored(self):
        self.init()
        build_id = self.register()['build_id']
        original = self.output.read_bytes()
        self.output.write_bytes(b'wrong')
        check = service().check_build(self.project, build_id)
        self.output.write_bytes(original)
        result = service().evaluate_build(self.project, build_id, [check['evidence_id']])
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'FAIL')

    def test_unreadable_artifact_is_blocked_measured_evidence(self):
        self.init()
        build_id = self.register()['build_id']
        real_read = service()._read_stable
        def read(path, *args, **kwargs):
            if path == self.output:
                raise PermissionError('cannot read artifact')
            return real_read(path, *args, **kwargs)
        with patch.object(service(), '_read_stable', side_effect=read):
            result = service().check_build(self.project, build_id)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(len(self.rows('evidence')), 1)

    def test_hardlinked_marker_and_replaced_store_marker_are_rejected(self):
        self.init()
        owner = self.store / 'owner.json'
        original = owner.read_bytes()
        alias = self.root / 'marker-alias'
        os.link(owner, alias)
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(alias.read_bytes(), original)
        alias.unlink()
        marker = json.loads(original)
        marker['store_id'] = '0' * 32
        owner.write_text(json.dumps(marker), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.register()

    def test_symlink_project_and_store_roots_are_rejected(self):
        alias = self.root / 'linked-project'
        try:
            alias.symlink_to(self.project, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'directory symlinks unavailable: {exc}')
        with self.assertRaises(ValueError):
            service().init_history(alias)
        self.init()
        real_store = self.root / 'moved-store'
        self.store.rename(real_store)
        self.store.symlink_to(real_store, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.register()

    @unittest.skipUnless(os.name == 'nt', 'Windows path semantics')
    def test_windows_reserved_project_and_artifact_names_are_rejected(self):
        for name in ('project:stream', 'NUL', 'ambiguous.'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                service().init_history(self.root / name)
        self.init()
        for name in ('original.bin:stream', 'NUL', 'ambiguous.'):
            config = copy.deepcopy(self.config)
            config['output'] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.register(config)

    def test_initialization_journal_collision_preserves_external_original(self):
        original = self.source.read_bytes()
        real_mkstemp = tempfile.mkstemp
        collisions = []
        def mkstemp(*args, **kwargs):
            fd, name = real_mkstemp(*args, **kwargs)
            collision = Path(name + '-journal')
            os.link(self.source, collision)
            collisions.append(collision)
            return fd, name
        with patch('romancer.history.tempfile.mkstemp', side_effect=mkstemp):
            with self.assertRaises((ValueError, OSError, sqlite3.Error)):
                self.init()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(collisions[0].read_bytes(), original)
        self.assertFalse(self.db.exists())

    def test_artifact_rewrite_inside_hash_read_is_detected(self):
        self.init()
        real_open = Path.open
        changed = []
        class Reader:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def read(self, size):
                data = self.stream.read(size)
                if data and not changed:
                    changed.append(True)
                    with real_open(self_path, 'ab') as output:
                        output.write(b'!')
                return data
        self_path = self.source
        def open_path(path, mode='r', *args, **kwargs):
            stream = real_open(path, mode, *args, **kwargs)
            return Reader(stream) if path == self.source and mode == 'rb' else stream
        with patch.object(Path, 'open', new=open_path):
            with self.assertRaises(ValueError):
                self.register()
        self.assertEqual(self.rows('builds'), [])

    def test_evidence_insertion_rolls_back_on_failed_commit(self):
        self.init()
        build_id = self.register()['build_id']
        real_connect = sqlite3.connect
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_authorizer(lambda action, arg1, *rest:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and arg1 == 'COMMIT' else sqlite3.SQLITE_OK)
            return connection
        with patch('romancer.history.sqlite3.connect', side_effect=connect):
            with self.assertRaises(sqlite3.Error):
                service().check_build(self.project, build_id)
        self.assertEqual(self.rows('evidence'), [])
        self.assertEqual(len(self.rows('builds')), 1)

    def test_build_identity_matches_independent_canonical_document(self):
        self.init()
        with patch.object(service(), 'ROMANCER_VERSION', 'test-version'):
            build = self.register()
        expected = {'schema_version': 1, 'canonical_version': 1, 'tool_version': 'test-version',
                    'inputs': [{'role': 'original', 'sha256': hashlib.sha256(b'original synthetic bytes').hexdigest(), 'size': 24}],
                    'output': {'sha256': hashlib.sha256(b'translated synthetic bytes').hexdigest(), 'size': 26},
                    'adapter': {'name': 'generic', 'version': '1'},
                    'profile': {'name': 'custom', 'version': '1'}, 'settings': {}}
        raw = json.dumps(expected, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
        self.assertEqual(build['build_id'], hashlib.sha256(raw).hexdigest())

    def test_forged_evidence_status_and_kind_are_rejected_even_with_updated_checksum(self):
        self.init()
        build_id = self.register()['build_id']
        check = service().check_build(self.project, build_id)
        with closing(sqlite3.connect(self.db)) as connection:
            original = json.loads(connection.execute('SELECT record_json FROM evidence').fetchone()[0])
        for change in ('wrong-kind', 'wrong-observed-hash', 'unknown-field'):
            record = copy.deepcopy(original)
            if change == 'wrong-kind':
                record['check_kind'] = 'gameplay'
            elif change == 'wrong-observed-hash':
                record['observations'][0]['sha256'] = '0' * 64
            else:
                record['approved'] = True
            raw = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
            with closing(sqlite3.connect(self.db)) as connection, connection:
                connection.execute('UPDATE evidence SET record_json=?, record_sha256=?',
                                   (raw, hashlib.sha256(raw.encode('utf-8')).hexdigest()))
            with self.subTest(change=change), self.assertRaises(ValueError):
                service().evaluate_build(self.project, build_id, [check['evidence_id']])

    @unittest.skipUnless(os.name == 'nt', 'Windows junction semantics')
    def test_windows_junction_project_root_is_rejected_without_writing_target(self):
        junction = self.root / 'junction'
        response = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(self.project)],
                                  capture_output=True, text=True, timeout=10)
        if response.returncode:
            self.skipTest('junction creation unavailable: ' + response.stderr)
        try:
            with self.assertRaises(ValueError):
                service().init_history(junction)
            self.assertFalse(self.store.exists())
        finally:
            junction.rmdir()


class DisappearingLockTests(unittest.TestCase):
    def test_waiting_lock_disappearing_during_validation_retries(self):
        from unittest.mock import patch
        from romancer import history
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder);history.init_history(project)
            lock=project/history.STORE_NAME/history.LOCK_NAME;lock.write_bytes(b'writer')
            regular=history._regular;removed=False
            def race(path,**kwargs):
                nonlocal removed
                if path==lock and lock.exists() and not removed:
                    removed=True;lock.unlink();raise ValueError('Windows delete-pending lock has zero links')
                return regular(path,**kwargs)
            with patch.object(history,'_regular',side_effect=race):
                with history._locked(project):pass


if __name__ == '__main__':
    unittest.main()
