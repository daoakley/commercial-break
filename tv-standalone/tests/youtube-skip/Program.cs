using System;
class Program {
 static void Check(bool b,string message){if(!b)throw new Exception(message);}
 static bool Attempt(YouTubeSkipGuard g,long now=100000,long frame=99900,bool enabled=true,bool regular=true,bool skip=true,long nav=4000,bool same=true)=>g.TryAttempt(now,frame,enabled,regular,skip,nav,same);
 static void Main(){
  Check(!Attempt(new YouTubeSkipGuard(),enabled:false),"disabled");Check(!Attempt(new YouTubeSkipGuard(),regular:false),"other app");Check(!Attempt(new YouTubeSkipGuard(),skip:false),"countdown");Check(!Attempt(new YouTubeSkipGuard(),nav:2999),"recent navigation");Check(!Attempt(new YouTubeSkipGuard(),same:false),"changed session");Check(!Attempt(new YouTubeSkipGuard(),frame:100001),"future");Check(!Attempt(new YouTubeSkipGuard(),frame:98000),"stale");
  var g=new YouTubeSkipGuard();Check(Attempt(g),"first highlighted Skip");Check(!Attempt(g,now:101000,frame:100900),"no double press");Check(!Attempt(g,now:200000,frame:199900),"continuous break never rearms");
  for(int i=201000;i<=211000;i+=1000)g.Observe(i,false,false);Check(!Attempt(g,now:212000,frame:211900),"missing evidence cannot rearm");
  for(int i=213000;i<=220000;i+=1000)g.Observe(i,true,false);Check(!Attempt(g,now:220000,frame:219900),"clear interval too short");g.Observe(221000,true,false);Check(Attempt(g,now:221000,frame:220900),"new break after clear frames");
  for(int i=222000;i<=231000;i+=1000)g.Observe(i,true,false);Check(!Attempt(g,now:232000,frame:231900),"minimum 60 second interval");Check(Attempt(g,now:282000,frame:281900),"later break");
  var restarted=new YouTubeSkipGuard(282000);Check(!Attempt(restarted,now:300000,frame:299900),"restart retains latch");for(int i=301000;i<=310000;i+=1000)restarted.Observe(i,true,false);Check(!Attempt(restarted,now:310000,frame:309900),"restart cooldown");Check(!Attempt(restarted,now:200000,frame:199900),"clock rollback");
  Console.WriteLine("18 automatic Skip guard checks passed");
 }
}
