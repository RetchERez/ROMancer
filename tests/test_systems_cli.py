import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tests.test_system_identify import nes_bytes


class SystemCLITests(unittest.TestCase):
    def call(self,*args):
        process=subprocess.run([sys.executable,'-B','-m','romancer',*map(str,args),'--json'],capture_output=True,text=True,timeout=15)
        return process,json.loads(process.stdout)

    def test_registry_identification_and_chr_routes(self):
        process,inventory=self.call('systems-list');self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual({s['id'] for s in inventory['systems']},{'nes','snes','genesis','gb','gbc','gba'})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'original Ω with spaces.bin';raw=nes_bytes();path.write_bytes(raw)
            process,report=self.call('systems-identify',path);self.assertEqual(process.returncode,0,report)
            self.assertEqual(report['system_id'],'nes');self.assertFalse(report['write_authorized'])
            sha=hashlib.sha256(raw).hexdigest()
            process,descriptor=self.call('systems-nes-chr',path,'--expect-sha',sha,'--first-tile',16,'--count',2)
            self.assertEqual(process.returncode,0,descriptor);self.assertEqual(descriptor['schema']['bitmaps'][0]['offset'],16+16384+256)
            process,blocked=self.call('systems-nes-chr',path,'--expect-sha','0'*64)
            self.assertEqual(process.returncode,1);self.assertEqual(blocked['status'],'BLOCKED')
            path.write_bytes(b'UNKNOWN');process,unknown=self.call('systems-identify',path)
            self.assertEqual(process.returncode,0);self.assertEqual(unknown['status'],'UNKNOWN')
            self.assertEqual(list(Path(temp).iterdir()),[path])


if __name__=='__main__':unittest.main()
