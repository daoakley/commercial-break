"""YouTube control evidence must be current, app-scoped and geometrically specific."""
import copy,json,os,subprocess,sys,tempfile
from pathlib import Path
base=dict(evidence=dict(at=1000,keepCard=False,detector='youtube-ad-controls-v2',controlKind='skip-in',elapsedMs=8,hit=True,state='countdown',skipReady=False,sponsoredScore=.99,countdownScore=.99,skipScore=0,yellowPixels=20),started=1000,now=1100,keepCard=False,app='com.samsung.tv.cobalt-yt')
cases=[('countdown',base,'ad')]
def case(name,field,value,parent='evidence',expected='uncertain'):
 r=copy.deepcopy(base);(r[parent] if parent else r)[field]=value;cases.append((name,r,expected))
case('YouTube TV excludes this rule','app','com.samsung.tv.cobalt-yttv',None)
case('unknown app','app','',None)
case('stale file','at',999);case('future','at',1101);case('too late','now',6001,None)
case('card invocation','keepCard',True,None);case('card result','keepCard',True)
case('label is optional','sponsoredScore',0,expected='ad');case('circle without Skip in','countdownScore',.89)
case('no yellow countdown','yellowPixels',4);case('wrong detector','detector','unvalidated')
case('explicit miss','hit',False);case('slow processing','elapsedMs',501)
case('bad score','countdownScore',2);case('bad timing','elapsedMs',-1)
case('missing result','evidence',{},None)
r=copy.deepcopy(base);r['evidence'].update(state='skip',controlKind='skip',skipReady=True,skipScore=.99,countdownScore=0,yellowPixels=0);cases.append(('focused Skip',r,'ad'))
for k,v in [('skipReady',False),('skipScore',.94),('controlKind','circle')]:
 q=copy.deepcopy(r);q['evidence'][k]=v;cases.append(('invalid skip '+k,q,'uncertain'))
r=copy.deepcopy(base);r['evidence'].update(controlKind='circle',sponsoredScore=0,countdownScore=0,yellowPixels=20,circleDigitPixels=10,circleRingPixels=8,circleRows=5,circleColumns=4,circleSectors=2,circleNoise=0);cases.append(('circle without text or label',r,'ad'))
for k,v in [('circleDigitPixels',4),('circleRingPixels',3),('circleRows',3),('circleColumns',9),('circleSectors',1),('circleNoise',3),('circleNoise',-1),('circleDigitPixels',46)]:
 q=copy.deepcopy(r);q['evidence'][k]=v;cases.append(('invalid circle '+k,q,'uncertain'))
q=copy.deepcopy(r);q['evidence']['detector']='youtube-ad-controls-v1';cases.append(('old protocol rejected',q,'uncertain'))
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'cases.json';p.write_text(json.dumps([r for _,r,_ in cases]))
 out=subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'dotnet',str(root/'engine/bin/Release/netcoreapp3.1/CommercialBlock.dll'),'--replay-youtube',str(p)],check=True,capture_output=True,text=True,env=dict(os.environ,DOTNET_ROLL_FORWARD='Major')).stdout.splitlines()
 assert len(out)==len(cases)
 for (name,_,expected),actual in zip(cases,out):assert actual==expected,(name,actual)
print(f'{len(cases)} YouTube evidence safety checks passed')
