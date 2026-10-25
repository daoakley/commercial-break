"""Bounded, read-only TV cover status. Never changes playback or mute."""
import hmac, json, os, secrets, shlex, subprocess, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
BASE=Path(__file__).resolve().parents[2]
TV=os.environ.get('TV_HOST', '')
MAC=os.environ.get('OBSERVER_BIND_IP', '127.0.0.1')
REMOTE='/home/owner/share/tmp/sdk_tools/cb-study-curl.conf'

class TVObserver:
    def __init__(self, study, port=8793):
        self.study=study; self.lock=threading.Lock(); self.launched=set(); self.samples=[]
        self.path=study.directory/'cover-samples.jsonl'
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                try:self.samples.append(json.loads(line))
                except ValueError:pass
        self.token=secrets.token_urlsafe(32)
        self.config=study.directory/'tv-observer-curl.conf'
        self.config.write_text('url = "http://'+MAC+':'+str(port)+'/sample"\nheader = "Authorization: Bearer '+self.token+'"\nheader = "Content-Type: application/json"\n')
        self.config.chmod(0o600)
        self.status='Ready for next window'
        owner=self
        class Receiver(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.path!='/sample' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+owner.token):
                    self.send_response(403);self.end_headers();return
                answer=b'STOP'
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<2048:raise ValueError()
                    data=json.loads(self.rfile.read(size))
                    with owner.study.lock:
                        owner.study.expire();active=owner.study.active
                        if not active: owner.status='Observer ended with window'
                        elif data.get('session_id')!=active['session_id']: owner.status='Ignoring stale window sample'
                        if active and data.get('session_id')==active['session_id']:
                            row=dict(session_id=active['session_id'],received_unix_ms=round(time.time()*1000),tv_unix_ms=int(data['tv_unix_seconds'])*1000,cover_active=data.get('cover_active') is True,paused=data.get('paused') is True,heartbeat_age_seconds=int(data.get('heartbeat_age_seconds',-1)))
                            with owner.lock:
                                with owner.path.open('a') as f:
                                    owner.path.chmod(0o600);f.write(json.dumps(row)+'\n')
                                owner.samples.append(row);owner.status='Receiving TV cover state'
                            answer=b'OK'
                except (ValueError,KeyError,TypeError,OSError) as error:
                    owner.status='Sample rejected: '+type(error).__name__
                    (owner.study.directory/'observer-error.txt').write_text(type(error).__name__+': '+str(error)[:200])
                self.send_response(200);self.send_header('Content-Length',str(len(answer)));self.end_headers();self.wfile.write(answer)
        self.server=ThreadingHTTPServer((MAC,port),Receiver)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def snapshot(self,sid):
        with self.lock:return [s for s in self.samples if s['session_id']==sid],self.status
    def launch(self,sid):
        if sid in self.launched:return
        self.launched.add(sid)
        threading.Thread(target=self._launch,args=(sid,),daemon=True).start()
    def _launch(self,sid):
        self.status='Connecting read-only TV observer'
        sdb=os.environ.get('SDB', 'sdb')
        root=os.environ.get('TVROOT', 'samsung-tv-root')
        try:
            result=subprocess.run([str(sdb),'-s',TV+':26101','push',str(self.config),REMOTE],capture_output=True,timeout=20)
            if result.returncode:raise RuntimeError()
            script=(Path(__file__).parent/'tv-status.sh').read_text().replace('__SID__',sid).replace('__CONFIG__',shlex.quote(REMOTE))
            command='chmod 600 '+shlex.quote(REMOTE)+'\nnohup /bin/sh -c '+shlex.quote(script)+' >/dev/null 2>&1 </dev/null &\necho observer_started\n'
            result=subprocess.run([str(root),'--sdb',str(sdb),'-o','json','archive-root','root',TV,'--command',command,'--command-timeout','10'],capture_output=True,timeout=75)
            if result.returncode and self.status!='Receiving TV cover state':raise RuntimeError()
        except (OSError,subprocess.TimeoutExpired,RuntimeError):
            if self.status!='Receiving TV cover state':self.status='TV status unavailable; labels still work'
