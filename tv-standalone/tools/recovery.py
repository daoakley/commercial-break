#!/usr/bin/env python3
"""Authenticated fixed recovery controls; never prints tokens or sends arbitrary commands."""
import argparse,json,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',required=True);p.add_argument('--token-file',type=Path,required=True);p.add_argument('action',choices=['status','arm','disarm','restore-developer-host']);a=p.parse_args()
if any(c not in '0123456789.' for c in a.host):p.error('Use the TV IPv4 address')
r=urllib.request.Request('http://'+a.host+':18765/'+a.action,method='GET' if a.action=='status' else 'POST',headers={'Authorization':'Bearer '+a.token_file.read_text().strip()})
try:
 with urllib.request.urlopen(r,timeout=25) as response:d=json.load(response)
except (urllib.error.URLError,TimeoutError) as e:raise SystemExit('Recovery endpoint unavailable: '+str(e))
if a.action!='status':print(json.dumps(d,indent=2))
else:
 s=d['state'];agent=d['platform']['agent'];e=s.get('engine');engine=None
 if e:
  try:engine=json.loads(e['report'].splitlines()[-1])
  except (ValueError,KeyError):pass
 print(json.dumps({'version':s['version'],'bootId':s['bootId'],'armed':s['armed'],'servicePid':s['pid'],'serviceStartedAt':s['startedAt'],'rootConnected':agent.get('connected',False),'rootUid':agent.get('uid'),'engine':None if not engine else {k:engine.get(k) for k in ['health','enabled','queries','matches','localChecks','message','lastError']},'events':s['events']},indent=2))
