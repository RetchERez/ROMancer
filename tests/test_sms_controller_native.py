"""Original SMS controller program, exercised against an explicitly supplied reviewed core."""
import os
from pathlib import Path
import tempfile
import unittest
from romancer.libretro_frontend import LibretroFrontend

def controller_program():
    data=bytearray(32768)
    data[:3]=bytes.fromhex('c30001')
    # Pause NMI increments a counter then returns; no commercial program data.
    data[0x66:0x70]=bytes.fromhex('f53a01c03c3201c0f1ed') # RETN completes below
    data[0x70]=0x45
    code=bytes.fromhex('f331f0dfaf3201c03e04d3bf3e80d3bf3e40d3bf3e81d3bfdbdc3200c018f9')
    data[0x100:0x100+len(code)]=code
    data[0x7ff0:0x7ff8]=b'TMR SEGA';data[0x7fff]=0x4c
    return bytes(data)

@unittest.skipUnless(os.environ.get('ROMANCER_SMS_TEST_CORE'),'Reviewed native SMS core not supplied')
class SMSControllerNativeTests(unittest.TestCase):
    def test_both_buttons_and_pause_reach_the_machine(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rom=root/'input.sms';rom.write_bytes(controller_program())
            host=LibretroFrontend(os.environ['ROMANCER_SMS_TEST_CORE'],save_dir=root/'run',
                core_options={'blastem_system_type':'sms','blastem_io_1':'gamepad2.1','blastem_ram_init':'zero'})
            try:
                host.load_game(rom);host.run_frames(3)
                base=host.memory_region('system_ram');self.assertEqual(base[0]&0x30,0x30)
                host.run_frames(2,['a']);a=host.memory_region('system_ram')
                self.assertEqual(a[0]&0x30,0x20,'A must drive SMS button 1')
                host.run_frames(2,[]);host.run_frames(2,['b']);b=host.memory_region('system_ram')
                self.assertEqual(b[0]&0x30,0x10,'B must drive SMS button 2')
                host.run_frames(2,[]);before=host.memory_region('system_ram')[1]
                host.run_frames(2,['start']);after=host.memory_region('system_ram')[1]
                self.assertEqual(after,(before+1)&255,'Start must trigger the SMS Pause NMI')
                host.run_frames(2,[]);self.assertEqual(host.memory_region('system_ram')[0]&0x30,0x30)
                saved=host.serialize()
                host.run_frames(1,[]);expected=host.last_frame.sha256();ram=host.memory_region('system_ram')
                host.unserialize(saved);host.run_frames(1,[])
                self.assertEqual(host.last_frame.sha256(),expected);self.assertEqual(host.memory_region('system_ram'),ram)

            finally:host.close()
if __name__=='__main__':unittest.main()
