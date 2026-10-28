"""Literal Game Boy storage and mapping vectors, independent of the writer."""
import hashlib
from pathlib import Path
import tempfile
import unittest


def cartridge(size=32768, color=0):
    data=bytearray(size);data[0x100:0x104]=bytes.fromhex('c3500100')
    data[0x134:0x143]=b'ROMANCER TEST'.ljust(15,b'\0');data[0x143]=color
    data[0x148]=(size//32768).bit_length()-1
    data[0x14d]=(-sum(data[0x134:0x14d])-25)&255
    data[0x14e:0x150]=(sum(data)&65535).to_bytes(2,'big')
    return bytes(data)


class GameBoyTests(unittest.TestCase):
    def test_five_workshops_have_current_source_bound_graphics(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                for system in ('nes','snes','genesis','gb','gbc','sms'):
                    demo=api.dispatch('project.demo_system',{'system_id':system})
                    self.assertTrue(demo['ok'],demo);row=demo['sources'][0]
                    self.assertEqual(row['system_id'],system)
                    model=api.dispatch('assets.inspect',{'project_id':demo['project_id'],'artifact_id':row['artifact_id'],'schema':row['descriptors']['assets']})
                    self.assertTrue(model['ok'],model)
            finally:api.close()

    def test_header_flags_extents_and_bad_checksum(self):
        from romancer.system_identify import identify_system
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'arbitrary.dat'
            for flag,mode in [(0,'dmg'),(0x80,'dmg-cgb'),(0xc0,'cgb-only')]:
                path.write_bytes(cartridge(color=flag));result=identify_system(path)
                self.assertEqual(result['system_id'],'gbc' if flag else 'gb');self.assertEqual(result['status'],'IDENTIFIED')
                meta=result['candidates'][0]['metadata'];self.assertEqual(meta['color_mode'],mode)
                self.assertEqual(meta['logo_validation'],'NOT_CHECKED');self.assertEqual(meta['rom_banks'],2)
            data=bytearray(cartridge());data[0x134]^=1;path.write_bytes(data)
            self.assertEqual(identify_system(path)['status'],'BLOCKED')
            path.write_bytes(cartridge()[:-1]);self.assertEqual(identify_system(path)['status'],'BLOCKED')
            path.write_bytes(bytes(32768));self.assertEqual(identify_system(path)['status'],'UNKNOWN')

    def test_interleaved_planes_literal_and_template(self):
        from romancer.asset_codecs import decode_cell,encode_cell
        from romancer.resource_forms import TEMPLATES
        codec='tile8-paired2-msb-v1';raw=bytes.fromhex('8040')+bytes(14)
        pixels=[1,2,0,0,0,0,0,0]+[0]*56
        self.assertEqual(TEMPLATES['gb'],codec)
        self.assertEqual(decode_cell(raw,codec=codec,width=8,height=8),pixels)
        self.assertEqual(encode_cell(pixels,codec=codec,width=8,height=8),raw)

    def test_both_checksums_repair_exact_fields_and_preserve_original(self):
        from romancer.system_integrity import integrity_edits
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'a.gb';original=cartridge();path.write_bytes(original)
            edits=integrity_edits(path,hashlib.sha256(original).hexdigest(),'gb',[{'offset':0x134,'before':'52','after':'53'}])
            output=bytearray(original)
            for edit in edits:output[edit['offset']:edit['offset']+len(bytes.fromhex(edit['after']))]=bytes.fromhex(edit['after'])
            self.assertEqual((sum(output[0x134:0x14e])+25)&255,0)
            self.assertEqual(int.from_bytes(output[0x14e:0x150],'big'),(sum(output[:0x14e])+sum(output[0x150:]))&65535)
            self.assertEqual(path.read_bytes(),original)
            with self.assertRaisesRegex(ValueError,'checksum'):
                integrity_edits(path,hashlib.sha256(original).hexdigest(),'gb',[{'offset':0x14f,'before':original[0x14f:0x150].hex(),'after':'00'}])

    def test_explicit_rom_banks_and_refusals(self):
        from romancer.system_addresses import translate
        self.assertEqual(translate('gb',0x1234,{'id':'gb-rom'},None,65536)['offset'],0x1234)
        self.assertEqual(translate('gb',0x4567,{'id':'gb-rom'},3,65536)['offset'],0xc567)
        for address,bank in [(0x4567,None),(0x8000,1),(0x4567,4),(0x1234,1)]:
            with self.subTest(address=address,bank=bank),self.assertRaises(ValueError):translate('gb',address,{'id':'gb-rom'},bank,65536)


if __name__=='__main__':unittest.main()
