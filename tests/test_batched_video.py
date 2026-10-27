import ctypes,unittest
from unittest.mock import patch
from romancer.libretro_frontend import LibretroFrontend,RETRO_PIXEL_FORMAT_XRGB8888

class BatchedVideoTests(unittest.TestCase):
    def test_intermediate_frames_are_not_converted_and_duplicate_frame_keeps_owned_last_pixels(self):
        f=LibretroFrontend.__new__(LibretroFrontend);f._loaded=True;f.frame_index=0;f.last_frame=None;f.pixel_format=RETRO_PIXEL_FORMAT_XRGB8888;f.shutdown_requested=False;f.hardware_video_seen=False;f._joypads={}
        buffer=(ctypes.c_uint32*1)();count=0
        def run():
            nonlocal count
            count+=1;buffer[0]=0x00102030 if count==1 else 0x00405060 if count==2 else 0x00abcdef
            f._video_refresh(ctypes.addressof(buffer) if count<3 else 0,1,1,4)
        f.lib=type('Core',(),{'retro_run':staticmethod(run)})()
        with patch.object(f,'_convert_frame',wraps=f._convert_frame) as convert:result=f.run_frames(3)
        self.assertEqual(convert.call_count,1,'Batching must decode only the last actual native buffer.')
        self.assertEqual(result.rgb,bytes.fromhex('405060'));self.assertEqual(result.index,2);self.assertEqual(f.frame_index,3)
        self.assertIsNone(getattr(f,'_pending_video',None));self.assertFalse(getattr(f,'_batch_video',False))
