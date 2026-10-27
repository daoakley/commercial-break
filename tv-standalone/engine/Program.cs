using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Net;
using System.Net.WebSockets;
using System.Diagnostics;
using System.Collections.Generic;
using System.Linq;
class Program {
 const string Home="/opt/usr/home/owner/commercial-block", State="/run/commercial-block";
 static readonly object Gate=new object();
 static bool Enabled=false, Covered=false, OwnMute=false;
 static readonly Queue<object> Events=new Queue<object>();
 static long LastAccepted=0, Covers=0, SteadyCardMatches=0, MaskedFallbacks=0;
 static string CaptureMode="normal";
 static void Record(string kind,string reason){lock(Gate){Events.Enqueue(new{at=Now(),kind,reason});while(Events.Count>180)Events.Dequeue();File.WriteAllText(State+"/events.json",JsonSerializer.Serialize(Events.ToArray()));Debug?.Event(kind,reason);}}
 static long LastAd=0, Queries=0, Matches=0, LastNavigation=0, Generation=0;
 static string Message="Off", LastApp="", Stage="idle", LastError="";
 static JsonElement Config;
 static ClientWebSocket Socket;
 static Process Overlay, Navigation, Watchdog;
 static string Token;
 static DebugRecords Debug;
 static ThemeSettings Themes;
 static string CoverTheme="default";
 static long ContextSince=0, CoverSince=0;
 static string ArtMode="unknown";static long ArtObserved=0;
 static async Task ArtMonitor(){using(var http=new System.Net.Http.HttpClient(){Timeout=TimeSpan.FromMilliseconds(500)}){while(true){try{string text=await http.GetStringAsync("http://127.0.0.1:47791/status");if(text.Length<262144){var d=JsonDocument.Parse(text).RootElement;string mode=d.GetProperty("guard").GetProperty("artMode").GetString();ArtMode=mode=="on"||mode=="off"?mode:"unknown";ArtObserved=Now();}}catch{ArtMode="unknown";}await Task.Delay(2000);}}}

 static readonly Queue<object> BreakHistory=new Queue<object>();
 sealed class PendingDebug { public DebugRecords.Ticket ticket; public object before; public string app,mode,error,verdict; public long navigation,generation,captureStarted,requestAt,responseAt; public JsonElement? fingerprint,response; public object diagnostics; }
 static readonly List<PendingDebug> Pending=new List<PendingDebug>();
 static object Unknown(string reason)=>new{value=(string)null,source="unavailable",confidence=(double?)null,reason};
 static object Context()=>new{
  observedAt=Now(),artMode=new{value=Now()-ArtObserved<6000?ArtMode:"unknown",observedAt=ArtObserved,source="Frame Home Art Mode guard, when available"},foregroundApp=new{value=LastApp,source="TV foreground-app state"},session=new{appFirstObservedAt=ContextSince,navigationGeneration=LastNavigation,engineGeneration=Generation},
  channel=Unknown("No verified channel metadata source connected"),show=new{title=Unknown("No verified program metadata source connected"),category=Unknown("Not inferred from a commercial match"),scheduledStart=Unknown("No schedule feed connected"),scheduledEnd=Unknown("No schedule feed connected"),firstObservedAt=(long?)null},
  source=new{configuredTvSource=Config.GetProperty("identity").GetProperty("sourceInfo").ToString(),authority="Device configuration; not proof of current channel"},
  ads=new{lastAcceptedMatchAt=LastAccepted==0?(long?)null:LastAccepted,secondsSinceLastMatch=LastAccepted==0?(double?)null:(Now()-LastAccepted)/1000.0,currentCoverStartedAt=CoverSince==0?(long?)null:CoverSince,currentCoverDurationSeconds=CoverSince==0?(double?)null:(Now()-CoverSince)/1000.0,observedCoverIntervals=BreakHistory.ToArray(),actualLastAdStart=Unknown("Cover timing is detection timing, not ground-truth ad onset"),expectedNextAd=Unknown("No validated prediction in TV-only engine")},
  controls=new{enabled=Enabled,covered=Covered,ownedMute=OwnMute},counters=new{queries=Queries,matches=Matches,covers=Covers},software=new{app="Commercial Break",version="0.2.0",initialCheckTargetMs=1000,releaseAfterLastMatchMs=8000,queryType=1,fingerprintVersion="1.2",maxMatchDistance=15,aiUsed=false,localPreprocessor="none"}};
 static void FlushDebug(){foreach(var p in Pending){Debug?.Complete(p.ticket,new{capture=new{captureStartedAt=p.captureStarted,fingerprintAt=p.fingerprint.HasValue&&p.fingerprint.Value.TryGetProperty("at",out var t)?(long?)t.GetInt64():null,mode=p.mode,imageWidth=480,imageHeight=270,imageContent=p.mode=="card-visible"?"cover card may obscure program; exclude from content labels":"underlying picture requested",imageAndFingerprintAreSeparateCapturePaths=true,diagnostics=p.diagnostics},fingerprint=p.fingerprint,samsung=new{requestAt=p.requestAt,responseAt=p.responseAt,roundTripMs=p.responseAt>0?(long?)(p.responseAt-p.requestAt):null,response=p.response,verdict=p.verdict,error=p.error},contextBefore=p.before,decision=new{evaluatedAt=Now(),sameSession=Enabled&&Generation==p.generation&&LastNavigation==p.navigation&&LastApp==p.app,covered=Covered,ownedMute=OwnMute,lastAcceptedAt=LastAccepted,reason=Message},contextAfter=Context()});}Pending.Clear();}
 static async Task DebugMaintenance(){while(true){try{Debug?.Maintain();}catch{}await Task.Delay(1000);}}

