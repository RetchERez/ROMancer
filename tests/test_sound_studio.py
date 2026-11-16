import base64,copy,hashlib,io,struct,unittest,wave


class SoundCodecTests(unittest.TestCase):
    def test_pcm_signed_unsigned_and_byte_order_vectors(self):
        from romancer.sound_studio import decode_sample,encode_sample
        for codec,raw,values in [('pcm-u8',b'\x00\x80\xff',[-32768,0,32512]),('pcm-s8',b'\x80\x00\x7f',[-32768,0,32512]),('pcm-s16le',b'\x00\x80\x34\x12',[-32768,4660]),('pcm-s16be',b'\x80\x00\x12\x34',[-32768,4660])]:
            with self.subTest(codec=codec):self.assertEqual(decode_sample(raw,codec),values);self.assertEqual(encode_sample(values,codec),raw)

    def test_game_boy_wave_is_high_nibble_first_with_32_samples(self):
        from romancer.sound_studio import decode_sample,encode_sample
        raw=b'\x0f\x87'*8;values=decode_sample(raw,'gb-wave4')
        self.assertEqual(values[:4],[-32768,32767,2184,-2185]);self.assertEqual(len(values),32);self.assertEqual(encode_sample(values,'gb-wave4'),raw)
        with self.assertRaises(ValueError):decode_sample(b'\x01','gb-wave4')

    def test_nes_dpcm_lsb_order_initial_level_and_saturation(self):
        from romancer.sound_studio import decode_sample,encode_sample
        values=[1024,0,1024,0,-1024,-2048,-3072,-2048]
        self.assertEqual(decode_sample(b'\x85','nes-dpcm',64),values)
        self.assertEqual(encode_sample(values,'nes-dpcm',64),b'\x85')
        self.assertEqual(decode_sample(b'\xff','nes-dpcm',126),[31744]*8)

    def test_brr_filter_zero_and_predictor_one_vectors(self):
        from romancer.sound_studio import decode_sample,encode_sample
        first=bytes([0x10]+[0x44]*8);second=bytes([0x15]+[0]*8)
        self.assertEqual(decode_sample(bytes([0x11,0x17,0x8f]+[0]*6),'snes-brr')[:4],[2,14,-16,-2])
        result=decode_sample(first+second,'snes-brr');self.assertEqual(result[:16],[8]*16);self.assertEqual(result[16:20],[6,4,2,0])
        for filter_id in (2,3):self.assertEqual(decode_sample(first+bytes([0x11|filter_id<<2]+[0]*8),'snes-brr')[16:20],[6,2,-4,-10])
        encoded=encode_sample([2048,-4096]*8,'snes-brr');self.assertEqual(len(encoded),9);self.assertEqual(decode_sample(encoded,'snes-brr'),[2048,-4096]*8)
        with self.assertRaises(ValueError):decode_sample(bytes([0xD1]+[0]*8),'snes-brr')
        with self.assertRaises(ValueError):decode_sample(bytes([0x15]+[0]*8),'snes-brr')

    def test_wav_roundtrip_and_resampling_capacity_refusal(self):
        from romancer.sound_studio import wav_bytes,read_wav
        data=wav_bytes([-32768,0,32767,0],8000)
        with wave.open(io.BytesIO(data)) as w:self.assertEqual((w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getnframes()),(1,2,8000,4))
        self.assertEqual(read_wav(data,8000,4),[-32768,0,32767,0])
        with self.assertRaisesRegex(ValueError,'capacity'):read_wav(data,16000,4)
        with self.assertRaises(ValueError):read_wav(b'not wave',8000,4)

    def test_wav_import_budget_counts_frames_for_mono_and_stereo(self):
        from romancer.sound_codecs import read_wav
        for channels in (1,2):
            for frames in (20000,40000,65536):
                for width in (1,2):
                    out=io.BytesIO()
                    with wave.open(out,'wb') as w:
                        w.setnchannels(channels);w.setsampwidth(width);w.setframerate(8000)
                        w.writeframes((bytes([132]) if width==1 else struct.pack('<h',1024))*channels*frames)
                    with self.subTest(channels=channels,frames=frames,width=width):
                        values=read_wav(out.getvalue(),8000,frames)
                        self.assertEqual(len(values),frames);self.assertEqual(set(values),{1024})


