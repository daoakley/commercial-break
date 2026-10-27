using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;

// Experimental, entirely TV-local spatial classifier. Uses the TV's existing
// OpenCV 4.5 libraries; no downloaded native runtime and no network calls.
internal static class LayoutDetector
{
    internal const string Version = "ad-layout-141-v1";
    internal const double Threshold = 0.5; // SVM margin, NOT a probability.
    const string Core = "/usr/lib/libopencv_core.so.4.5";
    const string Img = "/usr/lib/libopencv_imgproc.so.4.5";
    [StructLayout(LayoutKind.Sequential)] struct Point { public int x, y; public Point(int a,int b){x=a;y=b;} }
    [DllImport(Core, CallingConvention=CallingConvention.Cdecl)] static extern IntPtr cvCreateMat(int rows,int cols,int type);
    [DllImport(Core, CallingConvention=CallingConvention.Cdecl)] static extern void cvReleaseMat(ref IntPtr mat);
    [DllImport(Core, CallingConvention=CallingConvention.Cdecl)] static extern void cvGetRawData(IntPtr mat,out IntPtr data,out int step,IntPtr size);
    [DllImport(Core, CallingConvention=CallingConvention.Cdecl)] static extern void cvSetNumThreads(int count);
    [DllImport(Img, CallingConvention=CallingConvention.Cdecl)] static extern void cvResize(IntPtr src,IntPtr dst,int interpolation);
    [DllImport(Img, CallingConvention=CallingConvention.Cdecl)] static extern void cvCvtColor(IntPtr src,IntPtr dst,int code);
    [DllImport(Img, CallingConvention=CallingConvention.Cdecl)] static extern void cvCanny(IntPtr src,IntPtr dst,double lo,double hi,int aperture);
    [DllImport(Img, CallingConvention=CallingConvention.Cdecl)] static extern void cvFilter2D(IntPtr src,IntPtr dst,IntPtr kernel,Point anchor);
    sealed class Mat : IDisposable {
        public IntPtr Handle,Data; public int Step,Rows,Cols,Bytes;
        public Mat(int rows,int cols,int type,int bytes){Rows=rows;Cols=cols;Bytes=bytes;Handle=cvCreateMat(rows,cols,type);if(Handle==IntPtr.Zero)throw new IOException("OpenCV allocation");cvGetRawData(Handle,out Data,out Step,IntPtr.Zero);if(Data==IntPtr.Zero||Step<cols*bytes)throw new IOException("OpenCV stride");}
        public void Put(byte[] v){for(int r=0;r<Rows;r++)Marshal.Copy(v,r*Cols*Bytes,IntPtr.Add(Data,r*Step),Cols*Bytes);}
        public void Put(float[] v){for(int r=0;r<Rows;r++)Marshal.Copy(v,r*Cols,IntPtr.Add(Data,r*Step),Cols);}
        public byte[] Read(){var v=new byte[Rows*Cols*Bytes];for(int r=0;r<Rows;r++)Marshal.Copy(IntPtr.Add(Data,r*Step),v,r*Cols*Bytes,Cols*Bytes);return v;}
        public float[] Floats(){var v=new float[Rows*Cols];for(int r=0;r<Rows;r++)Marshal.Copy(IntPtr.Add(Data,r*Step),v,r*Cols,Cols);return v;}
        public void Dispose(){if(Handle!=IntPtr.Zero)cvReleaseMat(ref Handle);}
    }
    internal sealed class Model {
        public string version {get;set;} public string modelId {get;set;}
        public double threshold {get;set;} public double[] mean {get;set;} public double[] scale {get;set;}
        public double[][] vectors {get;set;} public double[] dual {get;set;}
        public double intercept {get;set;} public double gamma {get;set;} public float[][] kernels {get;set;}
        static bool Good(double x)=>!double.IsNaN(x)&&!double.IsInfinity(x);
        public static Model Load(string path){
            if(new FileInfo(path).Length>1024*1024)throw new IOException("layout model too large");
            var m=JsonSerializer.Deserialize<Model>(File.ReadAllText(path));
            if(m==null||m.version!=Version||m.threshold!=Threshold||string.IsNullOrEmpty(m.modelId)||m.modelId.Length>64||m.mean?.Length!=141||m.scale?.Length!=141||m.vectors==null||m.vectors.Length<1||m.vectors.Length>128||m.dual?.Length!=m.vectors.Length||m.kernels?.Length!=8||!Good(m.gamma)||m.gamma<=0||!Good(m.intercept)||m.mean.Any(v=>!Good(v))||m.scale.Any(v=>!Good(v)||v<=0)||m.dual.Any(v=>!Good(v))||m.vectors.Any(v=>v?.Length!=141||v.Any(a=>!Good(a)))||m.kernels.Any(k=>k?.Length!=121||k.Any(a=>!Good(a))))throw new IOException("invalid layout model");
            return m;
        }
        public double Score(float[] features){
            if(features.Length!=141||features.Any(v=>!Good(v)))throw new IOException("invalid layout features");
            var scaled=new double[141];for(int j=0;j<141;j++){
                // StandardScaler on float32 input rounds each in-place operation.
                float centered=(float)(features[j]-mean[j]);scaled[j]=(float)(centered/scale[j]);
            }
            double score=intercept;for(int i=0;i<vectors.Length;i++){double distance=0;for(int j=0;j<141;j++){double d=scaled[j]-vectors[i][j];distance+=d*d;}score+=dual[i]*Math.Exp(-gamma*distance);}
            if(!Good(score))throw new IOException("invalid layout score");return score;
        }
    }
    internal static byte[] RgbNv12(IntPtr y,IntPtr c,int width,int height,int pitch,int planeBytes){
        if(width<=0||height<=0||pitch<width||pitch%2!=0||(long)pitch*height>planeBytes||width>4096||height>2304)throw new ArgumentException("capture plane bounds");
        var rgb=new byte[480*270*3];var yr=new byte[pitch];var cr=new byte[pitch];int lastY=-1,lastC=-1;
        for(int oy=0;oy<270;oy++){int sy=oy*height/270;if(sy!=lastY){Marshal.Copy(IntPtr.Add(y,sy*pitch),yr,0,pitch);lastY=sy;}int cy=sy/2;if(cy!=lastC){Marshal.Copy(IntPtr.Add(c,cy*pitch),cr,0,pitch);lastC=cy;}
            for(int ox=0;ox<480;ox++){int sx=ox*width/480;double l=yr[sx],u=cr[sx/2*2]-128,v=cr[sx/2*2+1]-128;int o=(oy*480+ox)*3;rgb[o]=Clamp(l+1.402*v);rgb[o+1]=Clamp(l-.344*u-.714*v);rgb[o+2]=Clamp(l+1.772*u);}}
        return rgb;
    }
    static byte Clamp(double v)=>v<0?(byte)0:v>255?(byte)255:(byte)v;
    static int Reflect(int p,int n)=>p<0?-p:p>=n?2*n-2-p:p;
    internal static float[] Features(byte[] input,Model model){
        if(input.Length!=480*270*3)throw new ArgumentException("requires 480x270 RGB");
        cvSetNumThreads(1);var rgb=(byte[])input.Clone();
        for(int ch=0;ch<3;ch++){var samples=new byte[880];int n=0;for(int y=44;y<55;y++)for(int x=12;x<92;x++)samples[n++]=rgb[(y*480+x)*3+ch];Array.Sort(samples);byte median=(byte)((samples[439]+samples[440])/2);for(int y=17;y<44;y++)for(int x=12;x<92;x++)rgb[(y*480+x)*3+ch]=median;}
        using(var src=new Mat(270,480,16,3))using(var small=new Mat(96,160,16,3))using(var luvMat=new Mat(96,160,16,3))using(var grayMat=new Mat(96,160,0,1))using(var edgeMat=new Mat(96,160,0,1)){
            src.Put(rgb);cvResize(src.Handle,small.Handle,3);cvCvtColor(small.Handle,luvMat.Handle,51);cvCvtColor(small.Handle,grayMat.Handle,7);cvCanny(grayMat.Handle,edgeMat.Handle,50,150,3);
            byte[] luv=luvMat.Read(),gray=grayMat.Read(),edges=edgeMat.Read();var g=Array.ConvertAll(gray,b=>b/255f);var responses=new float[4][];
            // Legacy C filter2D uses replicate borders. Explicit reflect101 padding
            // makes the cropped region match the Python reference's default border.
            using(var padded=new Mat(106,170,5,4))using(var filtered=new Mat(106,170,5,4))using(var kernel=new Mat(11,11,5,4)){
                var pad=new float[106*170];for(int y=0;y<106;y++)for(int x=0;x<170;x++)pad[y*170+x]=g[Reflect(y-5,96)*160+Reflect(x-5,160)];padded.Put(pad);
                for(int k=0;k<4;k++){kernel.Put(model.kernels[k*2]);cvFilter2D(padded.Handle,filtered.Handle,kernel.Handle,new Point(-1,-1));var re=filtered.Floats();kernel.Put(model.kernels[k*2+1]);cvFilter2D(padded.Handle,filtered.Handle,kernel.Handle,new Point(-1,-1));var im=filtered.Floats();var mag=new float[160*96];for(int y=0;y<96;y++)for(int x=0;x<160;x++){int a=(y+5)*170+x+5;mag[y*160+x]=(float)Math.Sqrt((double)re[a]*re[a]+(double)im[a]*im[a]);}responses[k]=mag;}
            }
            var f=new float[141];int o=0;
            for(int top=0;top<96;top+=24)for(int left=0;left<160;left+=40){
                for(int ch=0;ch<3;ch++){var hist=new int[16];for(int y=top;y<top+24;y++)for(int x=left;x<left+40;x++)hist[luv[(y*160+x)*3+ch]/16]++;f[o++]=hist.Max()/960f;}
                int count=0;for(int y=top;y<top+24;y++)for(int x=left;x<left+40;x++)if(edges[y*160+x]>0)count++;f[o++]=count/960f;
                for(int k=0;k<4;k++){double sum=0;for(int y=top;y<top+24;y++)for(int x=left;x<left+40;x++)sum+=responses[k][y*160+x];f[o++]=(float)(sum/960);}
            }
            for(int ch=0;ch<3;ch++){var hist=new int[16];for(int i=0;i<15360;i++)hist[luv[i*3+ch]/16]++;Array.Sort(hist);for(int k=15;k>=13;k--)f[o++]=hist[k]/15360f;}
            var orientation=new int[4];int edgeCount=0;float pi=(float)Math.PI;
            for(int y=0;y<96;y++)for(int x=0;x<160;x++){int i=y*160+x;if(edges[i]==0)continue;int ym=Reflect(y-1,96)*160,yp=Reflect(y+1,96)*160,xm=Reflect(x-1,160),xp=Reflect(x+1,160),row=y*160;
                float dx=(g[ym+xp]-g[ym+xm])+2*(g[row+xp]-g[row+xm])+(g[yp+xp]-g[yp+xm]);
                float dy=(g[yp+xm]+2*g[yp+x]+g[yp+xp])-(g[ym+xm]+2*g[ym+x]+g[ym+xp]);
                float angle=((float)Math.Atan2(dy,dx)+pi)%pi;int bin=Math.Min(3,Math.Max(0,(int)(angle*4/pi)));orientation[bin]++;edgeCount++;}
            foreach(int count in orientation)f[o++]=count/(float)Math.Max(1,edgeCount);
            return f;
        }
    }
    internal static int Worker(int parentPid,string modelPath="/opt/usr/home/owner/commercial-block/layout-model.json",string state="/run/commercial-block"){
        string pending=state+"/layout-frame.bin",processing=state+"/layout-processing.bin",result=state+"/layout-result.json",ready=state+"/layout-ready";
        try {
            File.Delete(ready);File.Delete(processing);
            var model=Model.Load(modelPath);
            // Build native lookup tables and JIT code before asking for real frames.
            model.Score(Features(new byte[480*270*3],model));
            File.WriteAllText(ready,Process.GetCurrentProcess().Id.ToString());
            while(Directory.Exists("/proc/"+parentPid)){
                if(!File.Exists(pending)){System.Threading.Thread.Sleep(10);continue;}
                try {
                    File.Move(pending,processing,true);
                    var timer=Stopwatch.StartNew();
                    if(new FileInfo(processing).Length!=8+480*270*3)throw new IOException("invalid layout frame size");
                    byte[] packet=File.ReadAllBytes(processing);long at=BitConverter.ToInt64(packet,0);
                    // Never process queued frames from an expired capture.
                    long age=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()-at;if(age<0||age>5000)continue;
                    var rgb=new byte[480*270*3];Buffer.BlockCopy(packet,8,rgb,0,rgb.Length);
                    double score=model.Score(Features(rgb,model));
                    File.WriteAllText(result+".tmp",JsonSerializer.Serialize(new {at,score,hit=score>=Threshold,keepCard=false,elapsedMs=timer.Elapsed.TotalMilliseconds,threshold=Threshold,detector=Version,modelId=model.modelId}));
                    File.Move(result+".tmp",result,true);
                }catch(Exception){ /* malformed/expired input cannot become a match */ }
                finally {try{File.Delete(processing);}catch{}}
            }
            return 0;
        }catch(Exception){return 1;}
        finally{try{File.Delete(ready);File.Delete(processing);File.Delete(pending);}catch{}}
    }

}
