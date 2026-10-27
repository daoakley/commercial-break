using System;
using System.IO;
using System.Linq;
using System.Diagnostics;
using System.Globalization;
using System.Text.Json;

// Diagnostic data deliberately excludes exception messages, request bodies,
// identities, tokens, images, paths and viewing context. Logging cannot crash us.
sealed class EngineHealth {
 readonly string home,state,log;
 readonly object gate=new object();
 readonly int pid=Process.GetCurrentProcess().Id;
 readonly long started=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
 long pulse=-1,lastErrorAt;string lastError="";
 public EngineHealth(string home,string state){this.home=home;this.state=state;log=home+"/diagnostics/engine.jsonl";}
 public static bool LoadEnabled(string home){try{return File.ReadAllText(home+"/enabled").Trim()=="1";}catch{return false;}}
 public static void SaveEnabled(string home,bool enabled){File.WriteAllText(home+"/enabled.tmp",enabled?"1":"0");File.Move(home+"/enabled.tmp",home+"/enabled",true);}
 public void Pulse(string stage){
  long now=(long)double.Parse(File.ReadAllText("/proc/uptime").Split(' ')[0],CultureInfo.InvariantCulture);
  if(now==pulse)return;
  File.WriteAllText(state+"/engine-health.tmp",pid+" "+now);
  File.Move(state+"/engine-health.tmp",state+"/engine-health",true);pulse=now;
 }
 public void Event(string kind){Write(new{at=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),pid,kind});}
 public void Error(string stage,Exception error){lock(gate){
  string type=error?.GetType().Name??"Unknown";long now=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
  if(lastError==stage+type&&now-lastErrorAt<30000)return;
  lastError=stage+type;lastErrorAt=now;
  var frames=error==null?new string[0]:(new StackTrace(error,false).GetFrames()??new StackFrame[0]).Take(8).Select(f=>f.GetMethod()?.Name).ToArray();
  Write(new{at=now,pid,kind="error",stage,type,frames});
 }}
 void Write(object entry){try{lock(gate){
  Directory.CreateDirectory(home+"/diagnostics");
  if(File.Exists(log)&&new FileInfo(log).Length>=65536){if(File.Exists(log+".1"))File.Move(log+".1",log+".2",true);File.Move(log,log+".1",true);}
  File.AppendAllText(log,JsonSerializer.Serialize(entry)+"\n");
 }}catch{}}
 public object Status(){JsonElement? recovery=null;try{recovery=JsonDocument.Parse(File.ReadAllText(state+"/supervisor.json")).RootElement.Clone();}catch{}return new{pid,startedAt=started,lastLoopUptimeSeconds=pulse,recovery,diagnostics="bounded private logs; no screenshots or credentials"};}
}
