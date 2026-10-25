import copy
from contextlib import closing
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from romancer import capture_store as store
from romancer.history import init_history, register_build
from romancer.libretro_frontend import write_rgb_png

requires_pillow = unittest.skipUnless(importlib.util.find_spec('PIL') is not None,
                                     'optional Pillow decoder unavailable')


def entry(text='Gate opens', kind='text', **changes):
    result = dict(kind=kind, text=text, method='manual', author='fixture author',
                  locator=None, region=None, resource=None, supersedes=None)
    return dict(result, **changes)


class CaptureIngestTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.capture_ingest'),
                             'capture ingestion is not implemented')
        self.ingest = importlib.import_module('romancer.capture_ingest')
        self.tmp = tempfile.TemporaryDirectory(prefix='capture ingest ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        store.init_capture_store(self.root)
        self.image = self.root / 'historical.png'
        self.rgb = bytes([255, 0, 0, 0, 255, 0])
        write_rgb_png(self.image, 2, 1, self.rgb)
        self.manifest = dict(build_id=None, declared_context=dict(captured_utc=None,
                             core_sha256=None, game_sha256=None, run_mode='cold_boot',
                             state_derived=False, source_note=None), annotations=[])

    def import_one(self, **kwargs):
        return self.ingest.import_capture(self.root, self.image, self.manifest, self.root, **kwargs)['capture_id']

    @requires_pillow
    def test_png_import_preserves_original_and_measures_rgb_not_semantics(self):
        identifier = self.import_one()
        result = store.get_capture(self.root, identifier)
        self.assertEqual(result['png_bytes'], self.image.read_bytes())
        self.assertEqual(result['record']['image']['rgb_sha256'], hashlib.sha256(self.rgb).hexdigest())
        self.assertEqual(result['record']['origin'], 'imported_image')
        self.assertIsNone(result['record']['run'])
        self.assertFalse(result['record']['natural_progress_verified'])
        self.assertEqual(result['record']['import_source']['manifest_kind'], 'canonical_api_input')
        self.assertIsNone(result['record']['import_source']['manifest_path_hint'])

    @requires_pillow
    def test_original_manifest_bytes_are_preserved_not_reserialized(self):
        hashes = []
        for index, raw in enumerate([json.dumps(self.manifest).encode(),
                                     json.dumps(self.manifest, indent=3, sort_keys=True).encode()]):
            source = self.root / f'manifest {index}.json'
            source.write_bytes(raw)
            identifier = self.import_one(manifest_source=source)
            result = store.get_capture(self.root, identifier)
            observed = result['record']['import_source']
            self.assertEqual(observed['manifest_kind'], 'original_file')
            self.assertEqual(observed['manifest_path_hint'], str(source.resolve()))
            self.assertEqual(observed['manifest_sha256'], hashlib.sha256(raw).hexdigest())
            hashes.append(observed['manifest_sha256'])
        self.assertNotEqual(*hashes)

    def test_different_parsed_manifest_refused_atomically(self):
        source = self.root / 'manifest.json'
        other = copy.deepcopy(self.manifest)
        other['declared_context']['source_note'] = 'different'
        source.write_text(json.dumps(other))
        with self.assertRaises(ValueError):
            self.import_one(manifest_source=source)
        with closing(sqlite3.connect(self.root / store.STORE_NAME / store.DB_NAME)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM captures').fetchone()[0], 0)

    @requires_pillow
    def test_export_protects_deleted_manifest_without_annotations(self):
        source = self.root / 'original manifest.json'
        source.write_text(json.dumps(self.manifest))
        identifier = self.import_one(manifest_source=source)
        self.assertEqual(store.get_capture(self.root, identifier)['annotations'], [])
        source.unlink()
        with self.assertRaises(ValueError):
            store.export_capture(self.root, identifier, source)
        self.assertFalse(source.exists())
        destination = self.root / 'separate export.png'
        store.export_capture(self.root, identifier, destination)
        self.assertEqual(destination.read_bytes(), self.image.read_bytes())

    def test_manifest_binding_does_not_equate_json_boolean_and_number(self):
        source = self.root / 'wrong typed manifest.json'
        other = copy.deepcopy(self.manifest)
        other['declared_context']['state_derived'] = 0
        source.write_text(json.dumps(other))
        with self.assertRaises(ValueError):
            self.import_one(manifest_source=source)

    def test_missing_pillow_is_explicit_not_hash_fallback(self):
        with patch.dict('sys.modules', {'PIL': None, 'PIL.Image': None}):
            with self.assertRaisesRegex(ValueError, 'Pillow'):
                self.import_one()

    @requires_pillow
    def test_invalid_images_and_actual_image_budget_fail(self):
        for raw in (b'not a PNG', self.image.read_bytes()[:40]):
            self.image.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.import_one()
        write_rgb_png(self.image, 2, 1, self.rgb)
        with patch.object(store, 'MAX_PNG', self.image.stat().st_size-1), self.assertRaises(ValueError):
            self.import_one()

    @requires_pillow
    def test_png_chunk_framing_and_crc_reject_without_publication(self):
        valid = self.image.read_bytes()
        self.assertEqual(valid[-12:-4], b'\0\0\0\0IEND')
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        ancillary = chunk(b'tEXt', b'Comment\0synthetic fixture')
        cases = {
            'truncated_iend_crc': valid[:-4],
            'zero_iend_crc': valid[:-4] + b'\0'*4,
            'missing_iend': valid[:-12],
            'trailing_bytes': valid + b'junk',
            'nonempty_iend': valid[:-12] + chunk(b'IEND', b'x'),
            'oversized_chunk': valid[:-12] + struct.pack('>I', 0x7fffffff) + b'tEXt' + valid[-12:],
            'corrupt_ancillary_crc': valid[:-12] + ancillary[:-4] + b'\0'*4 + valid[-12:],
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                project = self.root / name
                project.mkdir()
                store.init_capture_store(project)
                self.image.write_bytes(raw)
                with self.assertRaises(ValueError):
                    self.ingest.import_capture(project, self.image, self.manifest, self.root)
                with closing(sqlite3.connect(project / store.STORE_NAME / store.DB_NAME)) as connection:
                    self.assertEqual(connection.execute('SELECT count(*) FROM captures').fetchone()[0], 0)
                    self.assertEqual(connection.execute('SELECT count(*) FROM blobs').fetchone()[0], 0)
        for index, raw in enumerate((valid, valid[:-12] + ancillary + valid[-12:])):
            self.image.write_bytes(raw)
            identifier = self.import_one()
            stored = store.get_capture(self.root, identifier)
            self.assertEqual(stored['png_bytes'], raw)
            self.assertEqual(stored['record']['image']['rgb_sha256'], hashlib.sha256(self.rgb).hexdigest())
            destination = self.root / f'valid export {index}.png'
            store.export_capture(self.root, identifier, destination)
            self.assertEqual(destination.read_bytes(), raw)

    @requires_pillow
    def test_image_pixel_budget_and_animation_are_rejected(self):
        from PIL import Image
        with patch.object(store, 'MAX_RGB', 5), self.assertRaises(ValueError):
            self.import_one()
        with Image.new('RGB', (2, 1), 'red') as first, Image.new('RGB', (2, 1), 'blue') as second:
            first.save(self.image, format='PNG', save_all=True, append_images=[second], duration=10)
        with self.assertRaises(ValueError):
            self.import_one()

    def test_import_never_accepts_forged_authority(self):
        for key, value in [('origin', 'native_worker'), ('status', 'PASS'), ('verified', True)]:
            manifest = dict(self.manifest, **{key: value})
            with self.assertRaises(ValueError):
                self.ingest.import_capture(self.root, self.image, manifest, self.root)

    def test_canonical_api_and_file_manifest_use_same_byte_limit(self):
        source = self.root / 'too large.json'
        source.write_bytes(b' ' * (store.MAX_SOURCE+1))
        with self.assertRaises(ValueError):
            self.import_one(manifest_source=source)
        self.manifest['annotations'] = [entry('x'*4096) for _ in range(300)]
        with self.assertRaises(ValueError):
            self.import_one()

    def test_strict_json_duplicate_nonfinite_and_depth(self):
        source = self.root / 'bad.json'
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'['*34+b'0'+b']'*34]:
            source.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.import_one(manifest_source=source)

    @requires_pillow
    def test_annotations_keep_source_and_explicit_ocr_origin(self):
        identifier = self.import_one()
        source = self.root / 'external OCR.txt'
        source.write_bytes(b'external supplied words')
        result = self.ingest.add_annotations(self.root, identifier,
                    [entry('Supplied OCR', method='imported_ocr', locator='ExternalEngine report 1')], source)
        stored = store.get_capture(self.root, identifier)['annotations'][0]
        self.assertEqual(stored['annotation_id'], result['annotation_ids'][0])
        self.assertEqual(stored['origin'], 'imported_annotation')
        self.assertEqual(stored['source']['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(stored['entry']['method'], 'imported_ocr')
        source.unlink()
        self.assertEqual(store.get_capture(self.root, identifier)['annotations'][0], stored)

    @requires_pillow
    def test_invalid_annotations_leave_batch_unwritten(self):
        identifier = self.import_one()
        cases = [[], [entry(method='imported_ocr', locator='OCR')], [entry(region=[0, 0, 3, 1])],
                 [entry(region=[False, 0, 1, 1])], [entry('x'*4097)], [entry()]*65,
                 [entry(), entry(method='guessed')], [entry(kind='speaker', author='')]]
        for entries in cases:
            with self.subTest(entries=str(entries)[:80]), self.assertRaises(ValueError):
                self.ingest.add_annotations(self.root, identifier, entries)
        self.assertEqual(store.get_capture(self.root, identifier)['annotations'], [])

    @requires_pillow
    def test_corrections_preserve_original_and_prevent_competing_successors(self):
        identifier = self.import_one()
        first = self.ingest.add_annotations(self.root, identifier, [entry('closed')])['annotation_ids'][0]
        self.ingest.add_annotations(self.root, identifier, [entry('opened', supersedes=first)])
        with self.assertRaises(ValueError):
            self.ingest.add_annotations(self.root, identifier, [entry('other', supersedes=first)])
        self.assertEqual(len(store.get_capture(self.root, identifier)['annotations']), 2)
        other = self.import_one()
        with self.assertRaises(ValueError):
            self.ingest.add_annotations(self.root, other, [entry('cross-capture', supersedes=first)])

    @requires_pillow
    def test_resource_requires_exact_build_artifact_and_range(self):
        init_history(self.root)
        game = self.root / 'game.bin'
        game.write_bytes(b'ABCD')
        config = dict(inputs=[dict(role='original', path=str(game))], output=str(game),
                      adapter=dict(name='generic', version='1'), profile=dict(name='test', version='1'), settings={})
        build = register_build(self.root, config, self.root)
        self.manifest['build_id'] = build['build_id']
        identifier = self.import_one()
        resource = dict(build_id=build['build_id'], artifact_role='output',
                        artifact_sha256=hashlib.sha256(b'ABCD').hexdigest(), resource_id='dialogue', offset=1, length=2)
        self.ingest.add_annotations(self.root, identifier, [entry(kind='resource', resource=resource)])
        for bad in [dict(resource, offset=3), dict(resource, artifact_sha256='0'*64), dict(resource, build_id='0'*64)]:
            with self.assertRaises(ValueError):
                self.ingest.add_annotations(self.root, identifier, [entry(kind='resource', resource=bad)])

    @requires_pillow
    def test_missing_annotation_source_and_export_alias(self):
        identifier = self.import_one()
        with self.assertRaises(OSError):
            self.ingest.add_annotations(self.root, identifier, [entry()], self.root / 'missing')
        source = self.root / 'notes.txt'
        source.write_bytes(b'notes')
        self.ingest.add_annotations(self.root, identifier, [entry()], source)
        source.unlink()
        with self.assertRaises(ValueError):
            store.export_capture(self.root, identifier, source)

    def test_actual_read_bound_and_source_change_detection(self):
        source = self.root / 'bounded.txt'
        source.write_bytes(b'x'*80)
        with self.assertRaises(ValueError):
            store._read_file(source, 79)
        self.assertEqual(store._read_file(source, 80), b'x'*80)

    def test_actual_growth_and_same_length_mutation_are_rejected(self):
        source = self.root / 'changing source.txt'
        original_open = Path.open
        for replacement in (b'x'*90, b'y'*80):
            source.write_bytes(b'x'*80)
            requests = []
            class Probe:
                def __init__(self, stream):
                    self.stream = stream
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    self.stream.close()
                def fileno(self):
                    return self.stream.fileno()
                def read(self, size):
                    requests.append(size)
                    chunk = self.stream.read(size)
                    if len(requests) == 1:
                        with original_open(source, 'wb') as writer:
                            writer.write(replacement)
                    return chunk
            def open_probe(path, *args, **kwargs):
                stream = original_open(path, *args, **kwargs)
                return Probe(stream) if path == source and args == ('rb',) else stream
            with patch.object(Path, 'open', open_probe), self.assertRaises(ValueError):
                store._read_file(source, 80)
            self.assertTrue(requests)
            self.assertLessEqual(max(requests), 81)

    @requires_pillow
    def test_corrupt_annotation_source_is_not_retrieved_as_verified(self):
        identifier = self.import_one()
        source = self.root / 'source.txt'
        source.write_bytes(b'evidence')
        added = self.ingest.add_annotations(self.root, identifier, [entry()], source)
        with closing(sqlite3.connect(self.root / store.STORE_NAME / store.DB_NAME)) as connection, connection:
            connection.execute('UPDATE blobs SET content=? WHERE sha256=?', (b'changed!', hashlib.sha256(b'evidence').hexdigest()))
        with self.assertRaises(ValueError):
            store.get_capture(self.root, identifier)

    @unittest.skipUnless(os.name == 'nt', 'Windows drive-relative path syntax')
    @requires_pillow
    def test_import_rejects_drive_relative_before_base_join(self):
        with self.assertRaises(ValueError):
            self.ingest.import_capture(self.root, self.root.drive+'historical.png', self.manifest, self.root)


if __name__ == '__main__':
    unittest.main()
