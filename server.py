#!/usr/bin/env python3
"""THE WAR ROOM — local web interface for the subscription/local controller."""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from controller import Controller

ROOT=Path(__file__).resolve().parent

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass  # No prompts, credentials, or browser tokens in logs.
    def send(self,status,data,content='application/json',headers=None):
        body=json.dumps(data).encode() if content=='application/json' else data
        self.send_response(status)
        for key,value in {'Content-Type':content,'Content-Length':str(len(body)),
            'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",**(headers or {})}.items(): self.send_header(key,value)
        self.end_headers();self.wfile.write(body)
    def allowed_host(self):
        return self.headers.get('Host') in self.server.hosts
    def authenticated(self):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception:return False
        value=cookie.get('warroom')
        if value and hmac.compare_digest(value.value,self.server.token):return True
        return self.client_address[0]=='127.0.0.1'  # Auto-auth localhost
    def do_GET(self):
        if not self.allowed_host():return self.send(403,{'error':'Invalid host'})
        path=urlparse(self.path).path
        if path.startswith('/api/'):
            if not self.authenticated():return self.send(401,{'error':'Open THE WAR ROOM from its launch link to connect.'})
            if path=='/api/state':
                return self.send(200,{'providers':self.server.controller.status(),'runs':self.server.controller.store.runs(),
                    'workspace':str(self.server.docs),'probing':self.server.probing,'app':'THE WAR ROOM'})
            return self.send(404,{'error':'Not found'})
        assets={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if path not in assets:return self.send(404,{'error':'Not found'})
        name,mime=assets[path];self.send(200,(ROOT/'static'/name).read_bytes(),mime)
    def do_POST(self):
        if not self.allowed_host():return self.send(403,{'error':'Invalid host'})
        origin=self.headers.get('Origin')
        if origin not in self.server.origins:return self.send(403,{'error':'Same-origin requests only'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'JSON required'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=100000:return self.send(413,{'error':'Request too large or empty'})
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('Expected an object')
            path=urlparse(self.path).path
            if path=='/api/unlock':
                if not isinstance(data.get('token'),str) or not hmac.compare_digest(data['token'],self.server.token):
                    return self.send(403,{'error':'Invalid launch token'})
                return self.send(200,{'ok':True},headers={'Set-Cookie':'warroom='+self.server.token+'; HttpOnly; SameSite=Strict; Path=/'})
            if not self.authenticated():return self.send(401,{'error':'Launch link required'})
            control=self.server.controller
            if path=='/api/probe':
                with self.server.probe_lock:
                    if not self.server.probing:
                        self.server.probing=True;threading.Thread(target=self.server.probe,daemon=True).start()
                return self.send(202,{'ok':True})
            if path=='/api/run':
                ident=control.create(data.get('prompt'),data.get('workspace',''),data.get('mode','auto'),data.get('tools',True))
                return self.send(202,{'id':ident})
            if path=='/api/resume':control.start(data.get('id'));return self.send(202,{'ok':True})
            if path=='/api/pause':control.cancel(data.get('id'));return self.send(200,{'ok':True})
            if path=='/api/review':
                if not isinstance(data.get('approved'),bool):raise ValueError('Approval must be true or false')
                control.review(data.get('id'),data.get('pending_id'),data['approved']);return self.send(202,{'ok':True})
            if path=='/api/finetune/validate':
                result=control.finetune_validate(data.get('data_path'));return self.send(200,result)
            if path=='/api/finetune/omlx':
                result=control.finetune_omlx(data.get('model'),data.get('data_path'),
                    data.get('epochs',1),data.get('batch_size',1));return self.send(202,result)
            if path=='/api/finetune/queue':
                import uuid
                job_id=uuid.uuid4().hex
                result=control.finetune_scheduler.queue_training(job_id,data.get('model'),data.get('data_path'),
                    data.get('epochs',1),data.get('batch_size',1));return self.send(202,result)
            if path=='/api/finetune/list':
                result=control.finetune_list();return self.send(200,result)
            if path=='/api/finetune/remove':
                result=control.finetune_remove(data.get('adapter_name'));return self.send(200,result)
            if path=='/api/finetune/generate':
                result=control.generate_training_data(data.get('folder_path'),data.get('max_files',20));return self.send(202,result)
            if path=='/api/finetune/train-inbox':
                result=control.train_from_inbox(data.get('epochs',3),data.get('batch_size',1));return self.send(202,result)
            return self.send(404,{'error':'Not found'})
        except (ValueError,TypeError,KeyError) as exc:self.send(400,{'error':str(exc)})
        except Exception:self.send(500,{'error':'Local operation failed. Your task remains saved.'})

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def probe(self):
        try:self.controller.probe()
        finally:self.probing=False

def main():
    parser=argparse.ArgumentParser(description='THE WAR ROOM — local coding controller')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    docs=Path.home()/'Documents'; state=docs/'.war-room-state'; state.mkdir(exist_ok=True,mode=0o700)
    # File lock prevents two controllers replaying the same durable jobs.
    import fcntl
    lock=(state/'server.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('THE WAR ROOM is already running. Use its existing browser window.')
    token_file=state/'browser-token'
    if token_file.exists():token=token_file.read_text().strip()
    else:
        token=secrets.token_urlsafe(32)
        fd=os.open(token_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as output:output.write(token)
    server=Server(('127.0.0.1',args.port),Handler)
    server.token=token;server.controller=Controller(state);server.docs=docs
    port=server.server_address[1]
    server.hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
    server.origins={'http://'+host for host in server.hosts}
    server.probe_lock=threading.Lock();server.probing=True
    threading.Thread(target=server.probe,daemon=True).start()
    url=f'http://127.0.0.1:{port}/#token={token}'
    (state/'launch-url').write_text(url);os.chmod(state/'launch-url',0o600)
    print(f'THE WAR ROOM is running at http://127.0.0.1:{port}',flush=True)
    print(f'Workspace: {docs}',flush=True)
    print('Use Launch THE WAR ROOM.command to open the authenticated browser. Ctrl+C stops the server.',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
