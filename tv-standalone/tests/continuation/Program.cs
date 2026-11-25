using System;
using System.Text.Json;
class Tests
{
 static void Check(bool b,string name){if(!b)throw new Exception(name);}
 static JsonElement Reply(string mm="[1,0,2,0]",string at="123",string dist="5",string matching="true")=>JsonDocument.Parse("{\"result\":{\"acr\":{\"result_frames\":[{\"tvt\":{\"utc\":\""+at+"\"},\"dist\":"+dist+",\"matching\":"+matching+",\"mm_count\":"+mm+"}]}}}").RootElement;
 static ArchiveContinuation Ready(bool hit=false){var p=new ArchiveContinuation{Enabled=true};for(int i=1;i<=50;i++)p.Observe(i*1000,hit,false,0,false);p.Strong(112000,true);return p;}
 static void Main(string[] args)
 {
  if(args.Length>0&&args[0]=="--replay"){
   var policy=new ArchiveContinuation{Enabled=true};bool covered=false;long strongExpiry=0;string line;
   while((line=Console.ReadLine())!=null){var e=JsonDocument.Parse(line).RootElement;long now=e.GetProperty("at").GetInt64();
    if(e.TryGetProperty("reset",out var r)&&r.GetBoolean()){policy.ResetSession();covered=false;strongExpiry=0;}
    if(covered&&now>=Math.Max(strongExpiry,policy.Until)){covered=false;policy.Released(now);}
    if(e.TryGetProperty("positive",out var pos)&&pos.GetBoolean()){policy.Strong(now,!covered);covered=true;strongExpiry=now+8000;}
    else if(e.TryGetProperty("qualifies",out var q)){if(e.TryGetProperty("eligible",out var eligible)&&!eligible.GetBoolean())policy.BreakSequence();else policy.Observe(now,q.GetBoolean(),covered,strongExpiry,covered);}
    Console.WriteLine(JsonSerializer.Serialize(new{covered,until=Math.Max(strongExpiry,policy.Until),status=policy.Status()}));
   }return;
  }
  Check(ArchiveContinuation.Qualifies(Reply(),"123"),"valid repeat");
  foreach(string mm in new[]{"[1,2,2,0]","[1,3,2,0]","[1,0,1,0]","[1,0,2]","[1,0,-2,0]","[1,0,2.5,0]","[true,0,2,0]","null"})Check(!ArchiveContinuation.Qualifies(Reply(mm),"123"),"malformed/no evidence "+mm);
  Check(!ArchiveContinuation.Qualifies(Reply(at:"122"),"123"),"timestamp");Check(!ArchiveContinuation.Qualifies(Reply(dist:"16"),"123"),"distance");Check(!ArchiveContinuation.Qualifies(Reply(dist:"1.5"),"123"),"fractional distance");Check(!ArchiveContinuation.Qualifies(Reply(matching:"false"),"123"),"unmatched");
  var p=Ready();Check(p.BaselineCount==50&&p.BaselineEligible,"mature baseline");
  Check(p.Observe(115000,true,false,120000,false)==0,"never starts cover");
  Check(p.Observe(115000,true,true,120000,false)==0,"missing lease");
  Check(p.Observe(118000,true,true,120000,true)==126000,"renew covered");
  for(long t=124000;t<=154000;t+=6000)p.Observe(t,true,true,120000,true);
  Check(p.Until==157000,"hard45 cap");Check(p.Observe(157000,true,true,120000,true)==0,"no resurrection at cap");
  p.ResetSession();Check(p.Until==0&&!p.BaselineEligible,"navigation resets");
  p=Ready(true);Check(p.Observe(115000,true,true,120000,true)==0&&p.BaselineBlocked==1,"high baseline");
  p=new ArchiveContinuation{Enabled=true};p.Strong(1000,true);Check(p.Observe(2000,true,true,9000,true)==0,"cold baseline");
  p=Ready();p.Enabled=false;Check(p.Observe(115000,true,true,120000,true)==0&&p.WouldRenew==1,"default-off shadow");
  p=Ready();p.Released(113000);p.Observe(114000,true,false,0,false);p.Strong(175000,true);Check(p.BaselineCount==50,"release quiet period");
  p=new ArchiveContinuation{Enabled=true};for(int i=1;i<=50;i++)p.Observe(i*1000,false,false,0,false);p.Strong(55000,true);p.Released(56000);p.Strong(120000,true);Check(p.BaselineCount==0,"pending prebreak excluded");
  var m=new MaskedLookPolicy();Check(!m.Begin(1000,8000),"no early mask");Check(m.Begin(5500,8000),"late mask");m.Complete(false);Check(!m.Begin(6500,8000),"one look per lease");m.Reset();Check(m.Begin(5500,8000),"new look");m.Complete(true);Check(!m.Begin(5700,8000)&&m.Begin(6100,8000),"bounded safe retry");m.Complete(true);Check(!m.Begin(6700,8000),"max two");Check(!m.Begin(9000,9000),"expired");
  Console.WriteLine("PASS continuation parser, baseline, quiet periods, hard budget, cancellation, no resurrection, shadow and masked scheduling");
 }
}
