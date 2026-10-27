using System;using System.IO;using System.Runtime.InteropServices;using System.Text.Json;
class Program {
 static int Main(string[] args){try{
  if(args[0]=="--score"){var m=LayoutDetector.Model.Load(args[1]);var f=JsonSerializer.Deserialize<float[]>(File.ReadAllText(args[2]));Console.WriteLine(m.Score(f).ToString("R",System.Globalization.CultureInfo.InvariantCulture));return 0;}
  if(args[0]=="--features"){var m=LayoutDetector.Model.Load(args[1]);var f=LayoutDetector.Features(File.ReadAllBytes(args[2]),m);Console.WriteLine(JsonSerializer.Serialize(new{features=f,score=m.Score(f)}));return 0;}
  if(args[0]=="--nv12"){int w=int.Parse(args[3]),h=int.Parse(args[4]),pitch=int.Parse(args[5]);byte[] bytes=File.ReadAllBytes(args[1]);var pin=GCHandle.Alloc(bytes,GCHandleType.Pinned);try{File.WriteAllBytes(args[2],LayoutDetector.RgbNv12(pin.AddrOfPinnedObject(),IntPtr.Add(pin.AddrOfPinnedObject(),pitch*h),w,h,pitch,pitch*h));}finally{pin.Free();}return 0;}
  return 2;
 }catch(Exception e){Console.Error.WriteLine(e.GetType().Name);return 1;}}
}
