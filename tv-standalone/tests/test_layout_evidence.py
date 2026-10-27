"""Only a fresh, enabled, uncovered result from the fixed pilot can block."""
import copy,json,os,subprocess,sys,tempfile
from pathlib import Path
base=dict(evidence=dict(at=1000,score=.617,hit=True,keepCard=False,threshold=.5,
    detector='ad-layout-141-v1',modelId='forward-49-20261027',elapsedMs=60),
    started=1000,now=1100,keepCard=False,enabled=True)
cases=[('fresh',base,'ad')]
def case(name,field,value,parent='evidence'):
    row=copy.deepcopy(base);(row[parent] if parent else row)[field]=value
    cases.append((name,row,'uncertain'))
case('switch off','enabled',False,None)
case('old capture','at',999);case('future','at',1101)
case('late decision','now',6001,None);case('below margin','score',.4999)
case('explicit negative','hit',False);case('card pixels','keepCard',True)
case('card capture','keepCard',True,None);case('other model','modelId','refit')
case('other detector','detector','other');case('changed margin','threshold',0)
case('slow worker','elapsedMs',1501);case('invalid timing','elapsedMs',-1)
case('missing result','evidence',{},None)
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'cases.json';path.write_text(json.dumps([r for _,r,_ in cases]))
    r=subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'dotnet',str(root/'engine/bin/Release/netcoreapp3.1/CommercialBlock.dll'),'--replay-layout',str(path)],check=True,capture_output=True,text=True,env=dict(os.environ,DOTNET_ROLL_FORWARD='Major'))
    actual=r.stdout.splitlines();assert len(actual)==len(cases)
    for (name,_,expected),got in zip(cases,actual):assert got==expected,(name,got)
print(f'{len(cases)} experimental evidence safety tests passed')
