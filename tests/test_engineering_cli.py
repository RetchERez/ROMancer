import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from asset_fixtures import asset_fixture


class EngineeringCLITests(unittest.TestCase):
    def test_asset_cli_runs_real_inspection_and_bad_descriptor_refuses(self):
        from romancer.cli import main
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source,schema=asset_fixture(root);path=root/'schema.json';path.write_text(json.dumps(schema))
            class Output(io.StringIO):
                def __init__(self):super().__init__();self.buffer=io.BytesIO()
            out=Output()
            with contextlib.redirect_stdout(out):code=main(['asset-inspect',str(path),str(source),'--json'])
            self.assertEqual(code,0);self.assertTrue(json.loads(out.buffer.getvalue())['ok'])
            path.write_text('{}');out=Output()
            with contextlib.redirect_stdout(out):code=main(['asset-inspect',str(path),str(source),'--json'])
            self.assertEqual(code,1);self.assertFalse(json.loads(out.buffer.getvalue())['ok'])
