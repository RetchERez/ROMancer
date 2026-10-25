import unittest


class RegistryTests(unittest.TestCase):
    def test_five_packs_separate_format_support_from_runtime(self):
        from romancer.system_registry import system_inventory, get_system
        result=system_inventory()
        self.assertEqual(result['schema_version'],1)
        self.assertEqual(result['registry_version'],'1')
        self.assertFalse(result['write_authorized']);self.assertFalse(result['runtime_verified'])
        self.assertEqual({s['id'] for s in result['systems']},{'nes','snes','genesis','gb','gba'})
        for pack in result['systems']:
            self.assertEqual(pack['version'],'1');self.assertTrue(pack['label']);self.assertTrue(pack['formats'])
            for capability in pack['capabilities'].values():
                self.assertIn(capability['status'],{'supported','experimental','unsupported','unavailable'})
                self.assertTrue(capability['reason']);self.assertTrue(capability['implementation'])
            self.assertEqual(pack['capabilities']['runtime_control']['status'],'unavailable')
        result['systems'][0]['capabilities']['runtime_control']['status']='supported'
        self.assertEqual(get_system('nes')['capabilities']['runtime_control']['status'],'unavailable')
        for invalid in ('NES','unknown',None,True,{},'nes\n'):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):get_system(invalid)


if __name__=='__main__':unittest.main()
