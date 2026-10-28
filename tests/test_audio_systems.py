import unittest


class AudioSystemTests(unittest.TestCase):
    def test_hardware_profiles_do_not_invent_a_music_driver(self):
        from romancer.audio_systems import audio_system_info
        for system,voices in [('nes',5),('snes',8),('genesis',10),('gb',4),('gbc',4),('sms',4)]:
            value=audio_system_info(system,'0'*64)
            self.assertEqual(value['hardware']['nominal_channels'],voices)
            self.assertEqual(value['driver']['status'],'UNKNOWN');self.assertFalse(value['sequence_edit_supported'])
            self.assertTrue(value['hardware']['references'])
        with self.assertRaises(ValueError):audio_system_info('unknown','0'*64)
