from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError


class UserGuideTests(unittest.TestCase):
    def test_reviewed_guide_and_new_ui_files_join_source_inventory(self):
        from tools.package_source import APPROVED_FILES, DIRECTORIES
        required={'user-guide/index.html','user-guide/guide.css','user-guide/guide.js','user-guide/guide.pdf','user-guide/guide.json',
                  'tools/build_user_guide.py','romancer/verified_room.py','romancer/ui/room_editor.js',
                  'tests/ui_interface_scale.mjs','tests/ui_room_editor.mjs','tests/test_verified_room.py','tests/test_user_guide.py'}
        self.assertFalse(required-APPROVED_FILES,required-APPROVED_FILES)
        self.assertIn('user-guide',DIRECTORIES)

    def test_guide_static_routes_keep_security_headers_and_reject_non_guides(self):
        from romancer import workbench_server as module
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);guide=root/'guide';guide.mkdir();(guide/'screenshots').mkdir()
            for name,raw in [('index.html',b'<link rel="stylesheet" href="guide.css">'),('guide.css',b'body{color:black}'),('guide.js',b'"use strict";'),('other.js',b'not permitted'),('guide.pdf',b'%PDF-1.7\nfixture'),('screenshots/example.png',b'\x89PNG\r\n\x1a\nfixture')]:
                (guide/name).write_bytes(raw)
            (guide/'private.json').write_text('{"private":true}')
            with patch.object(module,'GUIDE_ROOT',guide):
                server=module.create_server(root/'workspace');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(server.server_port)
                try:
                    for name,kind in [('index.html','text/html'),('guide.css','text/css'),('guide.js','javascript'),('guide.pdf','application/pdf'),('screenshots/example.png','image/png')]:
                        with urlopen(base+'/user-guide/'+name,timeout=5) as response:
                            self.assertEqual(response.read(),(guide/name).read_bytes())
                            self.assertIn(kind,response.headers['Content-Type'])
                            self.assertIn("style-src 'self'",response.headers['Content-Security-Policy'])
                            self.assertNotIn('unsafe-inline',response.headers['Content-Security-Policy'])
                    for path in ['../README.txt','private.json','other.js','screenshots/guide.js','%2e%2e/README.txt','screenshots/../../README.txt','missing.png']:
                        with self.assertRaises(HTTPError) as caught:urlopen(base+'/user-guide/'+path,timeout=5)
                        self.assertEqual(caught.exception.code,404);caught.exception.close()
                finally:server.shutdown();server.server_close();server.api.close();thread.join(3)
