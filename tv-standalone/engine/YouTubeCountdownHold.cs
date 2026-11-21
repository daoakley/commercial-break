using System;
using System.Text.Json;

// A countdown controls when to look again, never whether a frame is an ad.
// Call only after the existing fresh, app-scoped ad-control gate accepts it.
public sealed class YouTubeCountdownHold {
 public sealed class Reading { public long at; public int min,max; }
 Reading previous;
 public long CheckAt {get;private set;}
 public long StartedAt {get;private set;}
 public int? Seconds {get;private set;}
 public int? MaxSeconds {get;private set;}
 public static Reading Parse(JsonElement p,long now){try{
  long at=p.GetProperty("at").GetInt64();int min=p.GetProperty("timerSeconds").GetInt32(),max=p.GetProperty("timerMaxSeconds").GetInt32();
  double score=p.GetProperty("timerScore").GetDouble(),margin=p.GetProperty("timerLayoutMargin").GetDouble();
  if(p.GetProperty("timerReader").GetString()!="youtube-yellow-digits-v1"||p.GetProperty("state").GetString()!="countdown"||p.GetProperty("controlKind").GetString()!="circle"||now<at||now-at>2500||min<1||max<min||max>60||max-min>1||!(score>=.94&&score<=1.000001)||!(margin>=.15&&margin<=1))return null;
  return new Reading{at=at,min=min,max=max};
 }catch{return null;}}
 public void Reset(){previous=null;CheckAt=StartedAt=0;Seconds=MaxSeconds=null;}
 public bool Observe(Reading value,long now){
  var old=previous;Reset();
  if(value==null||value.at>now||now-value.at>2500||value.min<1||value.max<value.min||value.max>60||value.max-value.min>1)return false;
  previous=value;Seconds=value.min;MaxSeconds=value.max;
  if(old==null||value.at-old.at<350||value.at-old.at>5000||value.min>=old.min)return false;
  long oldEnd=old.at+old.min*1000L,end=value.at+value.min*1000L;
  // Quantization, capture timing and a one-digit ambiguity must agree within 2 s.
  if(Math.Abs(end-oldEnd)>2000)return false;
  long check=Math.Min(Math.Min(end,oldEnd)-1500,now+30000);
  if(check-now<750)return false;
  StartedAt=now;CheckAt=check;return true;
 }
 // Allow a bounded masked capture at the deadline before the ordinary lease
 // rule resumes. The independent watchdog still receives only short leases.
 public bool KeepsCovered(long now)=>CheckAt>0&&now>=StartedAt&&now<CheckAt+4000;
 public bool Waiting(long now)=>KeepsCovered(now)&&now<CheckAt;
}
