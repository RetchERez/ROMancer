"""Authenticated loopback-only HTTP host for the ROMancer local workbench."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlsplit,parse_qs
import webbrowser
from . import ROMANCER_VERSION,ROMANCER_RELEASE_NAME
from .asset_schema import fields

from .script_schema import canonical_bytes
from .workbench_api import WorkbenchAPI
from .workbench_projects import write_json

MAX_BODY=1024**2
MAX_UPLOAD=64*1024**2
UI_ROOT=Path(__file__).parent/'ui'
GUIDE_ROOT=Path(__file__).resolve().parent.parent/'user-guide'
GUIDE_VIDEO='ROMancer-v1.0-Walkthrough.mp4'
GUIDE_CAPTIONS='walkthrough.en.vtt'


class Handler(BaseHTTPRequestHandler):
    server_version='ROMancer/'+ROMANCER_VERSION

    def log_message(self,*args):pass

    def _headers(self,status,kind,length):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(length))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def _json(self,status,result):
        try:raw=canonical_bytes(result,max_bytes=8*1024**2)
        except (ValueError,TypeError):status=500;raw=b'{"ok":false,"error":"Response exceeds the workbench budget; use a smaller request."}'
        self._headers(status,'application/json; charset=utf-8',len(raw));self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass

    def _host(self):
        return self.headers.get('Host')=='127.0.0.1:'+str(self.server.server_port)

    def _discard_small_body(self):
        # Drain bounded rejected requests so Windows TCP can deliver the error
        # response instead of resetting a socket with unread incoming bytes.
        try:
            length=int(self.headers.get('Content-Length','0'))
            if 0<length<=MAX_BODY+1:
                self.connection.settimeout(2);self.rfile.read(length)
        except (ValueError,OSError):pass

    def _authorize(self):
        if not self._host():self._discard_small_body();self._json(403,{'ok':False,'error':'Invalid local host'});return False
        origin=self.headers.get('Origin')
        if origin is not None and origin!='http://127.0.0.1:'+str(self.server.server_port):
            self._discard_small_body()
            self._json(403,{'ok':False,'error':'Cross-origin request refused'});return False
        token=self.headers.get('Authorization','')
        if not hmac.compare_digest(token,'Bearer '+self.server.session_token):
            self._discard_small_body()
            self._json(401,{'ok':False,'error':'This workbench session has expired. Reopen it from the launcher.'});return False
        return True

    def _guide_video(self,file):
        size=file.stat().st_size;start=0;end=size-1;status=200
        interval=self.headers.get('Range')
        if interval is not None:
            match=re.fullmatch(r'bytes=([0-9]{0,20})-([0-9]{0,20})',interval)
            valid=match is not None and any(match.groups()) and size>0
            if valid:
                first,last=match.groups()
                if first:
                    start=int(first);end=min(int(last),size-1) if last else size-1
                    valid=start<size and end>=start
                else:
                    count=int(last);valid=count>0;start=max(0,size-count)
            if not valid:
                self._headers(416,'video/mp4',0);self.send_header('Content-Range','bytes */'+str(size));self.send_header('Accept-Ranges','bytes');self.end_headers();return
            status=206
        length=max(0,end-start+1);self._headers(status,'video/mp4',length);self.send_header('Accept-Ranges','bytes')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with file.open('rb') as stream:
                stream.seek(start);remaining=length
                while remaining:
                    chunk=stream.read(min(65536,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

    def do_GET(self):
        if not self._host():self._json(403,{'ok':False,'error':'Invalid local host'});return
        path=urlsplit(self.path).path
        if path.startswith('/api/'):
            if not self._authorize():return
            self._json(405,{'ok':False,'error':'Use POST for workbench operations'});return
        guide=path.startswith('/user-guide/')
        root=GUIDE_ROOT if guide else UI_ROOT
        name=path[len('/user-guide/'):] if guide else ('index.html' if path=='/' else path.lstrip('/'))
        if (not name or '\\' in name or '%' in name or any(p in ('','.','..') for p in name.split('/'))
                or Path(name).suffix not in (('.html','.css','.pdf','.png','.js','.mp4','.vtt') if guide else ('.html','.css','.js','.svg'))
                or (guide and Path(name).suffix=='.js' and name!='guide.js')
                or (guide and Path(name).suffix in ('.mp4','.vtt') and name not in (GUIDE_VIDEO,GUIDE_CAPTIONS))):
            self._json(404,{'ok':False,'error':'Page not found'});return
        file=root/name
        if (root.is_symlink() or root.is_junction() or not file.is_file() or file.is_symlink() or file.is_junction()
                or not file.resolve().is_relative_to(root.resolve())
                or any(p.is_symlink() or p.is_junction() for p in file.parents if p!=root and root in p.parents)):
            self._json(404,{'ok':False,'error':'Page not found'});return
        if guide and name==GUIDE_VIDEO:self._guide_video(file);return
        raw=file.read_bytes();kind='text/vtt' if guide and name==GUIDE_CAPTIONS else mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        self._headers(200,kind+('; charset=utf-8' if kind.startswith('text/') or kind in ('application/javascript',) else ''),len(raw));self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass

    def do_POST(self):
        if not self._authorize():return
        self.connection.settimeout(30)
        try:
            if self.headers.get('Transfer-Encoding') is not None:raise ValueError('chunked requests are not supported')
            length=int(self.headers.get('Content-Length','-1'))
            path=urlsplit(self.path).path;limit=MAX_UPLOAD if path=='/api/upload' else MAX_BODY
            if length<0:raise ValueError('Content-Length is required')
            if length>limit:self._discard_small_body();self.close_connection=True;self._json(413,{'ok':False,'error':'Request exceeds the byte budget'});return
            if path=='/api/upload':self._upload(length);return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON content type is required')
            raw=self.rfile.read(length)
            if len(raw)!=length:raise ValueError('request body is truncated')
            from .runtime_protocol import _pairs,_float,_constant
            document=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_float=_float,parse_constant=_constant)
            canonical_bytes(document,max_bytes=MAX_BODY)
            if path=='/api/call':
                fields(document,'operation parameters')
                if type(document['operation']) is not str:raise ValueError('operation must be a string')
                result=self.server.api.dispatch(document['operation'],document['parameters']);self._json(200,result)
            elif path=='/api/download':
                fields(document,'project_id export_id');file,row=self.server.api.download(**document)
                self._headers(200,'application/octet-stream',row['size'])
                self.send_header('Content-Disposition','attachment; filename="'+row.get('download_name',row['name'])+'"');self.end_headers()
                with file.open('rb') as stream:
                    while chunk:=stream.read(65536):self.wfile.write(chunk)
            else:self._json(404,{'ok':False,'error':'Unknown endpoint'})
        except (ValueError,KeyError,TypeError,UnicodeError,TimeoutError,OSError):
            self._json(400,{'ok':False,'error':'Invalid or incomplete request. Check the selected inputs and try again.'})

    def _upload(self,length):
        query=parse_qs(urlsplit(self.path).query,strict_parsing=True)
        if (set(query) not in ({'project_id','name'},{'project_id','name','kind'})
                or any(len(v)!=1 for v in query.values())):raise ValueError('invalid upload selection')
        project_id=query['project_id'][0];name=query['name'][0]
        if not name or len(name)>240 or Path(name).name!=name or any(c in name for c in '\\/:\x00'):raise ValueError('unsafe upload name')
        project=self.server.api.project({'project_id':project_id})
        fd,temp=tempfile.mkstemp(prefix='upload-',suffix=Path(name).suffix[:16],dir=self.server.api.incoming)
        try:
            with os.fdopen(fd,'wb') as stream:
                remaining=length
                while remaining:
                    chunk=self.rfile.read(min(65536,remaining))
                    if not chunk:raise ValueError('truncated upload')
                    stream.write(chunk);remaining-=len(chunk)
            if 'kind' in query:
                result=self.server.api.dispatch('inputs.import',{'project_id':project_id,'path':temp,'name':name,'kind':query['kind'][0]})
            else:result=self.server.api.dispatch('source.import',{'project_id':project_id,'path':temp,'system':None})
            if result.get('ok') and 'kind' not in query:
                # Preserve the selected filename in the project, never use it as a storage path.
                from .workbench_projects import locked,write_json
                with locked(project) as value:
                    for source in value['sources']:
                        if source['artifact_id']==result['artifact_id']:source['name']=name;result['name']=name
                    write_json(project/'project.json',value)
            self._json(200,result)
        finally:Path(temp).unlink(missing_ok=True)


def create_server(workspace:Path,port:int=0):
    if type(port) is not int or not 0<=port<=65535:raise ValueError('invalid local port')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    server.session_token=secrets.token_urlsafe(32)
    try:server.api=WorkbenchAPI(workspace)
    except BaseException:server.server_close();raise
    return server


def serve(workspace:Path,port:int=0,open_browser:bool=True):
    server=create_server(workspace,port);url='http://127.0.0.1:'+str(server.server_port)+'/#token='+server.session_token
    write_json(Path(workspace)/'connection.json',{'url':url,'pid':os.getpid(),'port':server.server_port})
    print(ROMANCER_RELEASE_NAME+' • By RetchEWretched',flush=True)
    print(url,flush=True)
    if open_browser:webbrowser.open(url)
    try:server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:pass
    finally:server.server_close();server.api.close()


def main():
    parser=argparse.ArgumentParser(description='ROMancer local workbench — By RetchEWretched')
    parser.add_argument('--workspace',type=Path,default=Path.home()/'Documents'/'ROMancer Projects')
    parser.add_argument('--port',type=int,default=0);parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args();serve(args.workspace,args.port,not args.no_browser)


if __name__=='__main__':main()
