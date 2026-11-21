using System;
using System.IO;
using System.Text.Json;
using System.Runtime.InteropServices;
class Program {
 static void Throws(Action run){try{run();}catch(ArgumentException){return;}throw new Exception("Expected invalid geometry to be rejected");}
 static int Main(string[] args){
  if(args.Length==1&&args[0]=="--self-test"){
   Throws(()=>YouTubeAdUi.ScoreRgb(null));Throws(()=>YouTubeAdUi.ScoreRgb(new byte[4]));
   foreach(var g in new[]{new[]{0,270,480},new[]{481,270,482},new[]{480,271,480},new[]{480,270,479},new[]{480,270,int.MaxValue-1},new[]{480,2306,480}})Throws(()=>YouTubeAdUi.ScoreNv12(new IntPtr(1),new IntPtr(1),g[0],g[1],g[2]));
   if(YouTubeAdUi.ScoreRgb(new byte[480*270*3]).hit)throw new Exception("Black frame hit");
   Console.WriteLine("geometry and blank frame guards passed");return 0;
  }
  if(args.Length==1&&args[0]=="--stream"){
   using(var input=Console.OpenStandardInput()){var data=new byte[480*270*3];while(true){int n=0,k;while(n<data.Length&&(k=input.Read(data,n,data.Length-n))>0)n+=k;if(n==0)break;if(n!=data.Length)throw new IOException("Incomplete RGB frame");Console.WriteLine(JsonSerializer.Serialize(YouTubeAdUi.ScoreRgb(data)));}}return 0;
  }
  if(args.Length==5&&args[0]=="--nv12"){
   byte[] bytes=File.ReadAllBytes(args[1]);int w=int.Parse(args[2]),h=int.Parse(args[3]),pitch=int.Parse(args[4]);if((long)pitch*h*3/2!=bytes.Length)throw new ArgumentException("Wrong plane length");IntPtr p=Marshal.AllocHGlobal(bytes.Length);try{Marshal.Copy(bytes,0,p,bytes.Length);Console.WriteLine(JsonSerializer.Serialize(YouTubeAdUi.ScoreNv12(p,IntPtr.Add(p,pitch*h),w,h,pitch)));}finally{Marshal.FreeHGlobal(p);}return 0;
  }
  throw new ArgumentException("--stream, --self-test or --nv12 FILE W H PITCH");
 }
}
