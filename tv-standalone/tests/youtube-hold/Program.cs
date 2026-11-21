using System;
using System.Text.Json;
class Program {
 static int checks;
 static void Check(bool b,string why){checks++;if(!b)throw new Exception(why);}
 static YouTubeCountdownHold.Reading R(long at,int n,int? max=null)=>new YouTubeCountdownHold.Reading{at=at,min=n,max=max??n};
 static YouTubeCountdownHold Hold(){var h=new YouTubeCountdownHold();Check(!h.Observe(R(100000,29),100400),"one frame cannot hold");Check(h.Observe(R(103000,25,26),103400),"consistent countdown");return h;}
 static void Main(){
  var h=Hold();Check(h.CheckAt==126500,"earliest plausible end minus lead time");Check(h.Waiting(125000),"stays steady through known countdown");Check(!h.Waiting(126500)&&h.KeepsCovered(126500),"masked recheck keeps cover lease");Check(!h.KeepsCovered(130500),"finite expiry grace");Check(!h.KeepsCovered(103399),"clock rollback fails open");
  h.Reset();Check(h.CheckAt==0&&!h.KeepsCovered(120000)&&h.Seconds==null,"navigation/Off/reset cancel hold");Check(!h.Observe(R(104000,24),104400),"reset removes old confirmation");
  h=Hold();Check(!h.Observe(null,104000)&&!h.KeepsCovered(104000),"unreadable or Skip returns to ordinary cadence");
  h=new YouTubeCountdownHold();h.Observe(R(100000,15,16),100300);Check(h.Observe(R(102000,14),102300)&&h.CheckAt==113500,"ambiguous digit uses lower deadline");
  h=new YouTubeCountdownHold();h.Observe(R(100000,5),100300);Check(!h.Observe(R(103000,2),103400),"near expiry never sleeps past transition");
  foreach(var pair in new[]{new[]{101000,30},new[]{101000,29},new[]{101000,10},new[]{106000,23},new[]{100100,28},new[]{99000,28}}){h=new YouTubeCountdownHold();h.Observe(R(100000,29),100300);Check(!h.Observe(R(pair[0],pair[1]),Math.Max(100300,pair[0]+100)),"inconsistent/reset/stale/out-of-order");}
  h=new YouTubeCountdownHold();h.Observe(R(100000,60),100100);Check(h.Observe(R(101000,59),101100)&&h.CheckAt==131100,"30 second unobserved maximum");
  foreach(var r in new[]{R(100000,0),R(100000,61),R(100000,15,17),R(100000,15,14),R(104000,15)})Check(!h.Observe(r,103000),"bad range or stale/future");
  string json="{\"at\":100000,\"timerReader\":\"youtube-yellow-digits-v1\",\"state\":\"countdown\",\"controlKind\":\"circle\",\"timerSeconds\":29,\"timerMaxSeconds\":29,\"timerScore\":0.99,\"timerLayoutMargin\":0.5}";
  Check(YouTubeCountdownHold.Parse(JsonDocument.Parse(json).RootElement,100400)!=null,"valid reader evidence");
  foreach(var bad in new[]{json.Replace("0.99","0.93"),json.Replace("0.5","0.1"),json.Replace("circle","skip"),json.Replace("countdown","skip"),json.Replace("digits-v1","digits-v0"),json.Replace(":29",":null"),"{}"})Check(YouTubeCountdownHold.Parse(JsonDocument.Parse(bad).RootElement,100400)==null,"reject invalid reader evidence");
  Check(YouTubeCountdownHold.Parse(JsonDocument.Parse(json).RootElement,102501)==null,"reject stale reader");Check(YouTubeCountdownHold.Parse(JsonDocument.Parse(json).RootElement,99999)==null,"reject future reader");
  Console.WriteLine(checks+" countdown scheduling checks passed");
 }
}
