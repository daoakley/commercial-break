using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Collections.Generic;

// Owns only debug-session.json, debug-records/, and debug-*.png in this app's
// runtime directory. Never touches production configuration or other projects.
internal sealed class DebugRecords {
 internal sealed class Ticket { public string session, id, image; public long startedAt; }
 readonly object gate=new object(); readonly string root, stateFile, runtime; readonly Func<long> clock; readonly long limit;
 string session; long started, until, dropped; string error="", reason="Off"; long lastSweep;
 public DebugRecords(string home,string runtime,Func<long> clock,long limit=128L*1024*1024) {
  root=Path.Combine(home,"debug-records");stateFile=Path.Combine(home,"debug-session.json");this.runtime=runtime;this.clock=clock;this.limit=limit;
  try { if(File.Exists(stateFile)){var s=JsonDocument.Parse(File.ReadAllText(stateFile)).RootElement;session=s.GetProperty("session").GetString();started=s.GetProperty("startedAt").GetInt64();until=s.GetProperty("expiresAt").GetInt64();if(string.IsNullOrEmpty(session)||until-started!=48L*60*60*1000||clock()<started)session=null;} }
  catch {session=null;error="Invalid saved debug session";}
  Maintain();
 }
 void SaveState(){Directory.CreateDirectory(Path.GetDirectoryName(stateFile));File.WriteAllText(stateFile+".tmp",JsonSerializer.Serialize(new{session,startedAt=started,expiresAt=until}));File.Move(stateFile+".tmp",stateFile,true);}
 public void Set(bool on){lock(gate){MaintainLocked();if(on){if(session!=null)return;Clean();if(Directory.Exists(root)||File.Exists(stateFile)){error="Previous debug cleanup is incomplete";return;}session=Guid.NewGuid().ToString("N");started=clock();until=started+48L*60*60*1000;dropped=0;try{SaveState();Directory.CreateDirectory(root);reason="Recording";error="";}catch{session=null;until=0;error="Cannot start debug recording";Clean();}}else{session=null;until=0;reason="Stopped and cleared";Clean();}}}
 public void Maintain(){lock(gate)MaintainLocked();}
 void MaintainLocked(){
  if(session!=null&&(clock()>=until||clock()<started)){session=null;until=0;reason="Expired and cleared";}
  if(session==null){Clean();return;}
  // A failed delete is retried, and a restart also enforces the disk bound.
  if(clock()-lastSweep>5000){lastSweep=clock();try{PruneOrphans();Trim(0);}catch{error="Debug storage cleanup failed; retrying";}}
 }
 void Clean(){try{if(Directory.Exists(root))Directory.Delete(root,true);File.Delete(stateFile);File.Delete(stateFile+".tmp");if(Directory.Exists(runtime))foreach(var p in Directory.GetFiles(runtime,"debug-*.png*"))File.Delete(p);error="";}catch{error="Debug cleanup pending; will retry";}}
 public Ticket Begin(){lock(gate){MaintainLocked();if(session==null)return null;string id=Guid.NewGuid().ToString("N");return new Ticket{session=session,id=id,startedAt=clock(),image=Path.Combine(runtime,"debug-"+id+".png")};}}
 public object Status(){lock(gate){MaintainLocked();long bytes=0;int count=0;try{if(Directory.Exists(root)){var fs=new DirectoryInfo(root).GetFiles();bytes=fs.Sum(f=>f.Length);count=fs.Count(f=>f.Extension==".json");}}catch{}
  return new{enabled=session!=null,startedAt=session==null?(long?)null:started,expiresAt=session==null?(long?)null:until,remainingSeconds=session==null?0:Math.Max(0,(until-clock()+999)/1000),records=count,bytes,maxBytes=limit,evictedRecords=dropped,message=session!=null?"Recording; oldest records removed at storage limit":reason,error};}}
 public void Event(string kind,string detail){lock(gate){MaintainLocked();if(session==null)return;try{Directory.CreateDirectory(root);string p=Path.Combine(root,"events.jsonl");if(File.Exists(p)&&new FileInfo(p).Length>1024*1024)File.Delete(p);File.AppendAllText(p,JsonSerializer.Serialize(new{at=clock(),kind,detail})+"\n");}catch{error="Could not save debug event";}}}
 void PruneOrphans(){
  long stale=clock()-30000;
  if(Directory.Exists(runtime))foreach(var f in new DirectoryInfo(runtime).GetFiles("debug-*.png*"))if(new DateTimeOffset(f.LastWriteTimeUtc).ToUnixTimeMilliseconds()<stale)f.Delete();
  if(Directory.Exists(root))foreach(var f in new DirectoryInfo(root).GetFiles())if(new DateTimeOffset(f.LastWriteTimeUtc).ToUnixTimeMilliseconds()<stale&&(f.Name.EndsWith(".tmp")||(f.Extension==".png"&&!File.Exists(Path.ChangeExtension(f.FullName,".json")))))f.Delete();
 }
 void Trim(long incoming){if(!Directory.Exists(root))return;var fs=new DirectoryInfo(root).GetFiles();long bytes=fs.Sum(f=>f.Length);foreach(var j in fs.Where(f=>f.Extension==".json").OrderBy(f=>f.Name,StringComparer.Ordinal)){if(bytes+incoming<=limit)break;string png=Path.ChangeExtension(j.FullName,".png");if(File.Exists(png)){bytes-=new FileInfo(png).Length;File.Delete(png);}bytes-=j.Length;j.Delete();dropped++;}if(bytes+incoming>limit)throw new IOException("Debug storage limit");}
 public void Complete(Ticket ticket,object metadata){if(ticket==null)return;lock(gate){try{MaintainLocked();if(session==null||session!=ticket.session)return;
   byte[] png=null;string imageError=null;try{if(File.Exists(ticket.image)){var f=new FileInfo(ticket.image);if(f.Length<=4*1024*1024)png=File.ReadAllBytes(ticket.image);else imageError="Image exceeded limit";}else imageError="Capture did not produce an image";}catch{imageError="Image unavailable";}
   var document=new{schema="commercial-break-debug/1",sessionId=session,captureId=ticket.id,recordedAt=clock(),sessionExpiresAt=until,imageAvailable=png!=null,imageError,evidence=metadata};
   string json=JsonSerializer.Serialize(Sanitize(JsonDocument.Parse(JsonSerializer.Serialize(document)).RootElement));byte[] tagged=null;if(png!=null)try{tagged=Embed(png,json);}catch{json=JsonSerializer.Serialize(Sanitize(JsonDocument.Parse(JsonSerializer.Serialize(new{schema="commercial-break-debug/1",sessionId=session,captureId=ticket.id,recordedAt=clock(),sessionExpiresAt=until,imageAvailable=false,imageError="Invalid PNG",evidence=metadata})).RootElement));}
   long needed=Encoding.UTF8.GetByteCount(json)+(tagged?.Length??0);Directory.CreateDirectory(root);Trim(needed);
   string path=Path.Combine(root,ticket.startedAt.ToString("D13")+"-"+ticket.id);if(tagged!=null){File.WriteAllBytes(path+".png.tmp",tagged);File.Move(path+".png.tmp",path+".png",true);}File.WriteAllText(path+".json.tmp",json);File.Move(path+".json.tmp",path+".json",true);error="";
  }catch{error="Debug record could not be saved";}finally{try{File.Delete(ticket.image);File.Delete(ticket.image+".tmp");}catch{}}}}
 static readonly HashSet<string> SecretKeys=new HashSet<string>(new[]{"psid","duid","deviceid","device_id","deviceuuid","device_uuid","uuid","mac","macaddress","mac_address","ip","ipaddress","ip_address","token","controltoken","authorization","cookie","password","serialnumber","serial_number"},StringComparer.OrdinalIgnoreCase);
 internal static object Sanitize(JsonElement e){switch(e.ValueKind){case JsonValueKind.Object:var d=new Dictionary<string,object>();foreach(var p in e.EnumerateObject())d[p.Name]=SecretKeys.Contains(p.Name)?(object)"[redacted]":Sanitize(p.Value);return d;case JsonValueKind.Array:return e.EnumerateArray().Select(Sanitize).ToArray();default:return e.Clone();}}
 static uint Crc(byte[] bytes){uint crc=0xffffffff;foreach(byte b in bytes){crc^=b;for(int i=0;i<8;i++)crc=(crc&1)!=0?0xedb88320^(crc>>1):crc>>1;}return crc^0xffffffff;}
 static uint Be(byte[] p,int i)=>(uint)p[i]<<24|(uint)p[i+1]<<16|(uint)p[i+2]<<8|p[i+3];
 static void WriteBe(Stream s,uint n){s.WriteByte((byte)(n>>24));s.WriteByte((byte)(n>>16));s.WriteByte((byte)(n>>8));s.WriteByte((byte)n);}
 internal static byte[] Embed(byte[] png,string metadata){byte[] signature={137,80,78,71,13,10,26,10};if(png.Length<20||!png.Take(8).SequenceEqual(signature))throw new IOException("Not PNG");int at=8;while(at+12<=png.Length){uint len=Be(png,at);if(len>(uint)(png.Length-at-12))throw new IOException("Invalid PNG length");string type=Encoding.ASCII.GetString(png,at+4,4);if(type=="IEND")break;at+=12+(int)len;}if(at+12!=png.Length||Encoding.ASCII.GetString(png,at+4,4)!="IEND")throw new IOException("Invalid PNG end");
  // Uncompressed UTF-8 iTXt, readable without any companion application.
  byte[] payload=Encoding.UTF8.GetBytes("CommercialBreak.Debug\0\0\0\0\0"+metadata);byte[] typed=Encoding.ASCII.GetBytes("iTXt").Concat(payload).ToArray();using(var s=new MemoryStream()){s.Write(png,0,at);WriteBe(s,(uint)payload.Length);s.Write(typed,0,typed.Length);WriteBe(s,Crc(typed));s.Write(png,at,png.Length-at);return s.ToArray();}}
}
