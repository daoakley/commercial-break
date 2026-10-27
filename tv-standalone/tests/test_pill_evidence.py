"""Local evidence must be fresh, explicit, and from an uncovered capture."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
base = dict(evidence=dict(at=1000, score=600, hit=True, keepCard=False,
                          threshold=300, detector='youtube-tv-sponsored-v1'),
            started=1000, now=1100, keepCard=False)
cases=[('fresh',base,'ad')]
def case(name, field, value, parent='evidence'):
    row=copy.deepcopy(base)
    (row[parent] if parent else row)[field]=value
    cases.append((name,row,'uncertain'))
case('old file','at',999)
case('future','at',1101)
case('delayed result','now',6001,None)
case('below threshold','score',299.99)
case('explicit miss','hit',False)
case('covered capture','keepCard',True)
case('covered invocation','keepCard',True,None)
case('wrong template','detector','other')
case('altered threshold','threshold',100)
case('malformed','evidence',{},None)
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'cases.json';path.write_text(json.dumps([row for _,row,_ in cases]))
    result=subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'dotnet',
        str(root/'engine/bin/Release/netcoreapp3.1/CommercialBlock.dll'), '--replay-pill',str(path)],
        check=True,capture_output=True,text=True,env=dict(os.environ,DOTNET_ROLL_FORWARD='Major'))
    actual=result.stdout.splitlines()
    assert len(actual)==len(cases)
    for (name,_,expected),observed in zip(cases,actual): assert observed==expected,(name,observed)
print(f'{len(cases)} local evidence safety tests passed')
