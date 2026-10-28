import re,unittest
from pathlib import Path

def luminance(hex):
    channels=[int(hex[i:i+2],16)/255 for i in (1,3,5)];return sum(w*(x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4) for w,x in zip((.2126,.7152,.0722),channels))
def contrast(a,b):
    x,y=sorted([luminance(a),luminance(b)]);return (y+.05)/(x+.05)
class ReadabilityTests(unittest.TestCase):
    def test_romancer_original_palette_has_deeper_menus_and_readable_contrast(self):
        css=(Path(__file__).resolve().parents[1]/'romancer/ui/theme.css').read_text(encoding='utf-8');root=re.search(r':root\{([^}]+)',css)[1];colors=dict(re.findall(r'(--[\w-]+):(#[0-9a-f]{6})',root))
        self.assertLess(luminance(colors['--theme-nav']),luminance(colors['--bg']))
        self.assertLess(luminance(colors['--theme-menu']),luminance(colors['--panel']))
        background=colors['--bg'];channels=[int(background[i:i+2],16) for i in (1,3,5)];self.assertLess(max(channels)-min(channels),16,'Workspace surfaces should stay neutral; green is an accent.')
        self.assertGreater(luminance(colors['--panel']),luminance(colors['--bg']))
        for surface in ('--bg','--panel','--panel2','--theme-nav','--theme-menu'):
            for ink in ('--text','--muted','--accent'):self.assertGreaterEqual(contrast(colors[ink],colors[surface]),4.5,(ink,surface))
