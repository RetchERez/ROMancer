from pathlib import Path
import hashlib,tempfile,unittest
from romancer.system_identify import identify_system
from romancer.system_integrity import integrity_edits
from tests.test_cartridge_integrity import expanded_mirror

def authored(size,*,extended=False,prefix=0):
 raw=bytearray(size);h=0x40ffc0 if extended else 0x7fc0
 raw[h:h+21]=b'CHECKSUM SIZE FIXTURE';raw[h+21]=0x35 if extended else 0x20;raw[h+22]=2;raw[h+23]=((size-1).bit_length())-10
 raw[-32768]=17;raw[h+28:h+32]=bytes.fromhex('ffff0000')
 value=expanded_mirror(raw);raw[h+28:h+32]=(value^65535).to_bytes(2,'little')+value.to_bytes(2,'little')
 return bytes(prefix)+bytes(raw)
class SnesEditSizesTests(unittest.TestCase):
 def test_non_power_of_two_and_checked_extended_storage_keep_weighted_checksums(self):
  for size,extended,prefix in[(0x180000,False,0),(0x300000,False,512),(0x600000,True,0)]:
   with self.subTest(size=size,extended=extended,prefix=prefix),tempfile.TemporaryDirectory()as directory:
    raw=authored(size,extended=extended,prefix=prefix);path=Path(directory)/'source.sfc';path.write_bytes(raw);self.assertEqual(identify_system(path)['status'],'IDENTIFIED')
    at=len(raw)-32768;edits=integrity_edits(path,hashlib.sha256(raw).hexdigest(),'snes',[{'offset':at,'before':'11','after':'12'}]);built=bytearray(raw)
    for edit in edits:self.assertEqual(bytes.fromhex(edit['before']),raw[edit['offset']:edit['offset']+len(bytes.fromhex(edit['after']))]);built[edit['offset']:edit['offset']+len(bytes.fromhex(edit['after']))]=bytes.fromhex(edit['after'])
    h=prefix+(0x40ffc0 if extended else 0x7fc0);self.assertEqual(int.from_bytes(built[h+30:h+32],'little'),expanded_mirror(built[prefix:]));self.assertEqual(path.read_bytes(),raw)
    self.assertEqual(identify_system(path)['status'],'IDENTIFIED')
 def test_unmatched_extended_convention_refuses_automatic_repair(self):
  raw=bytearray(authored(0x600000,extended=True));h=0x40ffc0;value=int.from_bytes(raw[h+30:h+32],'little')^1;raw[h+28:h+32]=(value^65535).to_bytes(2,'little')+value.to_bytes(2,'little')
  with tempfile.TemporaryDirectory()as directory:
   path=Path(directory)/'source.sfc';path.write_bytes(raw)
   with self.assertRaisesRegex(ValueError,'convention|preserv'):integrity_edits(path,hashlib.sha256(raw).hexdigest(),'snes',[{'offset':512,'before':'00','after':'01'}])
