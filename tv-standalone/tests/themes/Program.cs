using System;
using System.IO;
class Tests {
 static void Check(bool x,string name){if(!x)throw new Exception(name);}
 static void Main(string[] args){
  string dir=Path.Combine(Path.GetTempPath(),"cb-themes-"+Guid.NewGuid());Directory.CreateDirectory(Path.Combine(dir,"themes"));
  try{
   File.Copy(Path.Combine(args[0],"scene.json"),Path.Combine(dir,"scene.json"));
   File.Copy(Path.Combine(args[0],"themes","winter.json"),Path.Combine(dir,"themes","winter.json"));
   var s=new ThemeSettings(dir);Check(s.Selected=="default","fresh default");
   s.Set("winter");Check(new ThemeSettings(dir).Selected=="winter","persistent choice");
   foreach(string bad in new[]{"../scene","absent","spring"}){bool rejected=false;try{s.Set(bad);}catch(ArgumentException){rejected=true;}Check(rejected&&s.Selected=="winter","invalid choice preserves selection");}
   File.WriteAllText(Path.Combine(dir,"themes","winter.json"),"{}");Check(s.EffectiveTheme=="default"&&s.ResolveScene()==Path.Combine(dir,"scene.json"),"corruption falls back");
   Check(new ThemeSettings(dir).Selected=="default","invalid saved scene fallback");
   File.WriteAllText(Path.Combine(dir,"appearance.json"),"not json");Check(new ThemeSettings(dir).Selected=="default","bad settings fallback");
   s.Set("default");Check(new ThemeSettings(dir).Selected=="default","restore original");
   Console.WriteLine("Theme settings: persistence, invalid input, missing/corrupt scene and original restoration passed.");
  }finally{Directory.Delete(dir,true);}
 }
}
