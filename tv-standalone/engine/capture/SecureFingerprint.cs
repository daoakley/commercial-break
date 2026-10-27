using System;
using System.IO;
using System.Diagnostics;
using System.Threading;
using System.Text.Json;
using System.Runtime.InteropServices;
internal static class SecureFingerprint {
 [DllImport("libteec.so",CallingConvention=CallingConvention.Cdecl)] static extern uint TEEC_InitializeContext(IntPtr name,IntPtr context);
 [DllImport("libteec.so",CallingConvention=CallingConvention.Cdecl)] static extern uint TEEC_OpenSession(IntPtr context,IntPtr session,byte[] uuid,uint login,IntPtr data,IntPtr operation,out uint origin);
 [DllImport("libteec.so",CallingConvention=CallingConvention.Cdecl)] static extern void TEEC_CloseSession(IntPtr session);
 [DllImport("libteec.so",CallingConvention=CallingConvention.Cdecl)] static extern void TEEC_FinalizeContext(IntPtr context);
 [DllImport("libteec.so",CallingConvention=CallingConvention.Cdecl)] static extern uint TEEC_AllocateSharedMemory(IntPtr context,IntPtr shared);
 [DllImport("libteec.so",CallingConvention=CallingConvention.Cdecl)] static extern void TEEC_ReleaseSharedMemory(IntPtr shared);
 [DllImport("libteec.so",CallingConvention=CallingConvention.Cdecl)] static extern uint TEEC_InvokeCommand(IntPtr session,uint command,IntPtr operation,out uint origin);
 static IntPtr Zero(int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);return p;}
 static void F(IntPtr p,int at,float v){Marshal.WriteInt32(p,at,BitConverter.SingleToInt32Bits(v));}
 static uint SetParams(IntPtr context,IntPtr session){
  IntPtr shared=Zero(36),op=Zero(60);bool allocated=false;
  try {
   Marshal.WriteInt32(shared,4,136);Marshal.WriteInt32(shared,8,1);
   uint rc=TEEC_AllocateSharedMemory(context,shared);if(rc!=0)return rc;allocated=true;
   IntPtr data=Marshal.ReadIntPtr(shared);for(int i=0;i<136;i++)Marshal.WriteByte(data,i,0);
   F(data,0,1.2f);Marshal.WriteInt32(data,4,4);
   float[] baseRoi={.25f,.25f,.15f,.15f};for(int i=0;i<4;i++)F(data,8+i*4,baseRoi[i]);
   Marshal.WriteInt32(data,40,4);float[] ratios={0,0,1,0,1,.75f,0,.75f};for(int i=0;i<ratios.Length;i++)F(data,44+i*4,ratios[i]);
   F(data,124,.16f);F(data,128,10f);F(data,132,1.2f);
   Marshal.WriteInt32(op,4,0x0d);Marshal.WriteIntPtr(op,8,shared);Marshal.WriteInt32(op,12,136);
   return TEEC_InvokeCommand(session,9,op,out uint origin);
  }finally{if(allocated)TEEC_ReleaseSharedMemory(shared);Marshal.FreeHGlobal(op);Marshal.FreeHGlobal(shared);}
 }
 [DllImport("libcapi-video-capture.so.0",EntryPoint="_ZN12VideoCapture11getInstanceEv",CallingConvention=CallingConvention.Cdecl)] static extern IntPtr VideoInstance();
 [DllImport("libcapi-video-capture.so.0",EntryPoint="_ZN12VideoCapture10lockGlobalENS_15CaptureLockTypeEi",CallingConvention=CallingConvention.Cdecl)] static extern int VideoLock(IntPtr obj,int kind,int scaler);
 [DllImport("libcapi-video-capture.so.0",EntryPoint="_ZN12VideoCapture12unlockGlobalENS_15CaptureLockTypeEi",CallingConvention=CallingConvention.Cdecl)] static extern int VideoUnlock(IntPtr obj,int kind,int scaler);
 [DllImport("libcapi-video-capture.so.0",EntryPoint="_ZN12VideoCapture11getVideoYUVERKNS_11InputParamsERNS_12OutputParamsEi",CallingConvention=CallingConvention.Cdecl)] static extern int VideoYuv(IntPtr obj,IntPtr input,IntPtr output,int scaler);
 static uint CaptureSecure(IntPtr session,IntPtr op,out uint origin,out int prep){
  IntPtr obj=VideoInstance(),input=Zero(64),output=Zero(128),y=Marshal.AllocHGlobal(2097152),c=Marshal.AllocHGlobal(2097152);bool locked=false;origin=0;prep=-999;
  try{
   Marshal.WriteInt32(input,16,65535);Marshal.WriteInt32(input,20,65535);Marshal.WriteByte(input,24,1);
   Marshal.WriteInt32(output,40,2097152);Marshal.WriteInt32(output,44,2097152);Marshal.WriteIntPtr(output,48,y);Marshal.WriteIntPtr(output,52,c);
   VideoLock(obj,1,0);locked=true;prep=VideoYuv(obj,input,output,0);
   if(prep!=0 && prep!=-4)return 0xffff0000;
   return TEEC_InvokeCommand(session,1,op,out origin);
  }finally{if(locked)VideoUnlock(obj,1,0);Marshal.FreeHGlobal(c);Marshal.FreeHGlobal(y);Marshal.FreeHGlobal(output);Marshal.FreeHGlobal(input);}
 }
 static object CaptureFp(IntPtr context,IntPtr session,int index){
  IntPtr op=Zero(60),shared=Zero(36);bool allocated=false;long at=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();var clock=Stopwatch.StartNew();
  try{
   Marshal.WriteInt32(op,4,0x02020101);Marshal.WriteInt32(op,8,2); // Native scaler 0 maps to virtual capture source 2.
   uint capture=CaptureSecure(session,op,out uint captureOrigin,out int prep);
   if(capture!=0)return new {index,at,capture_rc=capture,capture_origin=captureOrigin,prepare_rc=prep};
   for(int i=0;i<60;i++)Marshal.WriteByte(op,i,0);
   Marshal.WriteInt32(shared,4,180);Marshal.WriteInt32(shared,8,3);
   uint alloc=TEEC_AllocateSharedMemory(context,shared);if(alloc!=0)return new {index,at,allocate_rc=alloc};allocated=true;
   IntPtr data=Marshal.ReadIntPtr(shared);for(int i=0;i<180;i++)Marshal.WriteByte(data,i,0);
   Marshal.WriteInt32(op,4,0x0e03);Marshal.WriteIntPtr(op,20,shared);Marshal.WriteInt32(op,24,180);
   uint fp=TEEC_InvokeCommand(session,4,op,out uint fpOrigin);int count=Marshal.ReadInt32(op,8);
   byte[] bytes=new byte[180];Marshal.Copy(data,bytes,0,180);
   return new {index,at,capture_rc=capture,prepare_rc=prep,fingerprint_rc=fp,fingerprint_origin=fpOrigin,roi_count=count,elapsed_ms=clock.ElapsedMilliseconds,raw_base64=Convert.ToBase64String(bytes)};
  }finally{if(allocated)TEEC_ReleaseSharedMemory(shared);Marshal.FreeHGlobal(shared);Marshal.FreeHGlobal(op);}
 }
 public static void TryCaptureDue(long imageAt){
  const string state="/run/commercial-block/";
  try {
   File.Delete(state+"acr-fingerprint");
   if(!File.Exists(state+"acr-next-capture"))return;
   if(!long.TryParse(File.ReadAllText(state+"acr-next-capture").Trim(),out long due) || due<=0 || DateTimeOffset.UtcNow.ToUnixTimeSeconds()<due)return;
   // Local backoff also bounds retries when the host is unavailable.
   File.WriteAllText(state+"acr-next-capture",(DateTimeOffset.UtcNow.ToUnixTimeSeconds()+60).ToString());
   CaptureOne(imageAt);
  } catch(Exception) { try { File.Delete(state+"acr-fingerprint"); }catch(Exception){} }
 }
 static int CaptureOne(long imageAt){
  IntPtr context=Marshal.AllocHGlobal(64),session=Marshal.AllocHGlobal(64);
  for(int i=0;i<64;i+=4){Marshal.WriteInt32(context,i,0);Marshal.WriteInt32(session,i,0);}
  bool initialized=false,opened=false;
  try{
   uint rc=TEEC_InitializeContext(IntPtr.Zero,context);if(rc!=0)return 2;initialized=true;
   byte[] uuid={1,0,0,0x50,0,0,0,0,0,0,0,0,0,0,0,1};
   rc=TEEC_OpenSession(context,session,uuid,0,IntPtr.Zero,IntPtr.Zero,out uint origin);
   if(rc!=0)return 3;opened=true;

   rc=SetParams(context,session);if(rc!=0)return 4;
   var capture=CaptureFp(context,session,0);
   string json=JsonSerializer.Serialize(capture);
   json=json.Substring(0,json.Length-1)+",\"image_capture_started_ms\":"+imageAt+"}";
   File.WriteAllText("/run/commercial-block/acr-fingerprint",Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(json)));
   return 0;
  }finally{if(opened)TEEC_CloseSession(session);if(initialized)TEEC_FinalizeContext(context);Marshal.FreeHGlobal(session);Marshal.FreeHGlobal(context);}
 }
}
