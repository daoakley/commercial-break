"""Model arithmetic, bounded input, and frame conversion; no TV/network required."""
import copy,json,os,subprocess,tempfile
from pathlib import Path
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
root=Path(__file__).resolve().parents[1]
dotnet=os.environ.get('LAYOUT_DOTNET','dotnet');env=dict(os.environ,DOTNET_ROLL_FORWARD='Major')
with tempfile.TemporaryDirectory() as directory:
    d=Path(directory);build=d/'build'
    subprocess.run([dotnet,'build',str(root/'tests/layout-harness/LayoutHarness.csproj'),'-c','Release','-o',str(build),'-p:UseSharedCompilation=false'],check=True,capture_output=True)
    def run(*args,ok=True):
        r=subprocess.run([dotnet,str(build/'LayoutHarness.dll'),*map(str,args)],env=env,capture_output=True,text=True)
        assert (r.returncode==0)==ok,r.stderr
        return r.stdout.strip()
    rng=np.random.default_rng(4);x=rng.normal(size=(49,141)).astype(np.float32);y=np.array([1]*7+[0]*42)
    p=make_pipeline(StandardScaler(),SVC(C=1,gamma='scale',class_weight='balanced')).fit(x,y);sc,sv=p[0],p[1]
    model=dict(version='ad-layout-141-v1',modelId='unit-test',threshold=.5,mean=sc.mean_.tolist(),scale=sc.scale_.tolist(),vectors=sv.support_vectors_.tolist(),dual=sv.dual_coef_[0].tolist(),intercept=float(sv.intercept_[0]),gamma=float(sv._gamma),kernels=[[0.0]*121 for _ in range(8)])
    modelpath=d/'model.json';featurepath=d/'feature.json';modelpath.write_text(json.dumps(model))
    for f in [*x[:4],rng.normal(size=141).astype(np.float32)]:
        featurepath.write_text(json.dumps(f.tolist()));actual=float(run('--score',modelpath,featurepath));expected=p.decision_function(f[None])[0];assert abs(actual-expected)<1e-6,(actual,expected)
    for field,value in [('threshold',0),('gamma',-1),('vectors',[[0]*140]),('scale',[0]*141),('version','wrong'),('kernels',[]),('dual',[])]:
        m=copy.deepcopy(model);m[field]=value;modelpath.write_text(json.dumps(m));run('--score',modelpath,featurepath,ok=False)
    for w,h,pitch in [(720,576,736),(2,2,4)]:
        yy=rng.integers(0,256,(h,pitch),dtype=np.uint8);uv=rng.integers(0,256,(h//2,pitch),dtype=np.uint8)
        source=d/'sample.nv12';dest=d/'rgb.bin';source.write_bytes(yy.tobytes()+uv.tobytes());run('--nv12',source,dest,w,h,pitch)
        sy=np.arange(270)*h//270;sx=np.arange(480)*w//480;l=yy[sy[:,None],sx[None,:]].astype(float);u=uv[(sy//2)[:,None],(sx//2*2)[None,:]].astype(float)-128;v=uv[(sy//2)[:,None],(sx//2*2+1)[None,:]].astype(float)-128
        expected=np.stack([l+1.402*v,l-.344*u-.714*v,l+1.772*u],axis=2).clip(0,255).astype(np.uint8)
        assert dest.read_bytes()==expected.tobytes()
print('5 model parity, 7 malformed-model, and 2 NV12 parity cases passed')
