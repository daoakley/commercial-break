"""Linux integration test: real child exit, stale loop, healthy/off heartbeat.
Run in a disposable Linux container; never targets a TV or Samsung.
"""
import json, os, signal, subprocess, tempfile, time
from pathlib import Path
script=Path(__file__).resolve().parents[1]/'scripts/engine-supervisor.sh'
def run(mode, stale=False):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); state=root/'state'; state.mkdir()
        fake=root/'fake-dotnet';fake.write_text('''#!/usr/bin/env python3
import os,time
from pathlib import Path
s=Path(os.environ['CB_STATE'])
mode=os.environ['FAKE_MODE']
if mode=='exit': raise SystemExit(17)
while True:
 if mode=='healthy':
  (s/'engine-health.tmp').write_text(str(os.getpid())+' '+Path('/proc/uptime').read_text().split('.')[0])
  (s/'engine-health.tmp').replace(s/'engine-health')
 time.sleep(.1)
''');fake.chmod(0o700)
        if stale: (state/'engine-health').write_text('123 99999999')
        env=dict(os.environ,CB_HOME=str(root),CB_STATE=str(state),CB_DOTNET=str(fake),CB_STALL_SECONDS='1',CB_POLL_SECONDS='.1',FAKE_MODE=mode)
        p=subprocess.Popen(['sh',str(script)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        try:
            if mode=='healthy':
                time.sleep(3.5);assert p.poll() is None,'healthy loop restarted'
                duplicate=subprocess.run(['sh',str(script)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
                assert duplicate.returncode==0,'duplicate supervisor not rejected'
                child=json.loads((state/'supervisor.json').read_text())['enginePid']
                os.kill(child,signal.SIGKILL)
            p.wait(timeout=7)
            events=[json.loads(l) for l in (root/'diagnostics/recovery.jsonl').read_text().splitlines()]
            assert p.returncode==1
            assert events[-1]['kind']=='exit'
            if mode=='exit': assert events[-1]['code']==17
            if mode=='stall': assert any(e['kind']=='stalled' for e in events)
            if mode=='healthy': assert not any(e['kind']=='stalled' for e in events) and events[-1]['code']==137
            assert (root/'diagnostics').stat().st_mode&0o777==0o700
            if mode=='exit':
                began=time.monotonic()
                again=subprocess.run(['sh',str(script)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)
                assert again.returncode==1 and time.monotonic()-began>=4
                events=[json.loads(l) for l in (root/'diagnostics/recovery.jsonl').read_text().splitlines()]
                assert any(e['kind']=='cooldown' and e['code']==4 for e in events)
                assert json.loads((state/'supervisor.json').read_text())['starts']==2
            print('PASS',mode,'stale heartbeat' if stale else '')
        finally:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
run('exit');run('stall',True);run('healthy')
