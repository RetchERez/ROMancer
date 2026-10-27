import base64,hashlib,unittest
from romancer.asset_codecs import encode_cell
from romancer.graphics_discovery import SYSTEM_CODECS,match_graphics
from romancer.visual_source import locator_markers,learn_mapping,validation_markers,assess_mapping,group_candidates,encoding_lanes

def frame(rgb,w=8,h=8):return {'ok':True,'width':w,'height':h,'index':10,'sha256':hashlib.sha256(rgb).hexdigest(),'rgb24_base64':base64.b64encode(rgb).decode()}

class VisualSourceTests(unittest.TestCase):
    def setup_case(self,system='genesis',height=8,flip=False):
        codec=SYSTEM_CODECS[system];pixels=[0 if (x+y)%11==0 else 1+(x+2*y)%3 for y in range(height) for x in range(8)]
        raw=b''.join(encode_cell(pixels[i:i+64],codec=codec,width=8,height=8) for i in range(0,len(pixels),64));match={'offset':0,'length':len(raw),'width':8,'height':height,'x':0,'y':0,'flip_x':flip,'flip_y':flip,'codec':codec}
        colors=[b'\0\0\0',b'\xff\0\0',b'\0\xff\0',b'\0\0\xff']
        def render(pp):
            pp=list(reversed(pp)) if flip else pp
            return frame(b''.join(colors[p] for p in pp),8,height)
        return raw,match,pixels,render
    def test_seven_codecs_recover_unique_pixel_origins_then_cross_validate_including_flips(self):
        for system in SYSTEM_CODECS:
            for height in ((8,16) if system=='nes' else (8,)):
                for flip in (False,True):
                    with self.subTest(system=system,height=height,flip=flip):
                        raw,m,pixels,render=self.setup_case(system,height,flip);original=render(pixels);loc=locator_markers(raw,m);mapping=learn_mapping(original,[render(v['pixels']) for v in loc],m,loc)
                        self.assertGreaterEqual(mapping['unique_source_pixels'],16);markers=validation_markers(raw,m,mapping);r=assess_mapping(original,[render(v['pixels']) for v in markers],m,mapping,markers)
                        self.assertEqual(r['status'],'VERIFIED_VISUAL_SOURCE',r);self.assertFalse(r['source_transfer_observed']);self.assertGreaterEqual(r['verified_pixels'],16)
                        changed=bytearray(base64.b64decode(render(markers[0]['pixels'])['rgb24_base64']));changed=bytes(v^1 for v in changed)
                        bad=assess_mapping(original,[frame(changed,8,height),render(markers[1]['pixels'])],m,mapping,markers);self.assertEqual(bad['status'],'NOT_VERIFIED')
    def test_global_palette_recoloring_cannot_masquerade_as_distinct_source_pixels(self):
        pixels=[];n=0
        for i in range(64):
            if i%11==0:pixels.append(0)
            else:pixels.append(1+n%2);n+=1
        colors=[b'\0\0\0',b'\xff\0\0',b'\0\xff\0'];raw=encode_cell(pixels,codec=SYSTEM_CODECS['genesis'],width=8,height=8);rgb=b''.join(colors[v] for v in pixels)
        accepted=match_graphics(raw,rgb,8,8,'genesis');self.assertTrue(accepted['matches']);m=accepted['matches'][0];loc=locator_markers(raw,m)
        fake=[frame(b''.join((colors[1] if n%2 else colors[2]) if v else colors[0] for v in pixels)) for n in range(len(loc))]
        with self.assertRaisesRegex(ValueError,'distinct|origin|color'):learn_mapping(frame(rgb),fake,m,loc)
    def test_partial_mask_is_in_screen_coordinates_and_does_not_discard_failed_validation_pixels(self):
        raw,m,pixels,render=self.setup_case(flip=True);original=render(pixels);loc=locator_markers(raw,m);frames=[]
        for v in loc:
            pp=list(v['pixels']);pp[0]=pixels[0];frames.append(render(pp))
        mapping=learn_mapping(original,frames,m,loc);markers=validation_markers(raw,m,mapping);r=assess_mapping(original,[render(v['pixels']) for v in markers],m,mapping,markers)
        self.assertEqual(r['status'],'VERIFIED_VISUAL_SOURCE');self.assertNotIn(0,[x['source_pixel'] for x in r['pixel_map']]);self.assertNotIn(63,r['verified_pixel_indices'])
    def test_automatic_search_keeps_aliases_and_reports_remaining_groups(self):
        base={'length':16,'width':8,'height':8,'x':0,'y':0,'flip_x':False,'flip_y':False,'codec':'tile8-planar2-msb-v1','visible_pixels':64};r={'matches':[{**base,'offset':17},{**base,'offset':32},{**base,'offset':32,'x':8},{**base,'offset':48}],'region':{'x':0,'y':0,'width':16,'height':8}}
        g=group_candidates(r,0,1);self.assertEqual(g['groups'][0]['offset'],32);self.assertEqual(g['groups'][0]['match_ids'],[1,2]);self.assertEqual(g['next'],1);self.assertEqual(g['total'],3)
        with self.assertRaises(ValueError):group_candidates(r,0,9)

    def test_reported_pixel_byte_lanes_match_the_actual_codec_encoding(self):
        for system,codec in SYSTEM_CODECS.items():
            m={'offset':1000,'codec':codec,'height':8,'width':8}
            for position in (0,7,8,63):
                pixels=[0]*64;pixels[position]=3;data=encode_cell(pixels,codec=codec,width=8,height=8);actual={1000+i for i,v in enumerate(data) if v};declared={r['offset'] for r in encoding_lanes(m,position)}
                self.assertTrue(actual<=declared,(system,position,actual,declared))

if __name__=='__main__':unittest.main()
