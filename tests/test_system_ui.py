from pathlib import Path
import shutil
import subprocess
import unittest

NODE=shutil.which('node') or (r'C:\Program Files\nodejs\node.exe' if Path(r'C:\Program Files\nodejs\node.exe').is_file() else None)


class IndexedUITests(unittest.TestCase):
    @unittest.skipUnless(NODE,'Node runtime for actual UI module regression')
    def test_palette_free_nes_exposes_four_distinct_literal_indices(self):
        script="""
import assert from 'node:assert/strict';
import {literalColorCount,literalRGB} from './romancer/ui/views/assets.js';
const bitmap={codec:'tile8-planar2-msb-v1'};
assert.equal(literalColorCount(bitmap,undefined),4);
assert.equal(literalColorCount(bitmap,{colors_per_bank:16}),4);
assert.equal(literalColorCount({codec:'tile8-packed4-high-v1'},undefined),16);
assert.equal(literalColorCount({codec:'unknown'},undefined),0);
assert.equal(new Set([0,1,2,3].map(i=>JSON.stringify(literalRGB(bitmap,i)))).size,4);
"""
        result=subprocess.run([NODE,'--input-type=module','-e',script],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
