using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
class LifecycleTests {
 static Type Engine=typeof(Program);
 static FieldInfo Field(string name)=>Engine.GetField(name,BindingFlags.NonPublic|BindingFlags.Static);
 static void Set(string name,object value)=>Field(name).SetValue(null,value);
 static void Refresh()=>Engine.GetMethod("RefreshIdleOverlay",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,null);
 static void Check(bool value,string name){if(!value)throw new Exception(name);}
 static void Main(string[] args){
  string dir=Path.Combine(Path.GetTempPath(),"cb-lifecycle-"+Guid.NewGuid());Directory.CreateDirectory(Path.Combine(dir,"themes"));
  Process warm=null;
  try{
   File.Copy(Path.Combine(args[0],"scene.json"),Path.Combine(dir,"scene.json"));
   File.Copy(Path.Combine(args[0],"themes","winter.json"),Path.Combine(dir,"themes","winter.json"));
   var settings=new ThemeSettings(dir);Set("Themes",settings);Set("CoverTheme","default");Set("Covered",false);
   warm=Process.Start(new ProcessStartInfo("/bin/sleep","60"){UseShellExecute=false});int pid=warm.Id;Set("Overlay",warm);
   Refresh();Check(!warm.HasExited && Field("Overlay").GetValue(null)==warm,"unchanged theme keeps warm renderer");
   settings.Set("winter");Set("Covered",true);Refresh();Check(!warm.HasExited,"save does not interrupt active cover");
   Set("Covered",false);Refresh();Check(Field("Overlay").GetValue(null)==null,"changed idle renderer retired");
   bool alive=true;try{using(var p=Process.GetProcessById(pid)){alive=!p.HasExited;}}catch(ArgumentException){alive=false;}Check(!alive,"stale process actually exited");
   Refresh();Check(settings.Selected=="winter","saved theme survives retirement");
   foreach(string city in new[]{"memphis","dc","raleigh","charlotte"})File.Copy(Path.Combine(args[0],"themes",city+"-night.json"),Path.Combine(dir,"themes",city+"-night.json"));
   settings.Set("cities-night");
   var prepare=Engine.GetMethod("PrepareBreakArtwork",BindingFlags.NonPublic|BindingFlags.Static);
   prepare.Invoke(null,null);Check(settings.EffectiveTheme=="memphis-night","first cover selects Memphis");
   Set("CoverTheme","memphis-night");Set("Covered",true);
   warm=Process.Start(new ProcessStartInfo("/bin/sleep","60"){UseShellExecute=false});Set("Overlay",warm);
   for(int i=0;i<4;i++)prepare.Invoke(null,null);
   Check(!warm.HasExited&&settings.EffectiveTheme=="memphis-night","renewal preserves city and renderer");
   Set("Covered",false);settings.EndBreak();prepare.Invoke(null,null);
   Check(settings.EffectiveTheme=="dc-night"&&Field("Overlay").GetValue(null)==null,"next cover advances and retires previous city renderer");
   Console.WriteLine("Renderer lifecycle passed: unchanged retained, active cover preserved, changed idle process retired, selection preserved.");
  }finally{try{if(warm!=null&&!warm.HasExited)warm.Kill();}catch{}Directory.Delete(dir,true);}
 }
}
