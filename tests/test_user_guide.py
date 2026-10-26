from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError


class UserGuideTests(unittest.TestCase):
    def test_walkthrough_declaration_requires_approved_complete_media(self):
        import json
        from tools.build_user_guide import load_content
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data={'schema_version':1,'chapters':[{'id':'watch','part':'Basic','video':True}],'glossary':[],'index':[]}
            (root/'guide.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'video and captions'):load_content(root)
            (root/'ROMancer-v1.0-Walkthrough.mp4').write_bytes(b'\x00\x00\x00\x20ftypisom'+b'\x00'*20)
            (root/'walkthrough.en.vtt').write_text('WEBVTT\n\n',encoding='utf-8')
            self.assertIs(load_content(root)['chapters'][0]['video'],True)
            data['chapters'][0]['video']='https://example.invalid/movie.mp4'
            (root/'guide.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'approved local'):load_content(root)
            data['chapters'][0]['video']=True;(root/'guide.json').write_text(json.dumps(data),encoding='utf-8')
            (root/'walkthrough.en.vtt').write_text('wrong caption format',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'unexpected format'):load_content(root)

    def test_reviewed_guide_and_new_ui_files_join_source_inventory(self):
        from tools.package_source import APPROVED_FILES, DIRECTORIES
        required={'user-guide/index.html','user-guide/guide.css','user-guide/guide.js','user-guide/guide.pdf','user-guide/guide.json',
                  'user-guide/ROMancer-v1.0-Walkthrough.mp4','user-guide/walkthrough.en.vtt',
                  'tools/build_user_guide.py','romancer/verified_room.py','romancer/ui/room_editor.js',
                  'tests/ui_interface_scale.mjs','tests/ui_room_editor.mjs','tests/test_verified_room.py','tests/test_user_guide.py'}
        self.assertFalse(required-APPROVED_FILES,required-APPROVED_FILES)
        self.assertIn('user-guide',DIRECTORIES)

    def test_guide_static_routes_keep_security_headers_and_reject_non_guides(self):
        from romancer import workbench_server as module
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);guide=root/'guide';guide.mkdir();(guide/'screenshots').mkdir()
            for name,raw in [('index.html',b'<link rel="stylesheet" href="guide.css">'),('guide.css',b'body{color:black}'),('guide.js',b'"use strict";'),('other.js',b'not permitted'),('guide.pdf',b'%PDF-1.7\nfixture'),('screenshots/example.png',b'\x89PNG\r\n\x1a\nfixture'),('ROMancer-v1.0-Walkthrough.mp4',b'0123456789abcdef'),('walkthrough.en.vtt',b'WEBVTT\n\n')]:
                (guide/name).write_bytes(raw)
            (guide/'private.json').write_text('{"private":true}')
            with patch.object(module,'GUIDE_ROOT',guide):
                server=module.create_server(root/'workspace');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(server.server_port)
                try:
                    for name,kind in [('index.html','text/html'),('guide.css','text/css'),('guide.js','javascript'),('guide.pdf','application/pdf'),('screenshots/example.png','image/png'),('ROMancer-v1.0-Walkthrough.mp4','video/mp4'),('walkthrough.en.vtt','text/vtt')]:
                        with urlopen(base+'/user-guide/'+name,timeout=5) as response:
                            self.assertEqual(response.read(),(guide/name).read_bytes())
                            self.assertIn(kind,response.headers['Content-Type'])
                            self.assertIn("style-src 'self'",response.headers['Content-Security-Policy'])
                            self.assertNotIn('unsafe-inline',response.headers['Content-Security-Policy'])
                    from urllib.request import Request
                    for interval,expected in [('bytes=2-5',b'2345'),('bytes=12-',b'cdef'),('bytes=-3',b'def'),('bytes=14-99',b'ef')]:
                        with urlopen(Request(base+'/user-guide/ROMancer-v1.0-Walkthrough.mp4',headers={'Range':interval}),timeout=5) as response:
                            self.assertEqual(response.status,206);self.assertEqual(response.read(),expected)
                            self.assertEqual(response.headers['Accept-Ranges'],'bytes');self.assertIn('/16',response.headers['Content-Range'])
                    for interval in ['bytes=99-','bytes=5-2','bytes=-0','bytes=1-2,4-5','bytes=','junk']:
                        with self.assertRaises(HTTPError) as caught:urlopen(Request(base+'/user-guide/ROMancer-v1.0-Walkthrough.mp4',headers={'Range':interval}),timeout=5)
                        self.assertEqual(caught.exception.code,416);self.assertEqual(caught.exception.headers['Content-Range'],'bytes */16');caught.exception.close()
                    for path in ['../README.txt','private.json','other.js','other.mp4','screenshots/ROMancer-v1.0-Walkthrough.mp4','other.vtt','screenshots/guide.js','%2e%2e/README.txt','screenshots/../../README.txt','missing.png']:
                        with self.assertRaises(HTTPError) as caught:urlopen(base+'/user-guide/'+path,timeout=5)
                        self.assertEqual(caught.exception.code,404);caught.exception.close()
                finally:server.shutdown();server.server_close();server.api.close();thread.join(3)
