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
   foreach(string city in new[]{"memphis","dc","raleigh","charlotte"})foreach(string mode in new[]{"day","night"})
    File.Copy(Path.Combine(args[0],"themes",city+"-"+mode+".json"),Path.Combine(dir,"themes",city+"-"+mode+".json"));
   s.Set("cities-night");
   foreach(string city in new[]{"memphis","dc","raleigh","charlotte","memphis"}) {
    s.BeginBreak();Check(s.EffectiveTheme==city+"-night","ordered city rotation");
    for(int i=0;i<10;i++){s.BeginBreak();Check(s.EffectiveTheme==city+"-night","renewals keep the same city");}
    s.EndBreak();
   }
   s=new ThemeSettings(dir);s.BeginBreak();Check(s.EffectiveTheme=="dc-night","next city survives restart");
   s.Set("cities-day");Check(s.EffectiveTheme=="dc-night","palette change keeps active break");
   s.EndBreak();s.BeginBreak();Check(s.EffectiveTheme=="raleigh-day","day palette applies next break");
   s.EndBreak();File.WriteAllText(Path.Combine(dir,"themes","charlotte-day.json"),"{}");
   s.BeginBreak();Check(s.EffectiveTheme=="memphis-day","corrupt city skipped");s.EndBreak();
   foreach(string city in new[]{"memphis","dc","raleigh","charlotte"})File.WriteAllText(Path.Combine(dir,"themes",city+"-day.json"),"{}");
   s.BeginBreak();Check(s.EffectiveTheme=="default","all missing cities fall back to Original");s.EndBreak();
   s.Set("raleigh-night");s.BeginBreak();s.EndBreak();s.BeginBreak();Check(s.EffectiveTheme=="raleigh-night","fixed theme never rotates");
   s.EndBreak();s.Set("cities-night");File.Delete(Path.Combine(dir,"appearance.json"));Directory.CreateDirectory(Path.Combine(dir,"appearance.json"));
   s.BeginBreak();Check(s.EffectiveTheme=="memphis-night","cursor write failure does not block rendering");
   Console.WriteLine("Theme settings: persistence, invalid input, missing/corrupt scene and original restoration passed.");
   Console.WriteLine("Rotation: sequence, renewals, restart, palette changes, missing scenes and failed cursor writes passed.");
  }finally{Directory.Delete(dir,true);}
 }
}
