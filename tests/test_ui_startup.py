from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from romancer.workbench_api import WorkbenchAPI


class UIStartupTests(unittest.TestCase):
    def test_readiness_is_per_launch_and_is_not_runtime_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            api=WorkbenchAPI(Path(directory))
            try:
                one={'launch_id':'a'*32};two={'launch_id':'b'*32}
                self.assertFalse(api.dispatch('system.ui_status',one)['ready'])
                result=api.dispatch('system.ui_ready',one)
                self.assertTrue(result['ok'],result);self.assertEqual(result['scope'],'ui_startup')
                self.assertTrue(api.dispatch('system.ui_status',one)['ready'])
                self.assertFalse(api.dispatch('system.ui_status',two)['ready'])
                for bad in ['', '../outside', 'a'*33, True, {}]:
                    self.assertFalse(api.dispatch('system.ui_ready',{'launch_id':bad})['ok'])
            finally:api.close()

    def test_readiness_records_expire_and_have_a_fixed_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            api=WorkbenchAPI(Path(directory))
            try:
                with patch('romancer.workbench_api.time.monotonic',return_value=10):
                    for i in range(34):self.assertTrue(api.dispatch('system.ui_ready',{'launch_id':f'{i:032x}'})['ok'])
                    self.assertFalse(api.dispatch('system.ui_status',{'launch_id':'0'*32})['ready'])
                    self.assertTrue(api.dispatch('system.ui_status',{'launch_id':f'{33:032x}'})['ready'])
                with patch('romancer.workbench_api.time.monotonic',return_value=131):
                    self.assertFalse(api.dispatch('system.ui_status',{'launch_id':f'{33:032x}'})['ready'])
            finally:api.close()
