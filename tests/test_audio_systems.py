import unittest


class AudioSystemTests(unittest.TestCase):
    def test_hardware_profiles_do_not_invent_a_music_driver(self):
        from romancer.audio_systems import audio_system_info
        for system,voices in [('nes',5),('snes',8),('genesis',10),('gb',4),('gba',6)]:
            value=audio_system_info(system,'0'*64)
            self.assertEqual(value['hardware']['nominal_channels'],voices)
            self.assertEqual(value['driver']['status'],'UNKNOWN');self.assertFalse(value['sequence_edit_supported'])
            self.assertTrue(value['hardware']['references'])
        with self.assertRaises(ValueError):audio_system_info('unknown','0'*64)

    def test_exact_wario_revision_has_documented_m4a_without_claiming_decoder(self):
        from romancer.audio_systems import audio_system_info
        value=audio_system_info('gba','d16c7bf6e62bb84049fff1b387108fbd1e6e2cd38ca994ab5310dd9cbf9ba414')
        self.assertEqual(value['driver']['id'],'m4a-mp2k');self.assertEqual(value['driver']['status'],'DOCUMENTED_EXACT_REVISION')
        self.assertIn('src/m4a.c',value['driver']['reference']);self.assertFalse(value['sequence_edit_supported'])
