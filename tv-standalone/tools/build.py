#!/usr/bin/env python3
"""Build private TV deployment files. Does not connect to or modify a TV."""
import argparse,hashlib,ipaddress,json,os,re,secrets,shutil,struct,subprocess,tarfile,zlib
from pathlib import Path
from widget_signer import sign_wgt
ROOT=Path(__file__).resolve().parents[1]
LIB_SHA='fdd3d6f58d2fc73fed6c07bc9d431c86ac911f34930b68071a65a141ab55970d'

def validate_device(d):
    if not isinstance(d,dict):raise ValueError('device configuration must be an object')
    for group,keys in [('identity',['psid','vdvendorcode','modelID','sourceInfo']),('parameters',['zipcode','firmware','modelID'])]:
        for key in keys:
            v=d.get(group,{}).get(key)
            if not isinstance(v,str) or not v.strip() or 'REPLACE' in v:raise ValueError('Missing device field: '+group+'.'+key)
    int(d['identity']['sourceInfo'])
    if d['parameters'].get('api')!=2:raise ValueError('Parameter request api must be 2')
    if d.get('controlToken') and not re.fullmatch(r'[a-f0-9]{64}',d['controlToken']):raise ValueError('controlToken must be 32 random bytes encoded as 64 lowercase hex characters')
    return d

def icon(dest):
    # Original geometric mark, generated without external assets or fonts.
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    rows=[]
    for y in range(117):
        row=bytearray()
        for x in range(117):
            foreground=(24<=x<=92 and (28<=y<=39 or 77<=y<=88)) or (24<=x<=36 and 28<=y<=88) or (72<=x<=92 and 52<=y<=63)
            row.extend((213,226,231) if foreground else (18,30,38))
        rows.append(b'\0'+row)
    dest.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',117,117,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))

def build_project(dotnet,project,target,stem):
    subprocess.run([dotnet,'build',str(project),'-c','Release','-p:UseAppHost=false','-p:UseSharedCompilation=false','--nologo'],check=True)
    b=project.parent/'bin/Release/netcoreapp3.1'
    for ext in ['.dll','.deps.json','.runtimeconfig.json']:shutil.copy2(b/(stem+ext),target/(stem+ext))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device-config',type=Path,required=True)
    p.add_argument('--capture-library',type=Path,required=True,help="Unmodified libtzcapturec.so from your TV")
    p.add_argument('--cert-dir',type=Path,required=True,help='author.p12, distributor.p12, password.txt (same export password)')
    p.add_argument('--restore-host',required=True,help='Developer Host PC IP to restore if recovery is disabled')
    p.add_argument('--dotnet',default='dotnet')
    p.add_argument('--out',type=Path,default=Path('private/tv-build'))
    a=p.parse_args();os.umask(0o077)
    ipaddress.IPv4Address(a.restore_host)
    if a.restore_host=='127.0.0.1':p.error('restore-host must be your computer address, not the TV-local address')
    d=validate_device(json.loads(a.device_config.read_text()))
    data=a.capture_library.read_bytes()
    if hashlib.sha256(data).hexdigest()!=LIB_SHA:p.error('Capture library differs from the tested firmware; refusing to patch')
    old=b'/usr/bin/tzcapturesample\0';new=b'/usr/bin/dotnet\0'
    if data.count(old)!=1:p.error('Unexpected capture allowlist structure')
    if a.out.exists():p.error('Output directory already exists; use a new path to preserve keys and backups')
    for n in ['author.p12','distributor.p12','password.txt']:
        if not (a.cert_dir/n).is_file():p.error('Missing certificate input: '+n)
    a.out.mkdir(parents=True,mode=0o700);engine=a.out/'engine';engine.mkdir()
    controller=a.out/'controller';shutil.copytree(ROOT/'app',controller)
    recovery=a.out/'recovery';recovery.mkdir();(recovery/'service').mkdir();(recovery/'payload').mkdir()
    for f in ['config.xml','index.html','VETRO-LICENSE']:shutil.copy2(ROOT/'recovery'/f,recovery/f)
    for f in (ROOT/'recovery/service').glob('*.js'):shutil.copy2(f,recovery/'service'/f.name)
    for project,stem in [('engine/CommercialBlock.csproj','CommercialBlock'),('engine/capture/AcrFrameProbe.csproj','AcrFrameProbe'),('engine/overlay/CommercialOverlayProbe.csproj','CommercialOverlayProbe'),('engine/navigation/NavigationObserver.csproj','NavigationObserver')]:build_project(a.dotnet,ROOT/project,engine,stem)
    for stem in ['SamsungTvArchiveRoot','SamsungTvRootAgent']:build_project(a.dotnet,ROOT/'recovery/payload-source'/(stem+'.csproj'),recovery/'payload',stem)
    shutil.copytree(ROOT/'engine/themes',engine/'themes');shutil.copy2(ROOT/'engine/scene.json',engine/'scene.json')
    for name in ['watchdog.sh','engine-supervisor.sh','release-owned.sh','commercial-break-engine.service']:shutil.copy2(ROOT/'scripts'/name,engine/name)
    existing_token=bool(d.get('controlToken'))
    d.setdefault('controlToken',secrets.token_hex(32));(engine/'device.json').write_text(a.device_config.read_text() if existing_token else json.dumps(d,indent=2)+'\n')
    (engine/'control.curl').write_text('header = "Authorization: Bearer '+d['controlToken']+'"\n')
    (engine/'libtzcapturec-probe.so').write_bytes(data.replace(old,new.ljust(len(old),b'\0'),1))
    (controller/'device.js').write_text('window.COMMERCIAL_BLOCK_TOKEN='+json.dumps(d['controlToken'])+';\n')
    token=secrets.token_hex(32);(a.out/'recovery-token').write_text(token+'\n')
    (recovery/'service/private-config.json').write_text(json.dumps({'token':token,'restoreHost':a.restore_host})+'\n')
    for app,name in [(controller,'commercial-break.wgt'),(recovery,'commercial-break-recovery.wgt')]:
        icon(app/'icon.png');sign_wgt(app,a.out/name,a.cert_dir)
    with tarfile.open(a.out/'engine.tar.gz','w:gz') as tar:
        for f in sorted(engine.rglob('*')):
            if f.is_file():tar.add(f,arcname=str(f.relative_to(engine)),recursive=False)
    shutil.copy2(ROOT/'tools/install-engine.sh',a.out/'install-engine.sh')
    print('Private deployment bundle written to '+str(a.out)+'. No TV changes made. Keep all bundle files private.')

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,json.JSONDecodeError) as e:raise SystemExit(str(e))
