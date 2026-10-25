import csv
import io
from pathlib import Path
import tempfile
import unittest
from tests.script_fixtures import fixed_fixture
from romancer import workbench_projects as p
from romancer.workbench_files import import_input


class TranslationSheetTests(unittest.TestCase):
    def test_csv_tsv_roundtrip_formula_escaping_and_exact_translated_build(self):
        from romancer.translation_sheets import export_sheet,preview_sheet,escape_cell,unescape_cell
        from romancer.workbench_api import WorkbenchAPI
        for literal in ('=SUM(1,2)','+3','-5','@id',"'hello",'\tvalue','normal','こんにちは'):
            self.assertEqual(unescape_cell(escape_cell(literal)),literal)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw,schema=fixed_fixture();raw=bytearray(raw+bytes(1024-len(raw)));raw[0x100:0x110]=b'SEGA MEGA DRIVE ';raw[0x1a4:0x1a8]=(1023).to_bytes(4,'big');raw=bytes(raw);schema['artifact']['size']=len(raw);schema['profile']['accepted_sha256']=[__import__('hashlib').sha256(raw).hexdigest()];source=root/'text.bin';source.write_bytes(raw);api=WorkbenchAPI(root/'workspace')
            try:
                project=Path(p.create_project(api.projects,'Sheets')['path']);row=p.register_source(project,source,None)
                for fmt,separator in (('csv',','),('tsv','\t')):
                    exported=export_sheet(project,row['artifact_id'],schema,fmt)
                    records=list(csv.DictReader(io.StringIO(exported),delimiter=separator));self.assertEqual(records[0]['record_id'],'a')
                    records[0]['translation']='BAA'
                    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=list(records[0]),delimiter=separator);writer.writeheader();writer.writerows(records)
                    sheet=root/('translation.'+fmt);sheet.write_text(output.getvalue(),encoding='utf-8',newline='')
                    inp=import_input(project,sheet,sheet.name,'translation');preview=preview_sheet(project,row['artifact_id'],schema,inp['input_id'],fmt)
                    self.assertTrue(preview['valid'],preview);self.assertEqual(preview['changed_segments'],1)
                    plan=api.dispatch('script.plan',{'project_id':project.name,'artifact_id':row['artifact_id'],'schema':schema,'edits':preview['edits']});self.assertTrue(plan['ok'],plan)
                    built=api.dispatch('structured.apply',{'project_id':project.name,'plan_id':plan['workbench_plan_id']});self.assertTrue(built['ok'],built)
                    expected=bytearray(raw);expected[8:20]=b'BAA\xf0\x03B\x00'+b'\xff'*5
                    self.assertEqual(Path(built['path']).read_bytes(),bytes(expected));self.assertEqual(source.read_bytes(),raw)
            finally:api.close()

    def test_sheet_reports_overflow_encoding_and_refuses_stale_or_protected_rows(self):
        from romancer.translation_sheets import export_sheet,preview_sheet
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw,schema=fixed_fixture();source=root/'text.bin';source.write_bytes(raw);project=Path(p.create_project(root/'projects','Sheets')['path']);row=p.register_source(project,source,None)
            records=list(csv.DictReader(io.StringIO(export_sheet(project,row['artifact_id'],schema,'csv'))))
            def check(rows):
                output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=list(records[0]));writer.writeheader();writer.writerows(rows)
                path=root/'sheet.csv';path.write_text(output.getvalue(),encoding='utf-8',newline='');inp=import_input(project,path,path.name,'translation')
                return preview_sheet(project,row['artifact_id'],schema,inp['input_id'],'csv')
            records[0]['translation']='A'*30;records[1]['translation']='🙂'
            result=check(records);self.assertFalse(result['valid']);self.assertIn('CAPACITY',[r['code'] for r in result['issues']]);self.assertIn('UNENCODABLE_TEXT',[r['code'] for r in result['issues']]);self.assertEqual(result['edits'],None)
            for mutate in (lambda r:r.append(dict(r[0])),lambda r:r.pop(),lambda r:r[0].update(source_sha256='0'*64),lambda r:r[0].update(controls='changed'),lambda r:r[0].update(original='Changed')):
                rows=[dict(r) for r in records];mutate(rows)
                with self.assertRaises(ValueError):check(rows)
