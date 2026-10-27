#!/usr/bin/env python3
"""Run one explicit TV command file through the existing authorized root tool.

Raw diagnostics belong in a private work directory, never in Git. Does not
discover devices, reconnect, reboot, or install anything by itself.
"""
import argparse,json,subprocess
from pathlib import Path

def fields(value,key):
    if isinstance(value,dict):
        for name,child in value.items():
            if name==key and isinstance(child,str):yield child
            elif isinstance(child,(dict,list)):yield from fields(child,key)
    elif isinstance(value,list):
        for child in value:yield from fields(child,key)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['sdb','root-tool','host','command-file','output']:p.add_argument('--'+name,required=True)
    p.add_argument('--timeout',type=int,default=40)
    a=p.parse_args()
    result=subprocess.run([a.root_tool,'--sdb',a.sdb,'-o','json','archive-root','root',a.host,
        '--command',Path(a.command_file).read_text(),'--command-timeout',str(a.timeout)],capture_output=True,text=True,timeout=a.timeout+60)
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(result.stdout);dest.chmod(0o600)
    try:
        payload=json.loads(result.stdout)
    except json.JSONDecodeError:
        print('TV transport returned no JSON:',result.stderr[-600:])
        raise SystemExit(result.returncode or 1)
    for s in fields(payload,'stdout'):print(s)
    for s in fields(payload,'stderr'):
        if s.strip():print('TV stderr:',s)
    if result.returncode:
        print('TV command/transport exit:',result.returncode)
        raise SystemExit(result.returncode)

if __name__=='__main__':main()
