import ctypes
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from romancer.controller_devices import ControllerDescription,ControllerInfo,read_controller_info,checked_choices,validate_devices


class ControllerDeviceTests(unittest.TestCase):
    def test_advertisement_keeps_labels_but_only_selects_supported_classes(self):
        types=(ControllerDescription*3)(ControllerDescription(b'Three-button pad',257),ControllerDescription(b'Six-button pad',513),ControllerDescription(b'Mouse',2))
        ports=(ControllerInfo*2)(ControllerInfo(types,3),ControllerInfo())
        result=read_controller_info(ctypes.addressof(ports));self.assertEqual(result[0]['devices'][1]['name'],'Six-button pad')
        self.assertFalse(result[0]['devices'][2]['selectable']);self.assertEqual(checked_choices(result,{'0':513}),{'0':513})
        with self.assertRaisesRegex(ValueError,'advertise'):checked_choices(result,{'0':769})
        with self.assertRaises(ValueError):validate_devices({'0':2})
        with self.assertRaises(ValueError):validate_devices({'0':True})
        with self.assertRaises(ValueError):validate_devices({'4':1})
        self.assertEqual(checked_choices([],{}),{'0':1})
        from romancer.libretro_frontend import LibretroFrontend
        frontend=LibretroFrontend.__new__(LibretroFrontend);frontend._joypads={0:1<<8}
        self.assertEqual(frontend._input_state(0,513,0,8),1)
        self.assertEqual(frontend._input_state(0,2,0,8),0)

    def test_profile_choice_changes_binding_and_survives_reopen(self):
        from romancer.runtime_profiles import save_profile,load_profile,validate_profile
        from tests.test_runtime_profiles import fake_core
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);core=root/'core';fake_core(core)
            first=save_profile(root,'genesis',str(core),{},None,{})['profile']
            second=save_profile(root,'genesis',str(core),{},None,{},controller_devices={'0':513})['profile']
            self.assertNotEqual(first['identity'],second['identity'])
            self.assertEqual(load_profile(root,'genesis')['profile']['controller_devices'],{'0':513})
            with patch('romancer.bundled_cores.packaged_release',return_value=False):
                self.assertEqual(validate_profile(second)['controller_devices'],{'0':513})
            keys=save_profile(root,'genesis',str(core),{'option':'value'},None,{'a':'v'})['profile']
            self.assertEqual(keys.get('controller_devices'),{'0':513},'Editing keys/options must preserve the same engine subtype.')
            reset=save_profile(root,'genesis',str(core),{},None,{},controller_devices={})['profile']
            self.assertNotIn('controller_devices',reset,'An explicit empty selection resets to the standard joypad.')


if __name__=='__main__':unittest.main()
