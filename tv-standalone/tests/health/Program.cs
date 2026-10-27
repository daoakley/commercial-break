using System;
using System.IO;
using System.Linq;
class Test {
 static void Check(bool ok,string name){if(!ok)throw new Exception(name);Console.WriteLine("PASS "+name);}
 static void Main(){string dir=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString());Directory.CreateDirectory(dir);try{
  Check(!EngineHealth.LoadEnabled(dir),"missing state defaults off");
  EngineHealth.SaveEnabled(dir,true);Check(EngineHealth.LoadEnabled(dir),"on survives a new read");
  EngineHealth.SaveEnabled(dir,false);Check(!EngineHealth.LoadEnabled(dir),"off survives a new read");
  File.WriteAllText(dir+"/enabled","corrupt");Check(!EngineHealth.LoadEnabled(dir),"invalid state defaults off");
  var h=new EngineHealth(dir,dir);h.Error("test",new Exception("SECRET_TOKEN_AND_VIEWING_METADATA"));
  Check(!File.ReadAllText(dir+"/diagnostics/engine.jsonl").Contains("SECRET"),"exception payload omitted");
  for(int i=0;i<7000;i++)h.Event("test");
  var logs=Directory.GetFiles(dir+"/diagnostics");Check(logs.Length==3&&logs.Sum(f=>new FileInfo(f).Length)<200000,"bounded log rotation");
  File.Delete(dir+"/diagnostics/engine.jsonl");Directory.CreateDirectory(dir+"/diagnostics/engine.jsonl");h.Event("unwritable");Check(true,"diagnostic write failure is nonfatal");
 }finally{Directory.Delete(dir,true);}}
}
