import hashlib
import struct
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from romancer import battle_background
from romancer.battle_background import (
    ART_CAPACITY, HEIGHT, WIDTH, decode_art, decode_map, encode_scene,
)


class BattleBackgroundTests(unittest.TestCase):
    def test_mask_uses_most_significant_bit_for_first_byte(self):
        literal = bytes(range(1, 32))
        data = b'\x01\xab\x80\x00\x00\x00' + literal + b'\xff'
        self.assertEqual(decode_art(data), [b'\xab' + literal])

    def test_rejects_overlapping_masks_and_missing_terminator(self):
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            decode_art(bytes.fromhex('02ab80000000cd80000000ff'))
        with self.assertRaisesRegex(ValueError, 'terminator'):
            decode_art(bytes.fromhex('01abffffffffff')[:-1])

    def test_scene_reuses_mirrored_tiles_and_round_trips_every_pixel(self):
        left = [1, 2, 0, 0, 0, 0, 3, 0]
        line = left + left[::-1] + [0] * (WIDTH - 16)
        pixels = bytes(line + [0] * (WIDTH * HEIGHT - WIDTH))
        art, tilemap, count = encode_scene(pixels)
        self.assertLessEqual(len(art), ART_CAPACITY)
        self.assertEqual(count, 1)
        self.assertEqual(struct.unpack_from('>H', tilemap, 2)[0], 0x781 | 0x0800)
        self.assertEqual(decode_map(tilemap, decode_art(art)), pixels)

    def test_scene_reports_tile_budget_before_any_write(self):
        pixels = bytearray(WIDTH * HEIGHT)
        for index in range(105):
            y, x = divmod(index, WIDTH // 8)
            offset = 8 * (x + y * WIDTH)
            pixels[offset] = 15
            pixels[offset + 1] = index // 16
            pixels[offset + 2] = index % 16
        with self.assertRaisesRegex(ValueError, '104'):
            encode_scene(bytes(pixels))

    def test_rejects_missing_tile_or_unknown_palette_bank(self):
        art = [bytes(32)]
        for entry in (0x782, 0x2781):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                decode_map(struct.pack('>H', entry) + bytes(1278), art)

    def test_blank_cells_use_existing_transparent_tile_zero(self):
        art, tilemap, count = encode_scene(bytes(WIDTH * HEIGHT))
        self.assertEqual(tilemap, bytes(1280))
        self.assertEqual(count, 0)
        self.assertEqual(decode_map(tilemap, decode_art(art)), bytes(WIDTH * HEIGHT))

    def test_fit_reports_capacity_and_matches_the_save_plan_without_writing_one(self):
        from romancer.boot_fixtures import make_boot_fixture
        from romancer.workbench_api import WorkbenchAPI

        with tempfile.TemporaryDirectory() as folder, ExitStack() as cleanup:
            root = Path(folder)
            data = bytearray(make_boot_fixture('genesis')['data']).ljust(battle_background.ROM_SIZE, b'\x00')
            struct.pack_into('>I', data, 0x1A4, len(data) - 1)
            loader = battle_background.LOADER_OFFSET
            record = battle_background.PALETTE_POINTER
            data[loader:loader + len(battle_background.LOADER)] = battle_background.LOADER
            data[record:record + len(battle_background.PALETTE_RECORD)] = battle_background.PALETTE_RECORD
            data[battle_background.ART_OFFSET] = 255
            path = root / 'example.md'
            path.write_bytes(data)
            api = WorkbenchAPI(root / 'work')
            cleanup.callback(api.close)
            project = api.dispatch('project.create', {'name': 'Backdrop testing'})
            project_id = project['project_id']
            source = api.dispatch('source.import', {'project_id': project_id, 'path': str(path), 'system': None})
            params = {'project_id': project_id, 'artifact_id': source['artifact_id'],
                      'source_sha256': hashlib.sha256(data).hexdigest(), 'pixels': '1' + '0' * (WIDTH * HEIGHT - 1)}
            plans = Path(project['path']) / 'plans'
            with patch.object(battle_background, 'ORIGINAL_SHA', params['source_sha256']):
                fit = api.dispatch('backgrounds.fit', params)
                self.assertTrue(fit['fits'])
                self.assertFalse(list(plans.glob('*.json')))
                plan = api.dispatch('backgrounds.plan', params)
                self.assertEqual(fit['ranges'], plan['ranges'])
                self.assertEqual(len(list(plans.glob('*.json'))), 1)
                complex_draft = bytearray(WIDTH * HEIGHT)
                for index in range(105):
                    y, x = divmod(index, WIDTH // 8)
                    offset = 8 * (x + y * WIDTH)
                    complex_draft[offset:offset + 3] = bytes((15, index // 16, index % 16))
                pixels = ''.join(format(color,'x') for color in complex_draft)
                fit = api.dispatch('backgrounds.fit', {**params, 'pixels': pixels})
                self.assertFalse(fit['fits'])
                self.assertIn('104', fit['reason'])
                stale = api.dispatch('backgrounds.fit', {**params, 'source_sha256': '0' * 64})
                self.assertFalse(stale['ok'])
                self.assertEqual(len(list(plans.glob('*.json'))), 1)