class SoundResourceTests(unittest.TestCase):
    def fixture(self):
        from romancer.studio_examples import make_studio_example
        f=make_studio_example();return f['raw'],f['sound'],hashlib.sha256(f['raw']).hexdigest()

    def test_original_song_refuses_sample_writes_into_its_header_or_vectors(self):
        from romancer.sound_studio import inspect_sound,plan_sound
        from romancer.studio_runtime import make_collision_studio_rom,runtime_definitions
        from romancer.script_schema import canonical_bytes
        mossy=make_collision_studio_rom();raw=mossy['data'];sha=hashlib.sha256(raw).hexdigest()
        fixtures=[self.fixture(),(raw,runtime_definitions(mossy,sha)['sound'],sha)]
        for raw,definition,sha in fixtures:
            for offset,length in [(0,16),(15,2),(16393,2),(16394,6),(16399,1)]:
                with self.subTest(driver=definition['songs'][0]['driver'],offset=offset,length=length):
                    d=copy.deepcopy(definition)
                    d['samples'].append({'id':'unsafe-sample','name':'Protected region','offset':offset,'length':length,'codec':'pcm-u8','sample_rate':8000,'initial_level':64})
                    document_id=hashlib.sha256(canonical_bytes(d,max_bytes=128*1024)).hexdigest()
                    with self.assertRaisesRegex(ValueError,'overlap'):
                        inspect_sound(raw,d,sha)
                    with self.assertRaisesRegex(ValueError,'overlap'):
                        plan_sound(raw,d,document_id,[{'kind':'sample','sample_id':'unsafe-sample','operation':'silence','value':0,'wav_base64':None}],sha)

    def test_original_song_keeps_sample_ranges_adjacent_to_vectors_available(self):
        from romancer.sound_studio import inspect_sound
        from romancer.studio_runtime import make_collision_studio_rom,runtime_definitions
        mossy=make_collision_studio_rom();raw=mossy['data'];sha=hashlib.sha256(raw).hexdigest()
        fixtures=[self.fixture(),(raw,runtime_definitions(mossy,sha)['sound'],sha)]
        for raw,definition,sha in fixtures:
            for offset,length in [(16390,4),(16400,1)]:
                with self.subTest(driver=definition['songs'][0]['driver'],offset=offset):
                    d=copy.deepcopy(definition)
                    d['samples'].append({'id':'adjacent-sample','name':'Adjacent region','offset':offset,'length':length,'codec':'pcm-u8','sample_rate':8000,'initial_level':64})
                    self.assertTrue(inspect_sound(raw,d,sha)['ok'])

    def test_practice_song_decodes_and_note_edit_changes_only_expected_byte(self):
        from romancer.sound_studio import inspect_sound,plan_sound
        raw,d,sha=self.fixture();doc=inspect_sound(raw,d,sha);self.assertEqual(doc['songs'][0]['events'][0]['note'],60)
        result=plan_sound(raw,d,doc['document_id'],[{'kind':'note','song_id':'hillside','index':0,'field':'note','value':64}],sha)
        self.assertEqual(result['edits'],[{'offset':0x3810,'before':'3c','after':'40'}])
        self.assertEqual(doc['samples'][0]['sample_count'],4096)

    def test_malformed_definitions_and_changes_are_actionable_refusals(self):
        from romancer.sound_studio import inspect_sound,plan_sound
        raw,d,sha=self.fixture();doc=inspect_sound(raw,d,sha)
        for malformed in (None,[],42):
            with self.subTest(definition=malformed),self.assertRaisesRegex(ValueError,'definition'):
                inspect_sound(raw,malformed,sha)
        with self.assertRaisesRegex(ValueError,'change'):
            plan_sound(raw,d,doc['document_id'],[None],sha)

    def test_sample_gain_plan_is_bounded_and_wav_replacement_is_same_allocation(self):
        from romancer.sound_studio import inspect_sound,plan_sound,wav_bytes
        raw,d,sha=self.fixture();d['samples']=[{'id':'pcm','name':'PCM','offset':0x1300,'length':4,'codec':'pcm-s16le','sample_rate':8000,'initial_level':64}]
        raw=bytearray(raw);raw[0x1300:0x1304]=struct.pack('<hh',10000,-10000);raw=bytes(raw);sha=hashlib.sha256(raw).hexdigest();d['source_sha256']=sha;doc=inspect_sound(raw,d,sha)
        c={'kind':'sample','sample_id':'pcm','operation':'gain','value':50,'wav_base64':None};result=plan_sound(raw,d,doc['document_id'],[c],sha)
        self.assertEqual(result['edits'],[{'offset':0x1300,'before':'1027f0d8','after':'881378ec'}])
        c.update(operation='replace_wav',wav_base64=base64.b64encode(wav_bytes([4000],8000)).decode());result=plan_sound(raw,d,doc['document_id'],[c],sha)
        self.assertEqual(result['edits'][0]['after'],'a00f0000')

    def test_unknown_codec_driver_overlap_and_stale_identity_are_refused(self):
        from romancer.sound_studio import inspect_sound,plan_sound
        raw,d,sha=self.fixture()
        for mutate in [lambda d:d['samples'][0].update(codec='unknown'),lambda d:d['songs'][0].update(driver='unknown'),lambda d:d['samples'][0].update(offset=d['songs'][0]['offset'])]:
            bad=copy.deepcopy(d);mutate(bad)
            with self.subTest(definition=bad),self.assertRaises(ValueError):inspect_sound(raw,bad,sha)
        with self.assertRaisesRegex(ValueError,'source'):inspect_sound(raw,d,'0'*64)
        with self.assertRaisesRegex(ValueError,'document|review'):plan_sound(raw,d,'stale',[],sha)
        altered=bytearray(raw);altered[16]^=1;sha2=hashlib.sha256(altered).hexdigest();d['source_sha256']=sha2
        with self.assertRaisesRegex(ValueError,'driver'):inspect_sound(bytes(altered),d,sha2)
