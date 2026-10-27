import base64,hashlib,unittest
from romancer.visual_checks import _png

class SceneCompositeTests(unittest.TestCase):
    def test_shared_flipped_tiles_change_their_scene_positions_and_preserve_every_other_pixel(self):
        from romancer.scene_composite import composite
        rgb=bytes([10,20,30])*32*16
        scene={'width':32,'height':16,'sha256':hashlib.sha256(rgb).hexdigest(),'png_base64':_png(rgb,32,16)}
        d={'scene_region':{'x':4,'y':4,'width':24,'height':8},'layout':{'columns':3,'rows':1,'indices':[0,None,0],'flips':[0,0,1],'colors':[{'0':[10,20,30],'1':[200,50,60]},None,{'0':[10,20,30],'1':[200,50,60]}]}}
        after=[0]*64;after[0]=1
        r=composite(scene,d,{0:[0]*64},[{'cell_index':0,'pixels':after}]);self.assertEqual(r['changed_pixels'],2);self.assertTrue(r['simulated']);self.assertFalse(r['emulated_frame'])
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(base64.b64decode(r['preview_png_base64']))) as image:
            self.assertEqual(image.getpixel((4,4)),(200,50,60));self.assertEqual(image.getpixel((27,4)),(200,50,60));self.assertEqual(image.getpixel((12,4)),(10,20,30))
        self.assertEqual(scene['sha256'],hashlib.sha256(rgb).hexdigest())
        d['layout']['colors'][0].pop('1')
        with self.assertRaisesRegex(ValueError,'color'):composite(scene,d,{0:[0]*64},[{'cell_index':0,'pixels':after}])
    def test_changed_frame_identity_bounds_duplicate_or_unused_edits_are_rejected(self):
        from romancer.scene_composite import composite
        rgb=bytes(8*8*3);scene={'width':8,'height':8,'sha256':'f'*64,'png_base64':_png(rgb,8,8)}
        d={'scene_region':{'x':0,'y':0,'width':8,'height':8},'layout':{'columns':1,'rows':1,'indices':[0],'flips':[0],'colors':[{'0':[0,0,0]}]}}
        with self.assertRaises(ValueError):composite(scene,d,{0:[0]*64},[])
        scene['sha256']=hashlib.sha256(rgb).hexdigest();d['scene_region']['x']=1
        with self.assertRaises(ValueError):composite(scene,d,{0:[0]*64},[])