 static long Now()=>DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
 static string Run(string file,string args,int timeout=2500) {
  using(var p=new Process()) {
   p.StartInfo=new ProcessStartInfo(file,args){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
   p.Start();var output=p.StandardOutput.ReadToEndAsync();var errors=p.StandardError.ReadToEndAsync();if(!p.WaitForExit(timeout)){try{p.Kill();}catch{} throw new TimeoutException();}
   if(p.ExitCode!=0)throw new IOException("command failed");return output.GetAwaiter().GetResult().Trim();
  }
 }
 static bool OtherActive(){try{return Now()-long.Parse(File.ReadAllText("/run/codex-commercial-muter/heartbeat").Trim())*1000<60000;}catch{return false;}}
 static string App(){try {string s=Run("/usr/bin/vconftool","get memory/appfw/current_fullscreen_appid");var i=s.IndexOf("value = ");return i<0?"":s.Substring(i+8).Split(' ')[0];}catch{return "";}}
 static void Release(string reason="reset"){lock(Gate){if(Covered||OwnMute)Record("release",reason);if(CoverSince>0){BreakHistory.Enqueue(new{start=CoverSince,end=Now(),durationSeconds=(Now()-CoverSince)/1000.0,endReason=reason,source="app cover intervals; not confirmed ad boundaries"});while(BreakHistory.Count>12)BreakHistory.Dequeue();CoverSince=0;}File.Delete(State+"/overlay-lease");File.Delete(State+"/overlay-pause");if(OwnMute&&!File.Exists(State+"/owned-mute"))OwnMute=false;if(OwnMute){try{Run("/usr/bin/busctl","--system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b false");OwnMute=false;File.Delete(State+"/owned-mute");}catch{}}Covered=false;LastAd=0;}}
 static Process Spawn(string file,string args){return Process.Start(new ProcessStartInfo(file,args){UseShellExecute=false});}
 static Process SpawnScript(string script){var info=new ProcessStartInfo("/bin/sh"){UseShellExecute=false};info.ArgumentList.Add("-c");info.ArgumentList.Add(script);return Process.Start(info);}
 static void Prepare(){
  File.WriteAllText(State+"/heartbeat",(Now()/1000).ToString());
  if(Navigation==null||Navigation.HasExited)Navigation=Spawn("/usr/bin/dotnet",Home+"/NavigationObserver.dll");
  if(Watchdog==null||Watchdog.HasExited)Watchdog=SpawnScript(File.ReadAllText(Home+"/watchdog.sh"));
 }
 static long NavigationAt(){try{return long.Parse(File.ReadAllText(State+"/navigation"));}catch{return 0;}}
 // The renderer stays alive, hidden, between leases. Retire stale artwork only
 // while uncovered so the next break uses the saved scene without flashing an
 // active break or losing the warm renderer when the theme has not changed.
 static void RefreshIdleOverlay(){
  if(Covered||Overlay==null||CoverTheme==Themes.EffectiveTheme)return;
  if(!Overlay.HasExited){Overlay.Kill();if(!Overlay.WaitForExit(1500))throw new IOException("Previous theme renderer did not exit");}
  Overlay.Dispose();Overlay=null;
 }
 static void Cover(){lock(Gate){if(!Enabled||OtherActive()||Now()-NavigationAt()<3000)return;RefreshIdleOverlay();if(!Covered){CoverSince=Now();Covers++;Record("cover","fresh ad match");
  string mute=Run("/usr/bin/busctl","--system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager GetSpeakerMute");
  if(mute.Trim()=="ii 0 0"){File.WriteAllText(State+"/owned-mute","1");Run("/usr/bin/busctl","--system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b true");OwnMute=true;}
 }File.WriteAllText(State+"/overlay-lease",Now().ToString());
 if(Overlay==null||Overlay.HasExited){CoverTheme=Themes.EffectiveTheme;Overlay=Spawn("/usr/bin/dotnet",Home+"/CommercialOverlayProbe.dll --seconds 0 --scene "+Themes.ResolveScene()+" --lease-file "+State+"/overlay-lease --pause-file "+State+"/overlay-pause --paused-ack-file "+State+"/overlay-paused-ack --standby-file "+State+"/heartbeat --navigation-file "+State+"/navigation");}
 Covered=true;}}
 static void Save(){File.WriteAllText(Home+"/enabled",Enabled?"1":"0");}
 static void Disable(string why){lock(Gate){Enabled=false;Generation++;Save();Debug?.Set(false);Release(why);foreach(var p in new[]{Overlay,Navigation,Watchdog})try{if(p!=null&&!p.HasExited)p.Kill();}catch{}File.Delete(State+"/heartbeat");Message=why;}}
 static bool IsAd(JsonElement response,string at){
  try{
   var acr=response.GetProperty("result").GetProperty("acr");var rc=acr.GetProperty("recog_content");
   if(!rc.GetProperty("matching").GetBoolean())return false;
   var matched=acr.GetProperty("result_frames").EnumerateArray().Where(f=>f.GetProperty("matching").GetBoolean()).ToList();
   var frames=matched.Where(f=>f.GetProperty("dist").GetInt32()>=0&&f.GetProperty("dist").GetInt32()<=15).ToList();
   if(frames.Count==0||!frames.Any(f=>f.TryGetProperty("tvt",out var ft)&&ft.GetProperty("utc").GetString()==at))return false;
   var candidates=new List<JsonElement>{rc.GetProperty("main")};candidates.AddRange(rc.GetProperty("multi").EnumerateArray());
   var ids=new HashSet<string>();
   foreach(var f in frames){if(f.TryGetProperty("tvt",out var ft)&&ft.GetProperty("utc").GetString()!=at)continue;foreach(var c in new[]{f.GetProperty("main")}.Concat(f.GetProperty("multi").EnumerateArray()))if(c.TryGetProperty("vid",out var v))ids.Add(v.ToString());}
   foreach(var c in candidates)if(c.TryGetProperty("vid",out var v)&&ids.Contains(v.ToString())&&c.GetProperty("content").GetProperty("type").GetString()=="AD")return true;
   if(matched.Any(f=>!f.TryGetProperty("tvt",out var ft)||ft.GetProperty("utc").GetString()!=at)||!rc.TryGetProperty("confidence",out var conf)||rc.GetProperty("tvt").GetProperty("utc").GetString()!=at||conf.GetProperty("tvt").GetProperty("utc").GetString()!=at)return false;
   var cc=new HashSet<string>(conf.GetProperty("cc").EnumerateArray().Where(c=>c.GetProperty("source").GetInt32()==4&&c.GetProperty("keepCnt").GetInt32()==0).Select(c=>c.GetProperty("vid").ToString()));
   return candidates.Any(c=>c.GetProperty("source").GetInt32()==4&&cc.Contains(c.GetProperty("vid").ToString())&&c.GetProperty("content").GetProperty("type").GetString()=="AD"&&c.GetProperty("content").GetProperty("ccType").GetString()=="AD");
  }catch{return false;}
 }
 static async Task<JsonElement> Exchange(object request){
  var data=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request));using(var stop=new CancellationTokenSource(2500)){
   await Socket.SendAsync(new ArraySegment<byte>(data),WebSocketMessageType.Text,true,stop.Token);
   using(var all=new MemoryStream()){var b=new byte[32768];WebSocketReceiveResult r;do{r=await Socket.ReceiveAsync(new ArraySegment<byte>(b),stop.Token);if(r.MessageType!=WebSocketMessageType.Text)throw new IOException("socket closed");all.Write(b,0,r.Count);if(all.Length>1048576)throw new IOException("response too large");}while(!r.EndOfMessage);return JsonDocument.Parse(all.ToArray()).RootElement.Clone();}
  }
 }
 static async Task<bool> Recognize(bool keepCard=false){
  Stage="connect";if(Socket==null||Socket.State!=WebSocketState.Open){Socket?.Dispose();Socket=new ClientWebSocket();using(var stop=new CancellationTokenSource(2500))await Socket.ConnectAsync(new Uri("wss://acr-us-prd.samsungcloud.tv/getacrinfo"),stop.Token);Stage="parameters";var p=await Exchange(Config.GetProperty("parameters"));if(p.GetProperty("server").GetProperty("fpVersion").GetDouble()!=1.2||!p.GetProperty("scte35Param").GetProperty("isMainQueryEnabled").GetBoolean())throw new IOException("recognition unavailable");}
  CaptureMode=Covered?(keepCard?"card-visible":"panel-masked"):"normal";
  var ticket=Debug?.Begin();PendingDebug debug=null;
  if(ticket!=null){debug=new PendingDebug{ticket=ticket,before=Context(),app=LastApp,mode=CaptureMode,navigation=NavigationAt(),generation=Generation,captureStarted=Now()};Pending.Add(debug);}
  try {
  Stage="capture";File.WriteAllText(State+"/acr-next-capture",(Now()/1000).ToString());
  using(var p=new Process()){
   p.StartInfo=new ProcessStartInfo("/usr/bin/dotnet",Home+"/AcrFrameProbe.dll"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
   p.StartInfo.Environment["LD_PRELOAD"]="/lib/libcapi-system-info.so.0:"+State+"/libtzcapturec-probe.so";
   p.StartInfo.Environment["CAPTURE_FINGERPRINT_ONLY"]="1";
   p.StartInfo.Environment["CAPTURE_KEEP_CARD"]=keepCard?"1":"0";
   if(ticket!=null)p.StartInfo.Environment["CAPTURE_DEBUG_ID"]=ticket.id;
   p.StartInfo.Environment["CAPTURE_OVERLAY_PAUSE_FILE"]=Covered?State+"/overlay-pause":"";
   p.StartInfo.Environment["CAPTURE_OVERLAY_ACK_FILE"]=Covered?State+"/overlay-paused-ack":"";
   p.Start();var output=p.StandardOutput.ReadToEndAsync();var errors=p.StandardError.ReadToEndAsync();if(!p.WaitForExit(4000)){try{p.Kill();}catch{}throw new TimeoutException();}if(p.ExitCode!=0)throw new IOException("capture unavailable");
  }
  Stage="fingerprint";var f=JsonDocument.Parse(Convert.FromBase64String(File.ReadAllText(State+"/acr-fingerprint"))).RootElement;
  if(debug!=null){debug.fingerprint=f.Clone();try{debug.diagnostics=JsonDocument.Parse(File.ReadAllText(State+"/capture-diagnostics.json")).RootElement.Clone();}catch{}}
  if(f.GetProperty("capture_rc").GetInt64()!=0||f.GetProperty("fingerprint_rc").GetInt64()!=0)throw new IOException("fingerprint unavailable");
  long at=f.GetProperty("at").GetInt64();if(Now()-at>5000||at-Now()>2000)throw new IOException("stale capture");int n=f.GetProperty("roi_count").GetInt32();byte[] raw=Convert.FromBase64String(f.GetProperty("raw_base64").GetString());if(n<1||n>10||raw.Length!=180)throw new IOException("invalid capture");
  var fps=new List<object>();for(int i=0;i<n;i++){var values=new List<uint>();for(int j=0;j<8;j+=2){int k=i*18+2+j*2;values.Add(((uint)BitConverter.ToUInt16(raw,k)<<16)|BitConverter.ToUInt16(raw,k+2));}fps.Add(new{roi=i,raws=values});}
  var id=Config.GetProperty("identity");var am=new Dictionary<string,object>();foreach(string k in new[]{"psid","vdvendorcode","modelID"})am[k]=id.GetProperty(k).Clone();am["power"]=1;am["tv_source"]=int.Parse(id.GetProperty("sourceInfo").ToString());am["source_APP_Id"]=LastApp;
  var frame=new{fps,tvt=new{utc=at.ToString(),tz=(int)TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow).TotalMinutes}};
  if(debug!=null)debug.requestAt=Now();
  Stage="query";var result=await Exchange(new{api=1,search=new{msg_ver="3.3",am,acr=new{retry_cnt=0,mtype=1,fp_ver="1.200000",query_type=1,query=new[]{frame}}}});
  if(debug!=null){debug.responseAt=Now();debug.response=result.Clone();}
  File.WriteAllText(State+"/last-reply.json",JsonSerializer.Serialize(new{at=at.ToString(),receivedAt=Now(),captureMode=CaptureMode,response=result}));
  if(!result.TryGetProperty("result",out var body)||!body.TryGetProperty("acr",out var acr))throw new IOException("invalid recognition reply");
  Queries++;LastError="";Stage="reply";bool ad=IsAd(result,at.ToString());Record("reply",ad?"ad":"unknown");if(debug!=null)debug.verdict=ad?"ad":"unknown";return ad;
  }catch(Exception error){if(debug!=null)debug.error=Stage+": "+error.GetType().Name;throw;}
 }
 static async Task Loop(){int failures=0;long next=0;
  while(true){try{
   if(!Enabled){await Task.Delay(500);continue;}
   if(OtherActive()){Disable("Other blocker is active — remaining off");continue;}
   Prepare();long navigation=NavigationAt();if(navigation!=LastNavigation){Release("navigation");LastNavigation=navigation;ContextSince=Now();}string app=App();if(app!=LastApp){Release("app change");LastApp=app;ContextSince=Now();}
   if(ArtMode=="on"&&Now()-ArtObserved<6000){Release("Art Mode");Message="Paused in Art Mode";await Task.Delay(1000);continue;}
   if(app!="com.samsung.tv.cobalt-yttv"){Release("outside YouTube TV");Message="Waiting for YouTube TV";await Task.Delay(1000);continue;}
   File.WriteAllText(State+"/heartbeat",(Now()/1000).ToString());
   if(Covered&&(!File.Exists(State+"/overlay-lease")||Now()-LastAd>=8000))Release("ad renewal expired or lease removed");
   if(Now()<next){await Task.Delay(200);continue;}
   long started=Now(), nav=NavigationAt(), generation=Generation;
   // First try the secure fingerprint with the existing card continuously
   // visible. Only a strict, fresh AD verdict renews that cover. An uncertain
   // result immediately falls back to the established masked capture path.
   bool trySteady=Covered;bool ad=await Recognize(trySteady);
   bool sameSession=Enabled&&generation==Generation&&nav==NavigationAt()&&App()==LastApp;
   if(trySteady&&sameSession){
    if(ad)SteadyCardMatches++;
    else {MaskedFallbacks++;ad=await Recognize(false);}
   }
   failures=0;next=started+1000;
   lock(Gate){if(!Enabled||generation!=Generation)continue;if(App()!=LastApp||nav!=NavigationAt()){Release("navigation during query");Record("discard","navigation during query");continue;}if(ad){Matches++;LastAccepted=LastAd=Now();Cover();Message="Commercial matched";}else Message=Covered?"Waiting for another match":"Watching — no confirmed ad";}
  }catch(Exception error){LastError=Stage+": "+error.GetType().Name+"/"+error.GetBaseException().GetType().Name;Console.Error.WriteLine(LastError);Record("error",LastError);Release("recognition error");Socket?.Dispose();Socket=null;failures++;next=Now()+Math.Min(60000,2000*(1<<Math.Min(failures,5)));Message="Recognition unavailable — playback released";await Task.Delay(500);}finally{try{FlushDebug();}catch{Pending.Clear();}}}
 }
 static object Status()=>new{enabled=Enabled,covered=Covered,otherActive=OtherActive(),message=Message,stage=Stage,lastError=LastError,lastAcceptedAt=LastAccepted,covers=Covers,captureMode=CaptureMode,steadyCardMatches=SteadyCardMatches,maskedFallbacks=MaskedFallbacks,queries=Queries,matches=Matches,engine="Samsung recognition only",releaseSeconds=8,persistentApp=true,rebootReady=false,appearance=new{theme=Themes?.Selected??"default",effectiveTheme=Themes?.EffectiveTheme??"default",activeTheme=Covered?CoverTheme:null},debug=Debug?.Status()};
 static async Task Serve(){var h=new HttpListener();h.Prefixes.Add("http://127.0.0.1:18764/");h.Start();while(true){var c=await h.GetContextAsync();try{
  c.Response.Headers.Add("Access-Control-Allow-Origin","*");c.Response.Headers.Add("Access-Control-Allow-Methods","GET, POST, OPTIONS");c.Response.Headers.Add("Access-Control-Allow-Headers","Authorization, Content-Type");
  if(c.Request.HttpMethod=="OPTIONS"){c.Response.StatusCode=204;c.Response.Close();continue;}
  if(c.Request.Headers["Authorization"]!="Bearer "+Token){c.Response.StatusCode=401;c.Response.Close();continue;}
  if(c.Request.Url.AbsolutePath=="/appearance"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   lock(Gate){Themes.Set(body.GetProperty("theme").GetString());}
  }else if(c.Request.Url.AbsolutePath=="/debug"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   Debug.Set(body.GetProperty("enabled").GetBoolean());
  }else if(c.Request.Url.AbsolutePath=="/control"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   lock(Gate){if(body.GetProperty("enabled").GetBoolean()){if(OtherActive()){c.Response.StatusCode=409;Message="Stop the other blocker before enabling";}else{Generation++;Enabled=true;Save();Message="Enabled";}}else Disable("Off");}
  }else if(c.Request.Url.AbsolutePath!="/status"){c.Response.StatusCode=404;c.Response.Close();continue;}
  byte[] b=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(Status()));c.Response.ContentType="application/json";await c.Response.OutputStream.WriteAsync(b,0,b.Length);c.Response.Close();
 }catch{try{c.Response.StatusCode=400;c.Response.Close();}catch{}}}}
 static int Main(string[] args){
  if(args.Length==3&&args[0]=="--classify"){Console.WriteLine(IsAd(JsonDocument.Parse(File.ReadAllText(args[1])).RootElement,args[2])?"ad":"uncertain");return 0;}
  if(args.Length==2&&args[0]=="--replay"){foreach(var item in JsonDocument.Parse(File.ReadAllText(args[1])).RootElement.EnumerateArray())Console.WriteLine(IsAd(item.GetProperty("response"),item.GetProperty("at").GetString())?"ad":"uncertain");return 0;}
  Directory.CreateDirectory(State);Themes=new ThemeSettings(Home);Config=JsonDocument.Parse(File.ReadAllText(Home+"/device.json")).RootElement.Clone();Token=Config.GetProperty("controlToken").GetString();
  using(var single=new FileStream(State+"/engine.lock",FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None)){
   File.Copy(Home+"/libtzcapturec-probe.so",State+"/libtzcapturec-probe.so",true);
   Debug=new DebugRecords(Home,State,Now);var cleanup=Task.Run(DebugMaintenance);var artMonitor=Task.Run(ArtMonitor);
   Enabled=false;OwnMute=File.Exists(State+"/owned-mute");Release();Save();Message="Off — experimental Samsung-only version";
   var loop=Task.Run(Loop);Serve().GetAwaiter().GetResult();
  }return 0;
 }
}
