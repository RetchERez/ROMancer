"""Fictional local catalog fixtures; no upstream cheat database is bundled."""
import hashlib,json,tempfile,unittest
from pathlib import Path


class CheatCatalogTests(unittest.TestCase):
    def test_text_preserves_required_groups_and_alternative_revisions(self):
        from romancer.cheat_catalog import parse_catalog
        raw=b'SOURCE-01: Fictional publication\n https://example.invalid/book\n\n[NES] Invented Orbit\n SOURCE: SOURCE-01 | page 7\n AAAAAA + APAAAA / AAAAAAAA | Alleged moon effect\n nonsense | Unparsed claim\nEND OF VERIFIED-PUBLICATION EXTRACT\n'
        rows=parse_catalog(raw)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['alternatives'],[['AAAAAA','APAAAA'],['AAAAAAAA']])
        self.assertEqual(rows[0]['source_url'],'https://example.invalid/book')
        self.assertEqual(rows[0]['source_location'],'page 7')
        self.assertEqual(rows[1]['code_text'],'nonsense')
        self.assertFalse(rows[0]['gameplay_verified'])

    def test_json_jsonl_csv_tsv_aliases_and_strict_input_bounds(self):
        from romancer.cheat_catalog import parse_catalog
        obj={'platform':'NES','game_title':'Invented Orbit','code_text':'AAAAAA','effect_name':'Imported claim','rom_crc':'12345678','source_url':'https://example.invalid/a'}
        for raw in [json.dumps([obj]).encode(),('[\t'+json.dumps(obj)+']').encode(),json.dumps(obj).encode(),(json.dumps(obj)+'\n'+json.dumps(obj)).encode(),b'system,game_title,code_text,effect_name\nNES,Invented Orbit,AAAAAA,Claim\n',b'system\tgame_title\tcode_text\teffect_name\nNES\tInvented Orbit\tAAAAAA\tClaim\n']:
            with self.subTest(raw=raw[:40]):self.assertEqual(parse_catalog(raw)[0]['system_id'],'nes')
        self.assertEqual(parse_catalog(json.dumps(obj).encode())[0]['hashes'],{'crc32':'12345678'})
        for platform,want in [('fc','nes'),('sfc','snes'),('md','genesis'),('gen','genesis'),('gameboycolor','gbc')]:
            self.assertEqual(parse_catalog(json.dumps({**obj,'platform':platform}).encode())[0]['system_id'],want)
        for raw in [b'[{"system":"NES","system":"SNES"}]',b'\xff',b'x'*(16*1024*1024+1),json.dumps([obj]*20001).encode(),json.dumps({**obj,'code_text':'A'*4097}).encode()]:
            with self.assertRaises(ValueError):parse_catalog(raw)

    def setup_project(self,root,*,mapper=0,banks=1):
        from romancer import workbench_projects as p
        image=bytearray(b'NES\x1a'+bytes([banks,0,mapper<<4,0])+bytes(8)+bytes(banks*16384))
        source=root/'Invented Orbit (USA).nes';source.write_bytes(image)
        project=Path(p.create_project(root/'projects','Catalog test')['path']);row=p.register_source(project,source,None)
        return project,p.artifact(project,row['artifact_id']),source

    def import_rows(self,project,root,rows):
        from romancer.workbench_files import import_input
        from romancer.cheat_catalog import import_catalog
        path=root/'fictional.json';path.write_text(json.dumps(rows));incoming=import_input(project,path,path.name,'catalog');return import_catalog(project,incoming['input_id'])

    def test_import_is_owned_fingerprinted_and_inspection_never_modifies_rom(self):
        from romancer.cheat_catalog import inspect_catalog,catalog_info
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,original=self.setup_project(root);before=original.read_bytes();owned=Path(row['path']).read_bytes()
            self.assertEqual(self.import_rows(project,root,[{'system':'nes','game_title':'Invented Orbit','code_text':'AAAAAA','effect_name':'Claimed energy'}]),1)
            info=catalog_info(project);self.assertEqual(info['count'],1);self.assertEqual(len(info['sha256']),64)
            result=inspect_catalog(project,row,Path(row['path']));entry=result['entries'][0]
            self.assertEqual(entry['revision_status'],'UNSPECIFIED');self.assertFalse(result['write_authorized']);self.assertFalse(entry['gameplay_verified'])
            part=entry['alternatives'][0][0];self.assertEqual(part['locations'][0]['offset'],16);self.assertEqual(part['locations'][0]['before_hex'],'00')
            self.assertEqual(original.read_bytes(),before);self.assertEqual(Path(row['path']).read_bytes(),owned)
            Path(row['path']).write_bytes(owned[:-1]+b'X')
            with self.assertRaises(ValueError):inspect_catalog(project,row,Path(row['path']))

    def test_revision_mismatch_is_visible_but_has_no_rom_location_authority(self):
        from romancer.cheat_catalog import inspect_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root)
            self.import_rows(project,root,[{'system':'nes','game_title':'Invented Orbit','code_text':'AAAAAA','sha256':'f'*64}])
            entry=inspect_catalog(project,row,Path(row['path']))['entries'][0]
            self.assertEqual(entry['revision_status'],'MISMATCH');self.assertEqual(entry['alternatives'][0][0]['locations'],[])

    def test_bank_compare_filter_does_not_claim_active_bank_and_ram_is_skipped(self):
        from romancer.cheat_catalog import inspect_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root,mapper=2,banks=4)
            self.import_rows(project,root,[{'system':'nes','game_title':'Invented Orbit','code_text':'AAAAAAAA'},{'system':'gba','game_title':'Invented Orbit','code_text':'AAAA-AAAA'}])
            result=inspect_catalog(project,row,Path(row['path']));self.assertEqual(result['total'],1)
            part=result['entries'][0]['alternatives'][0][0];self.assertEqual(len(part['locations']),4)
            self.assertTrue(all(x['mapping_status']=='BANK_CANDIDATE' for x in part['locations']))
            self.assertFalse(part['active_bank_known'])

    def test_cancelled_import_keeps_existing_complete_catalog(self):
        from romancer.cheat_catalog import import_catalog,catalog_info
        from romancer.workbench_files import import_input
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root);self.import_rows(project,root,[{'system':'nes','game_title':'Invented Orbit','code_text':'AAAAAA'}]);before=catalog_info(project)['sha256']
            path=root/'more.txt';path.write_text('[NES] Invented Orbit\nAAAAAA | Claim\n');incoming=import_input(project,path,path.name,'catalog')
            with self.assertRaises(KeyboardInterrupt):import_catalog(project,incoming['input_id'],cancelled=lambda:True)
            self.assertEqual(catalog_info(project)['sha256'],before)

    def test_static_mapper_candidates_filter_compare_without_choosing_runtime_bank(self):
        from romancer.cheat_catalog import _locations
        from romancer.system_identify import identify_system
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root,mapper=2,banks=4)
            image=bytearray(Path(row['path']).read_bytes());image[16+16384]=0x7b;Path(row['path']).write_bytes(image)
            assessment=identify_system(Path(row['path']))
            places,status,_=_locations('nes',{'address':0x8000,'width':1,'value':5,'compare':0x7b,'endian':'little'},Path(row['path']),assessment,None,lambda:False)
            self.assertEqual(status,'BANK_CANDIDATE');self.assertEqual([p['offset'] for p in places],[16400]);self.assertEqual(places[0]['before_value'],123);self.assertFalse(places[0]['active_bank_known'])
            places,status,_=_locations('genesis',{'address':0xff0000,'width':2,'compare':None,'endian':'big'},Path(row['path']),{},None,lambda:False)
            self.assertEqual((places,status),([], 'NOT_ROM'))

    def test_gameboy_mbc1_fixed_window_is_unresolved_and_switch_banks_remain_candidates(self):
        from romancer.cheat_catalog import _locations
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fictional.gb';path.write_bytes(bytes(4*16384));assessment={'candidates':[{'layout_valid':True,'metadata':{'cartridge_type':1}}]}
            decoded={'address':0x1234,'width':1,'compare':None}
            self.assertEqual(_locations('gb',decoded,path,assessment,None,lambda:False)[1],'UNRESOLVED')
            decoded['address']=0x4567;locations,status,_=_locations('gb',decoded,path,assessment,None,lambda:False)
            self.assertEqual(status,'BANK_CANDIDATE');self.assertEqual([p['offset'] for p in locations],[0x4567,0x8567,0xc567])

    def test_unique_snes_header_mapping_stays_heuristic_and_wram_is_not_a_file_offset(self):
        from romancer.cheat_catalog import _locations
        from romancer.system_identify import identify_system
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'invented.sfc';image=bytearray(1024*1024);header=bytearray(64);header[:21]=b'INVENTED MOON'.ljust(21,b' ');header[21]=0x21;header[23]=10;header[28:32]=bytes.fromhex('ffff0000');image[0xffc0:0x10000]=header;path.write_bytes(image)
            assessment=identify_system(path);places,status,_=_locations('snes',{'address':0xc01234,'width':1,'compare':None},path,assessment,None,lambda:False)
            self.assertEqual(status,'HEURISTIC');self.assertEqual(places[0]['offset'],0x1234)
            self.assertEqual(_locations('snes',{'address':0x7e1234,'width':1,'compare':None},path,assessment,None,lambda:False)[1],'NOT_ROM')

    def test_expanded_catalog_budget_failure_preserves_previous_catalog(self):
        from romancer.cheat_catalog import import_catalog,catalog_info
        from romancer.workbench_files import import_input
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root);self.import_rows(project,root,[{'system':'nes','game_title':'Invented Orbit','code_text':'AAAAAA'}]);before=catalog_info(project)['sha256']
            path=root/'expanded.txt';path.write_text('SOURCE-01: '+'R'*1980+'\n\n[NES] Invented Orbit\nSOURCE: SOURCE-01 | page 1\n'+('AAAAAA | Imported claim\n'*8000));incoming=import_input(project,path,path.name,'catalog')
            with self.assertRaises(ValueError):import_catalog(project,incoming['input_id'])
            self.assertEqual(catalog_info(project)['sha256'],before)

    def test_inspection_bounds_provenance_and_keeps_invalid_codes_visible(self):
        from romancer.cheat_catalog import inspect_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root)
            records=[{'system':'nes','game_title':'Invented Orbit','code_text':'not a code','source_refs':['R'*1500]*8}]
            self.import_rows(project,root,records);entry=inspect_catalog(project,row,Path(row['path']))['entries'][0]
            self.assertEqual(len(entry['source_refs']),4);self.assertTrue(all(len(s)==512 for s in entry['source_refs']));self.assertTrue(entry['source_refs_truncated'])
            self.assertTrue(entry['alternatives'][0][0]['error']);self.assertEqual(entry['alternatives'][0][0]['locations'],[])
            stored=json.loads((project/'catalog/cheats.json').read_text());self.assertEqual(len(stored['rows'][0]['source_refs'][0]),1500)

    def test_exact_hash_can_match_a_different_imported_title_without_turning_label_into_fact(self):
        from romancer.cheat_catalog import inspect_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root)
            self.import_rows(project,root,[{'system':'nes','game_title':'A misleading source title','code_text':'AAAAAA','sha256':row['sha256'],'label':'An unverified power claim'}])
            entry=inspect_catalog(project,row,Path(row['path']))['entries'][0]
            self.assertEqual(entry['revision_status'],'MATCHED');self.assertFalse(entry['gameplay_verified']);self.assertIn('Imported',entry['source_claim'])

    def test_page_byte_budget_retains_rows_and_marks_prose_truncation(self):
        from romancer.cheat_catalog import inspect_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root)
            record={'system':'nes','game_title':'Invented Orbit','code_text':'AAAAAA + AAAAAA','label':'月'*2048,'source_location':'月'*2048,'source_refs':['月'*1500]*8,'source_url':'https://example.invalid/'+'x'*1000}
            self.import_rows(project,root,[record]*20);result=inspect_catalog(project,row,Path(row['path']))
            self.assertEqual(len(result['entries']),20);self.assertLessEqual(len(json.dumps(result,ensure_ascii=True).encode()),200*1024)
            self.assertTrue(result['response_truncated']);self.assertTrue(any(e.get('truncated_fields') for e in result['entries']))
            self.assertTrue(all(e['source_url'] in ('',record['source_url']) for e in result['entries']))

    def test_genesis_odd_word_address_is_not_resolved_as_a_word_read(self):
        from romancer.cheat_catalog import _locations
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fictional.bin';path.write_bytes(bytes(16))
            self.assertEqual(_locations('genesis',{'address':1,'width':2,'compare':None,'alignment':2},path,{},None,lambda:False)[1],'UNRESOLVED')

    def test_genesis_requires_linear_header_and_respects_its_declared_extent(self):
        from romancer.cheat_catalog import _locations
        from romancer.system_identify import identify_system
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'invented.smd';path.write_bytes(bytes(1024));decoded={'address':0,'width':2,'compare':None,'endian':'big'}
            self.assertEqual(_locations('genesis',decoded,path,{},None,lambda:False)[1],'UNRESOLVED')
            image=bytearray(1024);image[0x100:0x104]=b'SEGA';image[0x1a4:0x1a8]=(511).to_bytes(4,'big');path.write_bytes(image);assessment=identify_system(path)
            places,status,_=_locations('genesis',decoded,path,assessment,None,lambda:False);self.assertEqual(status,'HEURISTIC');self.assertEqual(places[0]['offset'],0)
            decoded['address']=512;self.assertEqual(_locations('genesis',decoded,path,assessment,None,lambda:False)[1],'NOT_ROM')

    def test_title_hint_does_not_merge_different_declared_systems(self):
        from romancer import workbench_projects as p
        from romancer.cheat_catalog import inspect_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=bytearray(32768);image[0x100:0x103]=bytes.fromhex('c30001');image[0x134:0x140]=b'INVENTEDMOON';image[0x143]=0x80;image[0x14d]=(-sum(image[0x134:0x14d])-25)&255;source=root/'Invented Orbit.gb';source.write_bytes(image)
            project=Path(p.create_project(root/'projects','Color source')['path']);registered=p.register_source(project,source,None);row=p.artifact(project,registered['artifact_id']);self.assertEqual(row['system_id'],'gbc')
            self.import_rows(project,root,[{'system':'gb','game_title':'Invented Orbit','code_text':'000-00F'}]);self.assertEqual(inspect_catalog(project,row,Path(row['path']))['total'],0)

    def test_mixed_extract_resumes_after_end_and_keeps_device_and_source_path_separate(self):
        from romancer.cheat_catalog import parse_catalog
        raw=b'''SOURCE-01: Fictional publisher
 https://example.invalid/publisher

[NES] Invented Orbit
SOURCE: SOURCE-01 | page 7
AAAAAA + APAAAA / AAAAAAAA | Publication claim
END OF VERIFIED-PUBLICATION EXTRACT
ADDITIONAL COMMUNITY EXCERPTS
These are source claims, not instructions to run.
Source: https://example.invalid/community
[NES] Invented Orbit (Region) (Game Genie)
Source: cht/Fictional/Invented Orbit (Game Genie).cht
AAAAAA | Repeated community claim
[SNES] Invented Ninja (Action Replay)
Source: cht/Fictional/Invented Ninja (Action Replay).cht
7E100001 | Fictional RAM claim
[GAME BOY COLOR] Invented Color (Game Genie)
Source: cht/Fictional/Invented Color.cht
000-00F | Fictional color claim
[SEGA MASTER SYSTEM] Invented Flight (Action Replay)
Source: cht/Fictional/Invented Flight.cht
00D0-00XX | Placeholder modifier
NOTE: X means a placeholder, not a complete code.
This continuation is not an imported code record.
[GENESIS / MEGA DRIVE] Invented Ninja (Action Replay)
Source: cht/Fictional/Invented Ninja MD.cht
FF1000:0001 | Fictional RAM claim
'''
        rows=parse_catalog(raw);self.assertEqual(len(rows),6)
        self.assertEqual(rows[0]['alternatives'],[['AAAAAA','APAAAA'],['AAAAAAAA']]);self.assertEqual(rows[0]['source_url'],'https://example.invalid/publisher')
        self.assertEqual(rows[1]['game_title'],'Invented Orbit (Region)');self.assertEqual(rows[1]['format'],'game-genie')
        self.assertEqual(rows[1]['source_url'],'https://example.invalid/community');self.assertEqual(rows[1]['source_path'],'cht/Fictional/Invented Orbit (Game Genie).cht')
        self.assertEqual([(r['system_id'],r['format']) for r in rows[2:]],[('snes','action-replay'),('gbc','game-genie'),('sms','action-replay'),('genesis','action-replay')])
        self.assertTrue(all(not r['gameplay_verified'] for r in rows))

    def test_legacy_format_aliases_and_conflicting_devices_never_default_to_game_genie(self):
        from romancer.cheat_catalog import parse_catalog
        base={'system':'snes','game_title':'Invented Ninja','code_text':'7E100001'}
        for field in ('code_type','device_or_format'):
            self.assertEqual(parse_catalog(json.dumps({**base,field:'Action Replay'}).encode())[0]['format'],'action-replay')
        self.assertNotEqual(parse_catalog(json.dumps({**base,'format':'Game Genie','code_type':'Action Replay'}).encode())[0]['format'],'game-genie')

    def test_action_replay_is_retained_but_never_decoded_or_mapped_as_game_genie(self):
        from romancer.cheat_catalog import inspect_catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project,row,_=self.setup_project(root)
            self.import_rows(project,root,[{'system':'nes','game_title':'Invented Orbit','code_text':'AAAAAA','device_or_format':'Action Replay'}])
            entry=inspect_catalog(project,row,Path(row['path']))['entries'][0];part=entry['alternatives'][0][0]
            self.assertEqual(entry['format'],'action-replay');self.assertIsNone(part['decoded']);self.assertEqual(part['locations'],[]);self.assertEqual(part['mapping_status'],'UNSUPPORTED_FORMAT')


if __name__=='__main__':unittest.main()
