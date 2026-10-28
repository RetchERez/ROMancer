import hashlib,json,tempfile,unittest,zipfile,io,struct,subprocess,os,warnings,copy
from pathlib import Path
from romancer.boot_fixtures import make_boot_fixture

class RomSampleDatabaseTests(unittest.TestCase):
    def modules(self):
        from romancer import rom_sample_db,rom_archive_scan
        return rom_sample_db,rom_archive_scan
    def nested(self,path,raw,name='Example.nes'):
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(name,raw)
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('Example.zip',content.getvalue())
    def test_scan_keeps_measured_facts_and_offsets_but_no_game_payload(self):
        db,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=bytearray(make_boot_fixture('nes')['data'])
            secret=b'PRIVATE_DIALOGUE_MUST_NOT_BE_DISTRIBUTED';raw[0x1000:0x1000+len(secret)]=secret
            from romancer.resource_compression import encode_stream
            encoded=encode_stream(b'CONFIDENTIAL_SPRITE_DATA'*3,'rle');raw[0x1800:0x1800+len(encoded)]=encoded
            archive=root/'input.zip';self.nested(archive,raw)
            result=scan.scan_archives([archive],root/'facts.json',root/'report.json',jobs=1,journal=root/'resume.jsonl')
            self.assertEqual(result['records'],1);self.assertTrue(result['ok'])
            data=db.load_database(root/'facts.json');record=data['records'][0]
            self.assertEqual(record['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(record['system_id'],'nes')
            self.assertEqual(record['size'],len(raw));self.assertTrue(record['coverage']['whole_file_read'])
            self.assertTrue(any(r['kind']=='text' and r['offset']==0x1000 for r in record['discoveries']))
            self.assertTrue(any(r['kind']=='compression' and r['offset']==0x1800 for r in record['discoveries']))
            self.assertFalse(record['coverage']['graphics_truncated'],'Sampling many flat blocks does not truncate the few actual candidates.')
            exported=(root/'facts.json').read_text();self.assertNotIn(secret.decode(),exported);self.assertNotIn('CONFIDENTIAL',exported)
            self.assertNotIn(str(root),exported);self.assertNotIn('raw_hex',exported);self.assertNotIn('base64',exported)
            self.assertEqual(list(root.glob('*.nes')),[],'Temporary commercial inputs must not become release members.')
    def test_duplicates_resume_and_source_match_do_not_claim_canonical_revision_or_semantics(self):
        db,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=make_boot_fixture('gbc')['data'];archive=root/'input.zip';self.nested(archive,raw,'Example.gbc')
            first=scan.scan_archives([archive,archive],root/'facts.json',root/'report.json',jobs=1,journal=root/'resume.jsonl')
            self.assertEqual(first['records'],1);self.assertGreater(first['duplicates'],0)
            second=scan.scan_archives([archive],root/'facts.json',root/'report2.json',jobs=1,journal=root/'resume.jsonl')
            self.assertGreater(second['resumed'],0)
            data=db.load_database(root/'facts.json');matched=db.lookup(hashlib.sha256(raw).hexdigest(),len(raw),database=data)
            self.assertEqual(matched['status'],'RECORDED_SAMPLE');self.assertFalse(matched['write_authorized'])
            self.assertFalse(matched['canonical_revision_verified']);self.assertFalse(matched['gameplay_verified'])
            self.assertEqual(db.lookup('0'*64,len(raw),database=data)['status'],'NOT_RECORDED')
            with self.assertRaises(ValueError):db.lookup(hashlib.sha256(raw).hexdigest(),len(raw)+1,database=data)
    def test_six_systems_only_and_unsafe_members_are_not_admitted(self):
        db,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archives=[]
            for system in ('nes','snes','genesis','gb','gbc','sms'):
                raw=make_boot_fixture(system)['data'];archive=root/(system+'.zip');self.nested(archive,raw,'Sample'+make_boot_fixture(system)['suffix']);archives.append(archive)
            bad=root/'bad.zip'
            with zipfile.ZipFile(bad,'w') as z:
                z.writestr('../escape.nes',make_boot_fixture('nes')['data']);z.writestr('unknown.bin',b'UNKNOWN_GAME_CONTENT')
            archives.append(bad)
            result=scan.scan_archives(archives,root/'facts.json',root/'report.json',jobs=1)
            data=db.load_database(root/'facts.json');self.assertEqual({r['system_id'] for r in data['records']},{'nes','snes','genesis','gb','gbc','sms'})
            self.assertGreaterEqual(result['excluded'],2);self.assertFalse((root.parent/'escape.nes').exists())
            poisoned=json.loads((root/'facts.json').read_text());poisoned['records'][0]['rom_data']='COPYRIGHTED'
            with self.assertRaises(ValueError):db.validate_database(poisoned)
    def test_corrupt_archive_cannot_be_reported_as_a_successful_sample(self):
        _,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);bad=root/'bad.zip';bad.write_bytes(b'not a zip archive')
            result=scan.scan_archives([bad],root/'facts.json',root/'report.json',jobs=1)
            self.assertEqual(result['records'],0);self.assertGreater(result['excluded'],0);self.assertFalse(result['complete'])

    def test_large_factual_catalog_uses_a_separate_bounded_strict_loader(self):
        db,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'sample.zip';self.nested(archive,make_boot_fixture('nes')['data'])
            scan.scan_archives([archive],root/'facts.json',root/'report.json',jobs=1)
            data=json.loads((root/'facts.json').read_text());template=data['records'][0]
            data['records']=[{**template,'sha256':hashlib.sha256(str(i).encode()).hexdigest()} for i in range(1500)]
            path=root/'large.json';path.write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(len(db.load_database(path)['records']),1500)
            path.write_text('{"schema_version":1,"schema_version":2}',encoding='utf-8')
            with self.assertRaises(ValueError):db.load_database(path)
            path.write_bytes(b' '*(db.MAX_DATABASE+1))
            with self.assertRaises(ValueError):db.load_database(path)

    def test_duplicate_member_names_retain_each_distinct_source(self):
        db,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=make_boot_fixture('nes')['data'];other=bytearray(raw);other[0x1000]^=1
            for nested in (False,True):
                content=io.BytesIO()
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning)
                    with zipfile.ZipFile(content,'w') as z:
                        z.writestr('Same.nes',raw);z.writestr('Same.nes',other)
                archive=root/'input.zip'
                if nested:
                    with zipfile.ZipFile(archive,'w') as z:z.writestr('Inner.zip',content.getvalue())
                else:archive.write_bytes(content.getvalue())
                result=scan.scan_archives([archive],root/'facts.json',root/'report.json',jobs=1)
                self.assertTrue(result['complete']);self.assertEqual(result['records'],2)
                self.assertEqual({r['sha256'] for r in db.load_database(root/'facts.json')['records']},{hashlib.sha256(raw).hexdigest(),hashlib.sha256(other).hexdigest()})

    def test_malformed_deflate_members_are_excluded_without_aborting_batch(self):
        _,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('Bad.nes','Bad.zip'):
                content=io.BytesIO()
                with zipfile.ZipFile(content,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(name,make_boot_fixture('nes')['data'])
                raw=bytearray(content.getvalue());offset=30+struct.unpack_from('<H',raw,26)[0]+struct.unpack_from('<H',raw,28)[0];raw[offset]=7
                archive=root/'input.zip';archive.write_bytes(raw)
                result=scan.scan_archives([archive],root/'facts.json',root/'report.json',jobs=1)
                self.assertFalse(result['complete']);self.assertEqual(result['records'],0);self.assertEqual(result['excluded'],1)
                self.assertTrue((root/'report.json').is_file())

    def test_output_filesystem_alias_cannot_overwrite_any_input(self):
        _,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);real=root/'real';real.mkdir();alias=root/'alias'
            if os.name=='nt':
                result=subprocess.run(['cmd','/c','mklink','/J',str(alias),str(real)],capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            else:alias.symlink_to(real,target_is_directory=True)
            try:
                archive=real/'source.zip';self.nested(archive,make_boot_fixture('nes')['data']);before=archive.read_bytes()
                for target in ('output','report','journal'):
                    options={'output':root/'facts.json','report':root/'report.json','journal':root/'journal.jsonl'};options[target]=alias/'source.zip'
                    with self.assertRaises(ValueError):scan.scan_archives([archive],jobs=1,**options)
                    self.assertEqual(archive.read_bytes(),before)
                hard=root/'hard.zip';os.link(archive,hard)
                with self.assertRaises(ValueError):scan.scan_archives([archive],hard,root/'report.json',jobs=1)
                self.assertEqual(archive.read_bytes(),before)
            finally:
                if os.name=='nt':alias.rmdir()
                else:alias.unlink()

    def test_record_rejects_cross_system_and_contradictory_resource_evidence(self):
        db,scan=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'source.zip';self.nested(archive,make_boot_fixture('nes')['data'])
            scan.scan_archives([archive],root/'facts.json',root/'report.json',jobs=1)
            original=db.load_database(root/'facts.json')['records'][0]
            bad=copy.deepcopy(original);bad['system_id']='sms';bad['format']='gb-cartridge'
            with self.assertRaises(ValueError):db.validate_record(bad)
            for kind,format,confidence in [('text','lz10','format-derived'),('graphics','tile8-paired2-msb-v1','candidate'),('graphics','tile8-planar2-msb-v1','validated-encoding')]:
                bad=copy.deepcopy(original);bad['discoveries']=[{'kind':kind,'format':format,'confidence':confidence,'offset':0,'length':16,'decoded_size':None,'decoded_sha256':None}]
                with self.assertRaises(ValueError):db.validate_record(bad)
