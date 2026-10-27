import unittest,hashlib
from romancer.graphics_snapshot import parse_graphics_record,finish_snapshot

class GraphicsSnapshotTests(unittest.TestCase):
    def test_native_rgb_and_video_bytes_are_bounded_and_hash_measured(self):
        state={};self.assertTrue(parse_graphics_record('M\tsmsVideoRam\t4\t01020304','sms',state))
        self.assertTrue(parse_graphics_record('SCREEN\t2\t1\tff000000ff00','sms',state));self.assertTrue(parse_graphics_record('S\tvdp.reg5\tn\t126','sms',state))
        result=finish_snapshot(state,'sms');self.assertEqual(result['memory']['smsVideoRam']['data_sha256'],hashlib.sha256(bytes([1,2,3,4])).hexdigest());self.assertEqual(result['frame']['width'],2);self.assertEqual(result['state']['vdp.reg5'],126);self.assertFalse(result['write_authorized']);self.assertFalse(result['complete_memory_snapshot'])
    def test_bad_domains_lengths_pixels_duplicates_and_external_paths_are_refused(self):
        for line in ('M\tsmsVideoRam\t4\t01','M\tgbaPrgRom\t1\t01','M\tsmsVideoRam\t999999\t00','SCREEN\t0\t1\t00','S\t../path\tn\t1'):
            with self.subTest(line=line),self.assertRaises(ValueError):parse_graphics_record(line,'sms',{})
        state={};parse_graphics_record('M\tsmsVideoRam\t1\t01','sms',state)
        with self.assertRaises(ValueError):parse_graphics_record('M\tsmsVideoRam\t1\t01','sms',state)
    def test_genesis_snapshot_uses_shared_strict_transport_without_inventing_cpu_mappings(self):
        from romancer.genesis_debugger import parse_capture
        cfg={'steps':[{'frames':1,'buttons':[],'port':0}],'probes':[{'kind':'write','start':0xc00000,'end':0xc0001f}],'event_limit':4,'instruction_limit':1000,'timeout':5,'graphics_snapshot':True}
        text='BEGIN\t1\tn\tgenesis\nM\tgenesisVideoRam\t2\t1234\nSCREEN\t1\t1\t123456\nEND\t1\t0\t0\n'
        result=parse_capture(text,'','n',bytes(32768),cfg);self.assertEqual(result['graphics_snapshot']['memory']['genesisVideoRam']['data_hex'],'1234');self.assertFalse(result['graphics_snapshot']['write_authorized']);self.assertEqual(result['events'],[])

    def test_unrequested_snapshot_records_do_not_enter_ordinary_capture(self):
        from romancer.debugger_protocol import parse_capture
        cfg={'steps':[{'frames':1,'buttons':[],'port':0}],'probes':[{'kind':'write','start':0,'end':1}],'event_limit':4,'instruction_limit':1000,'timeout':5}
        text='BEGIN\t1\tn\tsms\nM\tsmsVideoRam\t1\t00\nEND\t1\t0\t0\t1\tframes\n'
        with self.assertRaises(ValueError):parse_capture(text,'n','sms',bytes(32768),cfg)
        result=parse_capture(text,'n','sms',bytes(32768),{**cfg,'graphics_snapshot':True});self.assertIn('graphics_snapshot',result);self.assertEqual(result['graphics_snapshot']['point'],'end_of_capture')

if __name__=='__main__':unittest.main()
