import hashlib,unittest
from romancer.format_readiness import checked_formats
from romancer.studio_runtime import make_collision_studio_rom,runtime_definitions
class FormatReadinessTests(unittest.TestCase):
 def test_original_program_recognition_never_grants_native_or_write_authority(self):
  raw=make_collision_studio_rom()['data'];sha=hashlib.sha256(raw).hexdigest();result=checked_formats(raw,sha,{})
  self.assertEqual(result['engine']['id'],'mossy-runtime-v1');self.assertEqual(len(result['features']),4)
  self.assertFalse(result['native_playtest_verified']);self.assertFalse(result['write_authorized'])
  raw=bytearray(raw);raw[16]^=1;self.assertIsNone(checked_formats(bytes(raw),hashlib.sha256(raw).hexdigest(),{})['engine'])
 def test_author_labels_cannot_forge_engine_evidence(self):
  r=make_collision_studio_rom();raw=bytearray(r['data']);raw[16]^=1;raw=bytes(raw);sha=hashlib.sha256(raw).hexdigest();defs=runtime_definitions(r,sha)
  result=checked_formats(raw,sha,defs);self.assertIsNone(result['engine']);self.assertTrue(all(f['status']=='declared_layout' for f in result['features']))
