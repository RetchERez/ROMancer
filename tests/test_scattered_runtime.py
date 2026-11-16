from pathlib import Path
import hashlib,tempfile,unittest
from unittest.mock import patch,Mock
from romancer.system_formats import genesis
from romancer.runtime_worker import Workspace
from tests.test_scattered_genesis import authored,signature
class ScatteredRuntimeTests(unittest.TestCase):
 def test_core_receives_checked_bus_view_while_source_and_snapshot_stay_physical(self):
  raw=authored()
  with tempfile.TemporaryDirectory()as directory,patch.dict(genesis.__dict__,{'SCATTERED_HEADERS':{(len(raw),signature(raw)):'quackshot-continue-v1'}}):
   root=Path(directory);game=root/'original.bin';game.write_bytes(raw);core=root/'core.bin';core.write_bytes(b'authored core fixture')
   front=Mock();front.load_game.return_value={};front.av_info.return_value={};front.memory_region.return_value=b''
   workspace=Workspace()
   try:
    with patch('romancer.runtime_worker.LibretroFrontend',return_value=front):
     result=workspace.load({'core':str(core),'game':str(game),'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(raw).hexdigest(),'session_dir':str(root/'session')})
    staged=front.load_game.call_args.args[0];value=staged.read_bytes();self.assertEqual(len(value),0x140000)
    self.assertEqual(value[:0x40000],raw[:0x40000]);self.assertEqual(value[0x100000:],raw[0x40000:]);self.assertEqual(value[0x40000:0x100000],bytes(0xc0000))
    self.assertEqual(game.read_bytes(),raw);self.assertEqual((root/'session/content/original.bin').read_bytes(),raw)
    self.assertEqual(result['game_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(result['content_view']['sha256'],hashlib.sha256(value).hexdigest());before=result['runtime_identity_sha256']
    workspace._content_view={**workspace._content_view,'sha256':'0'*64};self.assertNotEqual(workspace._binding()['runtime_identity_sha256'],before)
   finally:workspace.close()

 def test_snapshot_mapping_does_not_consult_a_replaced_original_after_copy(self):
  from romancer import runtime_worker as worker
  raw=authored()
  with tempfile.TemporaryDirectory()as directory,patch.dict(genesis.__dict__,{'SCATTERED_HEADERS':{(len(raw),signature(raw)):'quackshot-continue-v1'}}):
   root=Path(directory);game=root/'original.bin';game.write_bytes(raw);core=root/'core.bin';core.write_bytes(b'authored fixture')
   front=Mock();front.load_game.return_value={};front.av_info.return_value={};front.memory_region.return_value=b'';original_snapshot=worker._snapshot
   def copy_then_replace(source,destination,expected,remaining):
    result=original_snapshot(source,destination,expected,remaining)
    if source==game:game.write_bytes(bytes(9*1024**2))
    return result
   workspace=Workspace()
   try:
    with patch('romancer.runtime_worker.LibretroFrontend',return_value=front),patch.object(worker,'_snapshot',side_effect=copy_then_replace):
     result=workspace.load({'core':str(core),'game':str(game),'expected_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),'expected_game_sha256':hashlib.sha256(raw).hexdigest(),'session_dir':str(root/'session')})
    self.assertEqual(front.load_game.call_args.args[0].stat().st_size,0x140000)
    self.assertEqual(result['content_view']['source_sha256'],hashlib.sha256(raw).hexdigest())
   finally:workspace.close()
