import json, os, subprocess, tempfile, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
apps=['com.samsung.tv.cobalt-yt','com.samsung.tv.cobalt-yttv','',None,'com.samsung.tv.cobalt-yt.fake','Netflix','FrmHome001.Home']
expected=[{'supported':True,'broadcastChecks':False,'localOnly':True,'samsungRecognition':False},{'supported':True,'broadcastChecks':True,'localOnly':False,'samsungRecognition':True}]+[{'supported':False,'broadcastChecks':False,'localOnly':False,'samsungRecognition':False}]*5
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'apps.json';p.write_text(json.dumps(apps))
 r=subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'dotnet',str(root/'engine/bin/Release/netcoreapp3.1/CommercialBlock.dll'),'--replay-apps',str(p)],check=True,capture_output=True,text=True,env=dict(os.environ,DOTNET_ROLL_FORWARD='Major'))
 assert [json.loads(line) for line in r.stdout.splitlines()]==expected,r.stdout
print('7 foreground-app routing cases passed')
