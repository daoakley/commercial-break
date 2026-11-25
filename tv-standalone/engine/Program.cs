using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Net;
using System.Diagnostics;
using System.Collections.Generic;
using System.Linq;
partial class Program {
 const string Home="/opt/usr/home/owner/commercial-block", State="/run/commercial-block";
 static readonly object Gate=new object();
 static bool Enabled=false, Covered=false, OwnMute=false;
 static readonly Queue<object> Events=new Queue<object>();
 static long LastAccepted=0, Covers=0, SteadyCardMatches=0, MaskedFallbacks=0;
 static string CaptureMode="normal", LastMatchSource="none";
 static long LocalChecks=0, LocalHits=0;
 static long YouTubeChecks=0,YouTubeHits=0,YouTubeSkipAttempts=0,YouTubeSkipFrame=0;
 static bool YouTubeAutoSkip=false;
 static readonly YouTubeCountdownHold Countdown=new YouTubeCountdownHold();
 static YouTubeCountdownHold.Reading TimerEvidence;
 static long CountdownHolds=0;
 static string YouTubeSkipStatus="off";
 static YouTubeSkipGuard SkipGuard;
 static long ReadSkipAttempt(){try{return long.Parse(File.ReadAllText(Home+"/youtube-skip-last-attempt").Trim());}catch{return 0;}}
 static void SetYouTubeSkip(bool enabled){lock(Gate){File.WriteAllText(Home+"/youtube-skip-enabled.tmp",enabled?"1":"0");File.Move(Home+"/youtube-skip-enabled.tmp",Home+"/youtube-skip-enabled",true);YouTubeAutoSkip=enabled;YouTubeSkipStatus=enabled?"ready":"off";Record("youtube-skip-control",enabled?"automatic Skip enabled":"automatic Skip disabled");}}
 static bool TryYouTubeSkip(long navigation,long generation){
  long now=Now();bool same=Generation==generation&&NavigationAt()==navigation&&App()==LastApp;
  if(SkipGuard==null||OtherActive()||!SkipGuard.TryAttempt(now,YouTubeSkipFrame,Enabled&&YouTubeAutoSkip,IsRegularYouTube(LastApp),LastMatchSource=="youtube-ui-skip",now-navigation,same))return false;
  try {
   // Persist before sending: a crash or restart must not cause repeated Select presses.
   File.WriteAllText(Home+"/youtube-skip-last-attempt.tmp",now.ToString());File.Move(Home+"/youtube-skip-last-attempt.tmp",Home+"/youtube-skip-last-attempt",true);
   if(NavigationAt()!=navigation||App()!=LastApp||Now()-YouTubeSkipFrame>1500){YouTubeSkipStatus="cancelled-context-changed";return false;}
   YouTubeSkipAttempts++;Generation++;
   File.WriteAllText(State+"/navigation.tmp",Now().ToString());File.Move(State+"/navigation.tmp",State+"/navigation",true);
   Release("YouTube Skip selected");
   string down="",up="";
   try{down=Run("/usr/bin/busctl","--system --timeout=1 call org.enlightenment.wm /org/enlightenment/wm org.enlightenment.wm.Test EventKey us 1 Return",1500);}
   finally{up=Run("/usr/bin/busctl","--system --timeout=1 call org.enlightenment.wm /org/enlightenment/wm org.enlightenment.wm.Test EventKey us 0 Return",1500);}
   YouTubeSkipStatus=down=="b true"&&up=="b true"?"select-sent":"key-rejected";
   Record("youtube-skip",YouTubeSkipStatus+"; one attempt; frame age "+(Now()-YouTubeSkipFrame)+" ms");Message=YouTubeSkipStatus=="select-sent"?"Selected YouTube Skip":"Skip unavailable — use the remote";
   return true;
  }catch(Exception error){YouTubeSkipStatus="failed-no-retry";Health?.Error("youtube-skip",error);Record("youtube-skip","command failed; no automatic retry this break");return false;}
 }
 static string LastYouTubeUi="unknown";static double LastYouTubeMillis=0;
 static double LastPillScore=0, LastPillMillis=0;
 static volatile bool LayoutEnabled=false;
 static Process LayoutWorker;
 static int LayoutWorkerFailures=0,LayoutNoReplies=0;
 static long LayoutWorkerStarted=0;
 // Audio splice observer: a separate helper that reads the TV's audio tap (hw:0,5) and reports
 // digital-null splices through State/audio-splice.json. Mode 0 off; 1 shadow (recorded only);
 // 2 primary trigger, bounded by the existing eight-second renewal rule. The helper itself never
 // mutes, covers or changes settings. A silent tap (sound routed away from the speaker path)
 // yields no verdicts and is reported as tapSilent.
 static Process Audio; static int AudioMode=0, AudioFailures=0;
 static long AudioStarted=0, AudioExitedAt=0, AudioTriggers=0, AudioCovers=0, LastAudioTriggerAt=0, LastAudioDecision=0, LastAudioStateAt=0;
 static bool AudioSilent=false; static string AudioError="";
 static int ReadAudioMode(){try{int m=int.Parse(File.ReadAllText(Home+"/audio-enabled").Trim());return m>=0&&m<=3?m:0;}catch{return 0;}}
 static void StopAudio(){try{if(Audio!=null&&!Audio.HasExited)Audio.Kill();}catch{}Audio?.Dispose();Audio=null;foreach(string name in new[]{"audio-splice.json","audio-splice-state.json"})try{File.Delete(State+"/"+name);}catch{}}
 static void SetAudio(int mode){lock(Gate){
  if(mode<0||mode>3)throw new ArgumentException("mode");
  if(mode!=0&&!File.Exists(Home+"/AudioSpliceObserver.dll"))throw new IOException("audio observer unavailable");
  File.WriteAllText(Home+"/audio-enabled.tmp",mode.ToString());File.Move(Home+"/audio-enabled.tmp",Home+"/audio-enabled",true);
  AudioMode=mode;AudioError="";if(mode==0)StopAudio();else AudioFailures=0;
  if(mode!=2&&Covered&&LastMatchSource=="audio-splice")Release("audio primary disabled");
  Record("audio-control","audio splice mode "+mode);
 }}
 static void AudioReady(){
  if(Audio!=null&&Audio.HasExited){Audio.Dispose();Audio=null;AudioExitedAt=Now();AudioFailures++;if(AudioFailures>=5){AudioError="audio observer exited repeatedly; audio disabled";SetAudio(0);return;}}
  if(Audio==null&&Now()-AudioExitedAt>=30000){AudioStarted=Now();Audio=Spawn("/usr/bin/dotnet",Home+"/AudioSpliceObserver.dll --device hw:0,5 --result "+State+"/audio-splice.json --state "+State+"/audio-splice-state.json --log "+Home+"/diagnostics/audio-splice.jsonl --stats-every 30 --floor "+AudioFloor());}
 }
 static async Task AudioPump(){while(true){try{if(Enabled&&AudioMode!=0)AudioPoll();}catch(Exception e){Health?.Error("audio-poll",e);}await Task.Delay(200);}}
 static long AudioSetting(string name,long fallback,long lo,long hi){try{long v=long.Parse(File.ReadAllText(Home+"/"+name).Trim());return v>=lo&&v<=hi?v:fallback;}catch{return fallback;}}
 // Acting-mode gates: a splice may open a cover only after a quiet stretch with no audio trigger (scene-change clusters
 // and ad-to-ad splices never qualify), and not during the cool-down that follows an audio cover nothing confirmed.
 static long LastUnconfirmedAudioAt=0, AudioUnconfirmed=0, AudioSuppressed=0; static bool AudioCoverConfirmed=false;
 // Mode 3: an audio splice arms a short burst of back-to-back recognition cycles, only while no cover is up.
 // A cover ending the burst, or a splice arriving during a break, never changes the covered-state cadence,
 // so the masked-capture fallback (the visible blink) is not used more often than today.
 static long AudioArmedUntil=0, AudioArms=0, AudioArmHits=0;
 static string AudioFloor(){try{string v=File.ReadAllText(Home+"/audio-floor").Trim();double f=double.Parse(v,System.Globalization.CultureInfo.InvariantCulture);return f<=-60&&f>=-100?v:"-75";}catch{return "-75";}}
 static void AudioPoll(){lock(Gate){
  if(AudioMode==0||MaintenancePaused)return;AudioReady();
  try{var st=JsonDocument.Parse(File.ReadAllText(State+"/audio-splice-state.json")).RootElement;LastAudioStateAt=st.GetProperty("at").GetInt64();AudioSilent=st.GetProperty("silent").GetBoolean();if(Now()-AudioStarted>600000)AudioFailures=0;}catch{}
  JsonElement row;long decision;
  try{row=JsonDocument.Parse(File.ReadAllText(State+"/audio-splice.json")).RootElement.Clone();decision=row.GetProperty("decisionMs").GetInt64();}catch{return;}
  if(decision<=LastAudioDecision)return;LastAudioDecision=decision;long now=Now();
  if(now-decision>3000||decision-now>2000){Record("audio-stale","audio trigger ignored; decided "+(now-decision)+" ms ago");return;}
  long quietMs=LastAudioTriggerAt==0?long.MaxValue:now-LastAudioTriggerAt;AudioTriggers++;LastAudioTriggerAt=now;
  string info="audio splice trigger";try{info="null "+row.GetProperty("durMs").GetInt64()+" ms to "+row.GetProperty("floorDb").GetDouble().ToString("F0",System.Globalization.CultureInfo.InvariantCulture)+" dBFS, post mid/side "+row.GetProperty("postMidSideDb").GetDouble().ToString("F1",System.Globalization.CultureInfo.InvariantCulture)+" dB, decided "+(now-decision)+" ms ago";}catch{}
  Record("audio-splice",info+(Covered?"; already covered":""));
  if(AudioMode==2&&Enabled&&!AudioSilent&&!Covered&&LastApp=="com.samsung.tv.cobalt-yttv"&&App()==LastApp&&decision>=NavigationAt()&&!(ArtMode=="on"&&now-ArtObserved<6000)&&!OtherActive()&&Now()-NavigationAt()>=3000){
   long quietNeed=AudioSetting("audio-quiet",60,0,3600)*1000,cool=AudioSetting("audio-cooldown",300,0,3600)*1000;
   if(quietMs<quietNeed){AudioSuppressed++;Record("audio-suppressed","previous trigger "+(quietMs/1000)+" s ago, quiet gate "+(quietNeed/1000)+" s");return;}
   if(LastUnconfirmedAudioAt>0&&now-LastUnconfirmedAudioAt<cool){AudioSuppressed++;Record("audio-suppressed","cool-down: unconfirmed audio cover "+((now-LastUnconfirmedAudioAt)/1000)+" s ago, gate "+(cool/1000)+" s");return;}
   ActiveCaptureId=Timing.Begin();ActiveCaptureStarted=DetectionTiming.Clock;LastMatchSource="audio-splice";LastAd=Now();Cover();
   if(Covered){AudioCovers++;Message="Audio splice — awaiting confirmation";Record("audio-cover","cover on audio splice; releases after 8 s without a confirming match");Next=0;}
  }
  if(AudioMode==3&&Enabled&&!AudioSilent&&!Covered&&LastApp=="com.samsung.tv.cobalt-yttv"&&App()==LastApp&&decision>=NavigationAt()&&!(ArtMode=="on"&&now-ArtObserved<6000)&&!OtherActive()&&Now()-NavigationAt()>=3000&&now>=AudioArmedUntil){
   long arm=AudioSetting("audio-arm",5,1,30);AudioArmedUntil=now+arm*1000;AudioArms++;Next=0;Record("audio-armed","burst recognition for "+arm+" s while uncovered");
  }
 }}
 static void StopLayoutWorker(){
  try{if(LayoutWorker!=null&&!LayoutWorker.HasExited)LayoutWorker.Kill();}catch{}
  LayoutWorker?.Dispose();LayoutWorker=null;
  foreach(string name in new[]{"layout-ready","layout-frame.bin","layout-frame.bin.tmp","layout-processing.bin","layout-result.json"})try{File.Delete(State+"/"+name);}catch{}
 }
 static bool LayoutReady(){lock(Gate){
  if(!LayoutEnabled)return false;
  if(LayoutWorker!=null&&(LayoutWorker.HasExited||(!File.Exists(State+"/layout-ready")&&Now()-LayoutWorkerStarted>5000))){
   StopLayoutWorker();LayoutWorkerFailures++;
   if(LayoutWorkerFailures>=3){LayoutError="layout worker unavailable; experiment disabled";SetLayout(false);return false;}
  }
  if(LayoutWorker==null){
   File.Delete(State+"/layout-ready");LayoutWorkerStarted=Now();
   LayoutWorker=Spawn("/usr/bin/dotnet",Home+"/AcrFrameProbe.dll --layout-worker "+Process.GetCurrentProcess().Id);
  }
  return !LayoutWorker.HasExited&&File.Exists(State+"/layout-ready");
 }}
 static long LayoutChecks=0,LayoutHits=0;
 static double LastLayoutScore=0,LastLayoutMillis=0;
 static string LayoutError="",LastLayoutModel="";
 static bool IsYouTubeTv(string app)=>app=="com.samsung.tv.cobalt-yttv";
 static bool IsRegularYouTube(string app)=>app=="com.samsung.tv.cobalt-yt";
 static bool IsSupportedApp(string app)=>IsYouTubeTv(app)||IsRegularYouTube(app);
 static bool IsYouTubeUi(JsonElement p,long started,long now,bool keepCard,string app){try{
  long at=p.GetProperty("at").GetInt64();double ms=p.GetProperty("elapsedMs").GetDouble(),countdown=p.GetProperty("countdownScore").GetDouble(),skip=p.GetProperty("skipScore").GetDouble();string state=p.GetProperty("state").GetString(),kind=p.GetProperty("controlKind").GetString();
  bool circle=kind=="circle"&&YouTubeDetectionPolicy.Circle(p.GetProperty("circleDigitPixels").GetInt32(),p.GetProperty("circleRingPixels").GetInt32(),p.GetProperty("circleRows").GetInt32(),p.GetProperty("circleColumns").GetInt32(),p.GetProperty("circleSectors").GetInt32(),p.GetProperty("circleNoise").GetInt32());
  return IsRegularYouTube(app)&&!keepCard&&!p.GetProperty("keepCard").GetBoolean()&&p.GetProperty("detector").GetString()==YouTubeDetectionPolicy.Detector&&p.GetProperty("hit").GetBoolean()&&at>=started&&now>=at&&now-at<=5000&&ms>=0&&ms<=500&&
   ((state=="countdown"&&(circle||(kind=="skip-in"&&countdown>=.90&&countdown<=1.000001&&p.GetProperty("yellowPixels").GetInt32()>=5)))||(state=="skip"&&kind=="skip"&&skip>=.95&&skip<=1.000001&&p.GetProperty("skipReady").GetBoolean()));
 }catch{return false;}}
 // Broadcast-trained checks are deliberately restricted to their validated app.
 static bool IsLayout(JsonElement p,long started,long now,bool keepCard,bool enabled,string app){try{
  long at=p.GetProperty("at").GetInt64();double score=p.GetProperty("score").GetDouble();double elapsed=p.GetProperty("elapsedMs").GetDouble();
  return IsYouTubeTv(app)&&enabled&&!keepCard&&!p.GetProperty("keepCard").GetBoolean()&&p.GetProperty("detector").GetString()=="ad-layout-141-v1"&&p.GetProperty("modelId").GetString()=="forward-49-20261027"&&p.GetProperty("hit").GetBoolean()&&p.GetProperty("threshold").GetDouble()==0.5&&!double.IsNaN(score)&&!double.IsInfinity(score)&&score>=0.5&&elapsed>=0&&elapsed<=1500&&at>=started&&now-at>=0&&now-at<=5000;
 }catch{return false;}}
 static void SetLayout(bool enabled){lock(Gate){
  if(enabled&&!File.Exists(Home+"/layout-model.json"))throw new IOException("layout model unavailable");
  File.WriteAllText(Home+"/layout-enabled.tmp",enabled?"1":"0");File.Move(Home+"/layout-enabled.tmp",Home+"/layout-enabled",true);
  LayoutEnabled=enabled;Generation++;
  if(!enabled)StopLayoutWorker();else {LayoutWorkerFailures=0;LayoutNoReplies=0;}
  if(!enabled&&Covered&&LastMatchSource=="experimental-layout")Release("experimental layout disabled");
  Record("layout-control",enabled?"experimental layout enabled":"experimental layout disabled");
 }}
 // Result must belong to this capture invocation, never a retained file or covered card.
 static bool IsPill(JsonElement p,long started,long now,bool keepCard,string app){try{
  long at=p.GetProperty("at").GetInt64();double score=p.GetProperty("score").GetDouble();
  return IsYouTubeTv(app)&&!keepCard&&!p.GetProperty("keepCard").GetBoolean()&&p.GetProperty("detector").GetString()=="youtube-tv-sponsored-v1"&&p.GetProperty("hit").GetBoolean()&&
   p.GetProperty("threshold").GetDouble()==300&&!double.IsNaN(score)&&!double.IsInfinity(score)&&score>=300&&at>=started&&now-at>=0&&now-at<=5000;
 }catch{return false;}}
 static void Record(string kind,string reason){try{lock(Gate){Events.Enqueue(new{at=Now(),kind,reason});while(Events.Count>180)Events.Dequeue();File.WriteAllText(State+"/events.json",JsonSerializer.Serialize(Events.ToArray()));Debug?.Event(kind,reason);if(kind!="reply"&&kind!="discard")Decisions(kind,reason);}}catch(Exception e){Health?.Error("event-write",e);}}
 // Durable, bounded per-block log that outlives the debug session: covers with their source, confirmations, releases, audio events.
 static string CoverSource="none";
 static void Decisions(string kind,string reason){try{string p=Home+"/diagnostics/decisions.jsonl";var f=new FileInfo(p);if(f.Exists&&f.Length>1048576)File.Move(p,p+".1",true);File.AppendAllText(p,JsonSerializer.Serialize(new{at=Now(),kind,reason,covered=Covered,coverSource=CoverSource,coverSince=CoverSince==0?(long?)null:CoverSince,lastMatchSource=LastMatchSource,audioMode=AudioMode})+"\n");}catch{}}
 static long LastAd=0, Queries=0, Matches=0, LastNavigation=0, Generation=0;
 static string Message="Off", LastApp="", Stage="idle", LastError="";
 static JsonElement Config;

 static Process Overlay, Navigation, Watchdog;
 static string Token;
 static DebugRecords Debug;
 static ThemeSettings Themes;
 static EngineHealth Health;
 static string CoverTheme="default";
 static long ContextSince=0, CoverSince=0;
 static string ArtMode="unknown";static long ArtObserved=0;
 static async Task ArtMonitor(){using(var http=new System.Net.Http.HttpClient(){Timeout=TimeSpan.FromMilliseconds(500)}){while(true){try{string text=await http.GetStringAsync("http://127.0.0.1:47791/status");if(text.Length<262144){var d=JsonDocument.Parse(text).RootElement;string mode=d.GetProperty("guard").GetProperty("artMode").GetString();ArtMode=mode=="on"||mode=="off"?mode:"unknown";ArtObserved=Now();}}catch{ArtMode="unknown";}await Task.Delay(2000);}}}

 static readonly Queue<object> BreakHistory=new Queue<object>();
 sealed class PendingDebug { public DebugRecords.Ticket ticket; public object before; public string app,mode,error,verdict; public long navigation,generation,captureStarted,requestAt,responseAt; public bool remotePending; public JsonElement? fingerprint,response,pill,layout,youtube; public object diagnostics; }
 static readonly List<PendingDebug> Pending=new List<PendingDebug>();
 static object Unknown(string reason)=>new{value=(string)null,source="unavailable",confidence=(double?)null,reason};
 static object Context()=>new{
  observedAt=Now(),artMode=new{value=Now()-ArtObserved<6000?ArtMode:"unknown",observedAt=ArtObserved,source="Frame Home Art Mode guard, when available"},foregroundApp=new{value=LastApp,source="TV foreground-app state"},session=new{appFirstObservedAt=ContextSince,navigationGeneration=LastNavigation,engineGeneration=Generation},
  channel=Unknown("No verified channel metadata source connected"),show=new{title=Unknown("No verified program metadata source connected"),category=Unknown("Not inferred from a commercial match"),scheduledStart=Unknown("No schedule feed connected"),scheduledEnd=Unknown("No schedule feed connected"),firstObservedAt=(long?)null},
  source=new{configuredTvSource=Config.GetProperty("identity").GetProperty("sourceInfo").ToString(),authority="Device configuration; not proof of current channel"},
  ads=new{lastAcceptedMatchAt=LastAccepted==0?(long?)null:LastAccepted,secondsSinceLastMatch=LastAccepted==0?(double?)null:(Now()-LastAccepted)/1000.0,currentCoverStartedAt=CoverSince==0?(long?)null:CoverSince,currentCoverDurationSeconds=CoverSince==0?(double?)null:(Now()-CoverSince)/1000.0,observedCoverIntervals=BreakHistory.ToArray(),actualLastAdStart=Unknown("Cover timing is detection timing, not ground-truth ad onset"),expectedNextAd=Unknown("No validated prediction in TV-only engine")},
  audio=new{mode=AudioMode,triggers=AudioTriggers,covers=AudioCovers,lastTriggerAt=LastAudioTriggerAt==0?(long?)null:LastAudioTriggerAt,tapSilent=AudioSilent,rule="deep75_60-1500ms_post_not_mono"},
  controls=new{enabled=Enabled,covered=Covered,ownedMute=OwnMute},counters=new{queries=Queries,matches=Matches,covers=Covers},software=new{app="Commercial Break",version=DetectionTiming.Version,build=Build,initialCheckTargetMs=YouTubeDetectionPolicy.IntervalMs(LastApp),samsungRecognition=YouTubeDetectionPolicy.UsesSamsung(LastApp),releaseAfterLastMatchMs=8000,queryType=1,fingerprintVersion="1.2",maxMatchDistance=15,aiUsed=false,localPreprocessor=IsRegularYouTube(LastApp)?YouTubeDetectionPolicy.Detector:"youtube-tv-sponsored-v1",youtubeAutoSkip=YouTubeAutoSkip,experimentalLayoutEnabled=LayoutEnabled,experimentalLayoutModel="forward-49-20261027"}};
 static void FlushDebug(){foreach(var p in Pending.Where(item=>!item.remotePending).ToArray()){Debug?.Complete(p.ticket,new{capture=new{captureStartedAt=p.captureStarted,fingerprintAt=p.fingerprint.HasValue&&p.fingerprint.Value.TryGetProperty("at",out var t)?(long?)t.GetInt64():null,mode=p.mode,imageWidth=480,imageHeight=270,imageContent=p.mode=="card-visible"?"cover card may obscure program; exclude from content labels":"underlying picture requested",imageAndFingerprintAreSeparateCapturePaths=true,diagnostics=p.diagnostics},localDetection=p.pill,youtubeControls=p.youtube,experimentalLayout=p.layout,fingerprint=p.fingerprint,samsung=new{requestAt=p.requestAt,responseAt=p.responseAt,roundTripMs=p.responseAt>0?(long?)(p.responseAt-p.requestAt):null,response=p.response,verdict=p.verdict,error=p.error},contextBefore=p.before,decision=new{evaluatedAt=Now(),sameSession=Enabled&&Generation==p.generation&&LastNavigation==p.navigation&&LastApp==p.app,covered=Covered,ownedMute=OwnMute,lastAcceptedAt=LastAccepted,reason=Message},contextAfter=Context()});Pending.Remove(p);}}
 static async Task DebugMaintenance(){while(true){try{Debug?.Maintain();Timing?.Flush();}catch{}await Task.Delay(1000);}}

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
 static void Release(string reason="reset"){lock(Gate){if(Covered)Timing?.Record(CoverCaptureId,DetectionStage.Released,CoverCaptureStarted);if(Covered)Archive.Released(Now());MaskedLooks.Reset();if(Covered&&CoverSource=="audio-splice"&&!AudioCoverConfirmed){LastUnconfirmedAudioAt=Now();AudioUnconfirmed++;Record("audio-unconfirmed","audio cover released after "+(Now()-CoverSince)+" ms without confirmation; cool-down "+AudioSetting("audio-cooldown",300,0,3600)+" s");}if(Covered||OwnMute)Record("release",reason);if(CoverSince>0){BreakHistory.Enqueue(new{start=CoverSince,end=Now(),durationSeconds=(Now()-CoverSince)/1000.0,endReason=reason,source="app cover intervals; not confirmed ad boundaries"});while(BreakHistory.Count>12)BreakHistory.Dequeue();CoverSince=0;}File.Delete(State+"/overlay-lease");File.Delete(State+"/overlay-pause");if(OwnMute&&!File.Exists(State+"/owned-mute"))OwnMute=false;if(OwnMute){try{Run("/usr/bin/busctl","--system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b false");OwnMute=false;File.Delete(State+"/owned-mute");}catch{}}Covered=false;LastAd=0;CoverSource="none";Countdown.Reset();Next=0;Themes?.EndBreak();}}
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
 static void PrepareBreakArtwork(){if(!Covered)Themes.BeginBreak();RefreshIdleOverlay();}
 static void Cover(){lock(Gate){bool newCover=!Covered;if(!Enabled||OtherActive()||Now()-NavigationAt()<3000)return;PrepareBreakArtwork();if(!Covered){CoverSince=Now();Covers++;CoverSource=LastMatchSource;AudioCoverConfirmed=false;bool armed=Now()<AudioArmedUntil;if(armed)AudioArmHits++;AudioArmedUntil=0;Record("cover","fresh ad match via "+LastMatchSource+(LastAudioDecision>0&&LastMatchSource!="audio-splice"&&Now()-LastAudioDecision<=30000?"; audio trigger decided "+(Now()-LastAudioDecision)+" ms earlier":"")+(armed?"; during audio burst":""));
  string mute=Run("/usr/bin/busctl","--system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager GetSpeakerMute");
  if(mute.Trim()=="ii 0 0"){File.WriteAllText(State+"/owned-mute","1");Run("/usr/bin/busctl","--system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b true");OwnMute=true;}
 }if(newCover){
  CoverCaptureId=ActiveCaptureId;CoverCaptureStarted=ActiveCaptureStarted;CoverReceiptSeen=false;
  Timing?.Record(CoverCaptureId,DetectionStage.MuteCompleted,CoverCaptureStarted);
  try{File.WriteAllText(State+"/overlay-lease.request",CoverCaptureId+" "+CoverCaptureStarted);}catch(IOException error){Health?.Error("timing-request",error);}
 }File.WriteAllText(State+"/overlay-lease",Now().ToString());
 if(newCover)Timing?.Record(CoverCaptureId,DetectionStage.CoverRequested,CoverCaptureStarted);
 if(Overlay==null||Overlay.HasExited){CoverTheme=Themes.EffectiveTheme;Overlay=Spawn("/usr/bin/dotnet",Home+"/CommercialOverlayProbe.dll --seconds 0 --scene "+Themes.ResolveScene()+" --lease-file "+State+"/overlay-lease --pause-file "+State+"/overlay-pause --paused-ack-file "+State+"/overlay-paused-ack --standby-file "+State+"/heartbeat --navigation-file "+State+"/navigation");}
 Covered=true;}}
 static void Save(){EngineHealth.SaveEnabled(Home,Enabled);}
 static void Disable(string why){lock(Gate){SamsungLane.Cancel();Enabled=false;Generation++;Save();Debug?.Set(false);StopLayoutWorker();StopAudio();Release(why);foreach(var p in new[]{Overlay,Navigation,Watchdog})try{if(p!=null&&!p.HasExited)p.Kill();}catch{}File.Delete(State+"/heartbeat");Message=why;}}
 static bool IsAd(JsonElement response,string at)=>SamsungVerdict.IsAd(response,at);
 static async Task<bool> Recognize(EvidenceSession session,long captureId,bool keepCard=false){
  YouTubeSkipFrame=0;TimerEvidence=null;
  CaptureMode=Covered?(keepCard?"card-visible":"panel-masked"):"normal";
  var ticket=Debug?.Begin();PendingDebug debug=null;
  if(ticket!=null){debug=new PendingDebug{ticket=ticket,before=Context(),app=LastApp,mode=CaptureMode,navigation=NavigationAt(),generation=Generation,captureStarted=Now()};Pending.Add(debug);}
  try {
  bool broadcastChecks=IsYouTubeTv(LastApp);
  bool youtubeOnly=YouTubeDetectionPolicy.LocalOnly(LastApp);
  bool layoutRequested=broadcastChecks&&!keepCard&&LayoutReady();
  bool samsungEligible=broadcastChecks&&SamsungLane.Ready(DetectionTiming.Clock);
  Stage="capture";long captureStarted=Now();File.Delete(State+"/youtube-ui.json");File.Delete(State+"/sponsored-pill.json");File.Delete(State+"/layout-result.json");File.WriteAllText(State+"/acr-next-capture",(Now()/1000).ToString());
  using(var p=new Process()){
   p.StartInfo=new ProcessStartInfo("/usr/bin/dotnet",Home+"/AcrFrameProbe.dll"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
   p.StartInfo.Environment["LD_PRELOAD"]="/lib/libcapi-system-info.so.0:"+State+"/libtzcapturec-probe.so";
   p.StartInfo.Environment["CAPTURE_FINGERPRINT_ONLY"]="1";
   p.StartInfo.Environment["CAPTURE_CHECK_FINGERPRINT"]=samsungEligible?"1":"0";
   p.StartInfo.Environment["CAPTURE_CHECK_SPONSORED"]=broadcastChecks?"1":"0";
   p.StartInfo.Environment["CAPTURE_CHECK_YOUTUBE"]=IsRegularYouTube(LastApp)?"1":"0";
   p.StartInfo.Environment["CAPTURE_LOCAL_YOUTUBE_ONLY"]=youtubeOnly?"1":"0";
   p.StartInfo.Environment["CAPTURE_CHECK_LAYOUT"]=layoutRequested?"1":"0";
   p.StartInfo.Environment["CAPTURE_KEEP_CARD"]=keepCard?"1":"0";
   if(ticket!=null)p.StartInfo.Environment["CAPTURE_DEBUG_ID"]=ticket.id;
   p.StartInfo.Environment["CAPTURE_OVERLAY_PAUSE_FILE"]=Covered?State+"/overlay-pause":"";
   p.StartInfo.Environment["CAPTURE_OVERLAY_ACK_FILE"]=Covered?State+"/overlay-paused-ack":"";
   p.Start();var output=p.StandardOutput.ReadToEndAsync();var errors=p.StandardError.ReadToEndAsync();if(!p.WaitForExit(4000)){try{p.Kill();}catch{}throw new TimeoutException();}if(p.ExitCode==75){MaskedLooks.Complete(true);Stage="capture-deferred";Timing.Record(captureId,DetectionStage.CaptureDeferred,session.Started);if(debug!=null)debug.verdict="not_queried_safe_deferral";return false;}if(p.ExitCode!=0)throw new IOException("capture unavailable");
  }
  Timing.Record(captureId,DetectionStage.CaptureFinished,session.Started);if(CaptureMode=="panel-masked")MaskedLooks.Complete(false);LastError="";
  if(debug!=null){try{debug.diagnostics=JsonDocument.Parse(File.ReadAllText(State+"/capture-diagnostics.json")).RootElement.Clone();}catch{}}
  try {
   var local=JsonDocument.Parse(File.ReadAllText(State+"/youtube-ui.json")).RootElement.Clone();
   if(debug!=null)debug.youtube=local;
   if(!keepCard&&IsRegularYouTube(LastApp)&&local.GetProperty("at").GetInt64()>=captureStarted){YouTubeChecks++;LastYouTubeUi=local.GetProperty("state").GetString();LastYouTubeMillis=local.GetProperty("elapsedMs").GetDouble();}
   bool uiAd=IsYouTubeUi(local,captureStarted,Now(),keepCard,LastApp);
   bool fresh=!keepCard&&IsRegularYouTube(LastApp)&&local.GetProperty("detector").GetString()==YouTubeDetectionPolicy.Detector&&(uiAd||(local.GetProperty("state").GetString()=="unknown"&&!local.GetProperty("hit").GetBoolean()))&&local.GetProperty("at").GetInt64()>=captureStarted&&Now()>=local.GetProperty("at").GetInt64()&&Now()-local.GetProperty("at").GetInt64()<=1500;
   SkipGuard?.Observe(Now(),fresh,uiAd);
   if(fresh&&!uiAd&&YouTubeSkipStatus=="select-sent")YouTubeSkipStatus="ad-controls-cleared";
   if(uiAd){
    TimerEvidence=YouTubeCountdownHold.Parse(local,Now());
    if(local.GetProperty("state").GetString()=="skip")YouTubeSkipFrame=local.GetProperty("at").GetInt64();
    YouTubeHits++;LastError="";Stage="local-match";LastMatchSource="youtube-ui-"+local.GetProperty("state").GetString();
    Record("local-match","YouTube control: "+local.GetProperty("controlKind").GetString());
    if(debug!=null)debug.verdict="not_queried_local_positive";
    return true;
   }
  }catch{}
  // Regular YouTube never falls through to fingerprinting/network recognition.
  // A valid local miss is a successful check, not a Samsung failure/backoff.
  if(youtubeOnly){LastError="";Stage="local-only";if(debug!=null)debug.verdict="not_queried_youtube_local_only";return false;}
  JsonElement? pill=null;
  try{pill=JsonDocument.Parse(File.ReadAllText(State+"/sponsored-pill.json")).RootElement.Clone();}catch{}
  if(pill.HasValue){
   var local=pill.Value;if(debug!=null)debug.pill=local;
   if(!keepCard){LocalChecks++;try{LastPillScore=local.GetProperty("score").GetDouble();LastPillMillis=local.GetProperty("elapsedMs").GetDouble();}catch{}}
   if(IsPill(local,captureStarted,Now(),keepCard,LastApp)){
    LocalHits++;LastError="";Stage="local-match";LastMatchSource="sponsored-pill";
    Record("local-match","YouTube TV Sponsored pill");if(debug!=null)debug.verdict="not_queried_local_positive";
    return true;
   }
  }
  // Warm feature processing usually finishes while the capture helper encodes
  // its optional debug PNG. Bound any additional wait; Samsung remains fallback.
  if(layoutRequested&&LayoutEnabled){var wait=Stopwatch.StartNew();while(!File.Exists(State+"/layout-result.json")&&wait.ElapsedMilliseconds<200&&LayoutEnabled)await Task.Delay(10);}
  bool layoutFresh=false;
  try {
   var local=JsonDocument.Parse(File.ReadAllText(State+"/layout-result.json")).RootElement.Clone();
   if(debug!=null)debug.layout=local;
   if(!keepCard&&local.GetProperty("at").GetInt64()>=captureStarted){
    layoutFresh=true;LayoutNoReplies=0;LayoutChecks++;LastLayoutMillis=local.GetProperty("elapsedMs").GetDouble();
    if(local.TryGetProperty("error",out var error))LayoutError=error.GetString();
    else {LayoutError="";LastLayoutScore=local.GetProperty("score").GetDouble();LastLayoutModel=local.GetProperty("modelId").GetString();}
   }
   if(IsLayout(local,captureStarted,Now(),keepCard,LayoutEnabled,LastApp)){
    LayoutHits++;LastError="";Stage="local-match";LastMatchSource="experimental-layout";
    Record("local-match","experimental spatial layout; margin "+LastLayoutScore.ToString("F3",System.Globalization.CultureInfo.InvariantCulture));
    if(debug!=null)debug.verdict="not_queried_local_positive";
    return true;
   }
  }catch{}
  finally{
   try{File.Delete(State+"/layout-frame.bin");}catch{}
   if(layoutRequested&&LayoutEnabled&&!layoutFresh&&++LayoutNoReplies>=3){LayoutError="three missing worker replies; experiment disabled";SetLayout(false);}
  }
  if(!samsungEligible){Stage="local-only";if(debug!=null)debug.verdict="not_queried_samsung_busy_or_backoff";return false;}
  Stage="fingerprint";
  var fingerprint=JsonDocument.Parse(Convert.FromBase64String(File.ReadAllText(State+"/acr-fingerprint"))).RootElement.Clone();
  if(fingerprint.GetProperty("capture_rc").GetInt64()!=0||fingerprint.GetProperty("fingerprint_rc").GetInt64()!=0)throw new IOException("fingerprint unavailable");
  if(debug!=null)debug.fingerprint=fingerprint;
  if(!session.Current(App(),Generation,NavigationAt(),DetectionTiming.Clock,Enabled&&!MaintenancePaused))return false;
  var job=new RemoteRecognition{session=session,captureId=captureId,keepCard=keepCard,fingerprint=fingerprint,debug=debug,mode=CaptureMode};
  if(SamsungLane.TryStart(DetectionTiming.Clock,token=>SamsungClient.Query(Config,fingerprint,session.App,token))){
   RemoteJob=job;if(debug!=null)debug.remotePending=true;
   Timing.Record(captureId,DetectionStage.RemoteSubmitted,session.Started);Stage="samsung-pending";
  }
  return false;
  }catch(Exception error){if(debug!=null)debug.error=Stage+": "+error.GetType().Name;throw;}
 }
 static long Next=0;
 static volatile bool MaintenancePaused=false,RecognitionInProgress=false;
 static async Task Loop()
 {
  int failures=0;
  while(true)
  {
   try
   {
    Health.Pulse(Stage);
    if(MaintenancePaused||!Enabled)
    {
     InvalidateRemote();FinishRemote(false,LastApp);
     Stage=MaintenancePaused?"maintenance":"off";
     await Task.Delay(200);continue;
    }
    if(OtherActive()){Disable("Other blocker is active — remaining off");continue;}
    Prepare();
    long navigation=NavigationAt();
    if(navigation!=LastNavigation)
    {
     InvalidateRemote();Release("navigation");LastNavigation=navigation;ContextSince=Now();
    }
    string app=PollApp();
    if(app!=LastApp)
    {
     InvalidateRemote();Release("app change");LastApp=app;ContextSince=Now();Next=0;AudioArmedUntil=0;
    }
    if(ArtMode=="on"&&Now()-ArtObserved<6000)
    {
     InvalidateRemote();FinishRemote(false,app);Release("Art Mode");Message="Paused in Art Mode";
     await Task.Delay(1000);continue;
    }
    if(!IsSupportedApp(app))
    {
     InvalidateRemote();FinishRemote(false,app);Release("outside supported apps");Message="Waiting for YouTube or YouTube TV";
     await Task.Delay(1000);continue;
    }
    File.WriteAllText(State+"/heartbeat",(Now()/1000).ToString());
    ObserveOverlay();
    lock(Gate)
    {
     bool timerLease=IsRegularYouTube(app)&&Countdown.KeepsCovered(Now());
     if(Covered&&(!File.Exists(State+"/overlay-lease")||(!timerLease&&Now()>=CoverExpiry)))Release("ad renewal expired or lease removed");
     if(Covered&&timerLease)
     {
      File.WriteAllText(State+"/overlay-lease",Now().ToString());
      if(Countdown.Waiting(Now()))Stage="youtube-countdown-hold";
     }
    }
    FinishRemote(true,app);
    // A covered Samsung check can finish without repeatedly dropping its card.
    // Uncovered local checks continue even while a remote operation is pending.
    if(Covered&&IsYouTubeTv(app)&&SamsungLane.Busy)
    {
     await Task.Delay(50);continue;
    }
    if(DetectionTiming.Clock<Next&&!(!Covered&&Now()<AudioArmedUntil))
    {
     await Task.Delay(SamsungLane.Busy?50:100);continue;
    }
    var session=new EvidenceSession{App=app,Generation=Generation,Navigation=NavigationAt(),Started=DetectionTiming.Clock};
    long captureId=Timing.Begin();
    lock(Gate){if(MaintenancePaused||!Enabled)continue;RecognitionInProgress=true;}
    bool steady=Covered&&IsYouTubeTv(app)&&!MaskedLooks.Begin(Now(),CoverExpiry);
    if(Covered&&IsYouTubeTv(app)&&!steady)MaskedFallbacks++;
    Timing.Record(captureId,DetectionStage.CaptureStarted,session.Started);
    bool ad=await Recognize(session,captureId,steady);
    failures=0;
    Next=session.Started+YouTubeDetectionPolicy.IntervalMs(app);
    if(ad)
    {
     Timing.Record(captureId,DetectionStage.LocalPositive,session.Started);
     AcceptAd(session,captureId);
    }
    else Message=Covered?"Waiting for another match":"Watching — no confirmed ad";
    FinishRemote(true,app);
   }
   catch(Exception error)
   {
    LastError=Stage+": "+error.GetType().Name+"/"+error.GetBaseException().GetType().Name;
    Health.Error(Stage,error);Record("error",LastError);InvalidateRemote();Release("capture or control error");
    failures++;if(failures>=5)throw new InvalidOperationException("Repeated local failures",error);
    Next=DetectionTiming.Clock+500;Message="Capture unavailable — playback released";await Task.Delay(500);
   }
   finally
   {
    try{FlushDebug();}catch{Pending.RemoveAll(item=>!item.remotePending);}
    RecognitionInProgress=false;
   }
  }
 }
 static object Status()=>new{continuation=Archive.Status(),maskedLooks=new{total=MaskedLooks.Looks,deferred=MaskedLooks.Deferrals},build=Build,timing=Timing?.Status(),samsungLane=SamsungLane.Status(DetectionTiming.Clock),samsungError=SamsungError,health=Health?.Status(),enabled=Enabled,maintenancePaused=MaintenancePaused,recognitionInProgress=RecognitionInProgress,covered=Covered,otherActive=OtherActive(),message=Message,stage=Stage,lastError=LastError,lastAcceptedAt=LastAccepted,covers=Covers,captureMode=CaptureMode,steadyCardMatches=SteadyCardMatches,maskedFallbacks=MaskedFallbacks,queries=Queries,matches=Matches,foregroundApp=LastApp,supportedApp=IsSupportedApp(LastApp),engine="YouTube: local countdown/Skip only; YouTube TV: Samsung + broadcast rules",samsungRecognition=YouTubeDetectionPolicy.UsesSamsung(LastApp),checkTargetMs=YouTubeDetectionPolicy.IntervalMs(LastApp),youtubeUi=new{checks=YouTubeChecks,hits=YouTubeHits,state=LastYouTubeUi,lastMillis=LastYouTubeMillis,automaticSkip=YouTubeAutoSkip,skipAttempts=YouTubeSkipAttempts,skipStatus=YouTubeSkipStatus,lastSkipAttemptAt=SkipGuard?.LastAttempt,countdown=new{seconds=Countdown.Seconds,maxSeconds=Countdown.MaxSeconds,holding=Covered&&Countdown.Waiting(Now()),checkAt=Countdown.CheckAt,checkInMs=Covered?Math.Max(0,Countdown.CheckAt-Now()):0,holds=CountdownHolds}},layout=new{enabled=LayoutEnabled,checks=LayoutChecks,hits=LayoutHits,lastScore=LastLayoutScore,lastMillis=LastLayoutMillis,lastModel=LastLayoutModel,error=LayoutError,threshold=0.5,experimental=true},localChecks=LocalChecks,localHits=LocalHits,lastPillScore=LastPillScore,lastPillMillis=LastPillMillis,lastMatchSource=LastMatchSource,releaseSeconds=8,persistentApp=true,rebootReady=false,audio=new{mode=AudioMode,shadow=AudioMode==1,triggers=AudioTriggers,covers=AudioCovers,lastTriggerAt=LastAudioTriggerAt==0?(long?)null:LastAudioTriggerAt,tapSilent=AudioSilent,lastStateAt=LastAudioStateAt==0?(long?)null:LastAudioStateAt,observerAlive=Audio!=null&&!Audio.HasExited,error=AudioError,floorDb=AudioFloor(),quietSeconds=AudioSetting("audio-quiet",60,0,3600),cooldownSeconds=AudioSetting("audio-cooldown",300,0,3600),unconfirmed=AudioUnconfirmed,suppressed=AudioSuppressed,armSeconds=AudioSetting("audio-arm",5,1,30),arms=AudioArms,armHits=AudioArmHits,armed=Now()<AudioArmedUntil,rule="null 60-1500 ms at or below floor, then non-mono audio; decision 1 s after the null"},appearance=new{theme=Themes?.Selected??"default",effectiveTheme=Themes?.EffectiveTheme??"default",activeTheme=Covered?CoverTheme:null},debug=Debug?.Status()};
 static async Task Serve(){var h=new HttpListener();h.Prefixes.Add("http://127.0.0.1:18764/");h.Start();while(true){var c=await h.GetContextAsync();try{
  c.Response.Headers.Add("Access-Control-Allow-Origin","*");c.Response.Headers.Add("Access-Control-Allow-Methods","GET, POST, OPTIONS");c.Response.Headers.Add("Access-Control-Allow-Headers","Authorization, Content-Type");
  if(c.Request.HttpMethod=="OPTIONS"){c.Response.StatusCode=204;c.Response.Close();continue;}
  if(c.Request.Headers["Authorization"]!="Bearer "+Token){c.Response.StatusCode=401;c.Response.Close();continue;}
  if(c.Request.Url.AbsolutePath=="/maintenance"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   lock(Gate){MaintenancePaused=body.GetProperty("paused").GetBoolean();Generation++;Next=0;if(MaintenancePaused){SamsungLane.Cancel();Release("maintenance");}Message=MaintenancePaused?"Maintenance paused; waiting for capture to finish":"Maintenance complete";}
  }else if(c.Request.Url.AbsolutePath=="/appearance"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   lock(Gate){Themes.Set(body.GetProperty("theme").GetString());}
  }else if(c.Request.Url.AbsolutePath=="/continuation"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   lock(Gate){bool value=body.GetProperty("enabled").GetBoolean();
    File.WriteAllText(Home+"/archive-continuation-enabled.tmp",value?"1":"0");File.Move(Home+"/archive-continuation-enabled.tmp",Home+"/archive-continuation-enabled",true);
    Archive.Enabled=value;Archive.ResetSession();Generation++;
    if(Covered&&Now()-LastAd>=8000)Release("continuation setting changed");
    else if(Covered&&File.Exists(State+"/overlay-lease"))File.WriteAllText(State+"/overlay-lease",LastAd.ToString());
   }
  }else if(c.Request.Url.AbsolutePath=="/layout"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   SetLayout(body.GetProperty("enabled").GetBoolean());
  }else if(c.Request.Url.AbsolutePath=="/youtube-skip"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   SetYouTubeSkip(body.GetProperty("enabled").GetBoolean());
  }else if(c.Request.Url.AbsolutePath=="/audio"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   SetAudio(body.GetProperty("mode").GetInt32());
  }else if(c.Request.Url.AbsolutePath=="/debug"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   Debug.Set(body.GetProperty("enabled").GetBoolean());
  }else if(c.Request.Url.AbsolutePath=="/control"&&c.Request.HttpMethod=="POST"){
   if(c.Request.ContentLength64<1||c.Request.ContentLength64>128){c.Response.StatusCode=400;c.Response.Close();continue;}
   var body=JsonDocument.Parse(await new StreamReader(c.Request.InputStream).ReadToEndAsync()).RootElement;
   lock(Gate){if(body.GetProperty("enabled").GetBoolean()){if(OtherActive()){c.Response.StatusCode=409;Message="Stop the other blocker before enabling";}else{Generation++;MaintenancePaused=false;Enabled=true;Save();Message="Enabled";}}else Disable("Off");}
  }else if(c.Request.Url.AbsolutePath!="/status"){c.Response.StatusCode=404;c.Response.Close();continue;}
  byte[] b=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(Status()));c.Response.ContentType="application/json";await c.Response.OutputStream.WriteAsync(b,0,b.Length);c.Response.Close();
 }catch{try{c.Response.StatusCode=400;c.Response.Close();}catch{}}}}
 static int Main(string[] args){
  if(args.Length==2&&args[0]=="--replay-youtube"){foreach(var item in JsonDocument.Parse(File.ReadAllText(args[1])).RootElement.EnumerateArray())Console.WriteLine(IsYouTubeUi(item.GetProperty("evidence"),item.GetProperty("started").GetInt64(),item.GetProperty("now").GetInt64(),item.GetProperty("keepCard").GetBoolean(),item.GetProperty("app").GetString())?"ad":"uncertain");return 0;}
  if(args.Length==2&&args[0]=="--replay-apps"){foreach(var item in JsonDocument.Parse(File.ReadAllText(args[1])).RootElement.EnumerateArray()){string app=item.ValueKind==JsonValueKind.Null?null:item.GetString();Console.WriteLine(JsonSerializer.Serialize(new{supported=IsSupportedApp(app),broadcastChecks=IsYouTubeTv(app),localOnly=YouTubeDetectionPolicy.LocalOnly(app),samsungRecognition=YouTubeDetectionPolicy.UsesSamsung(app)}));}return 0;}
  if(args.Length==2&&args[0]=="--replay-layout"){foreach(var item in JsonDocument.Parse(File.ReadAllText(args[1])).RootElement.EnumerateArray())Console.WriteLine(IsLayout(item.GetProperty("evidence"),item.GetProperty("started").GetInt64(),item.GetProperty("now").GetInt64(),item.GetProperty("keepCard").GetBoolean(),item.GetProperty("enabled").GetBoolean(),item.TryGetProperty("app",out var app)?app.GetString():"com.samsung.tv.cobalt-yttv")?"ad":"uncertain");return 0;}
  if(args.Length==2&&args[0]=="--replay-pill"){foreach(var item in JsonDocument.Parse(File.ReadAllText(args[1])).RootElement.EnumerateArray())Console.WriteLine(IsPill(item.GetProperty("evidence"),item.GetProperty("started").GetInt64(),item.GetProperty("now").GetInt64(),item.GetProperty("keepCard").GetBoolean(),item.TryGetProperty("app",out var app)?app.GetString():"com.samsung.tv.cobalt-yttv")?"ad":"uncertain");return 0;}
  if(args.Length==3&&args[0]=="--classify"){Console.WriteLine(IsAd(JsonDocument.Parse(File.ReadAllText(args[1])).RootElement,args[2])?"ad":"uncertain");return 0;}
  if(args.Length==2&&args[0]=="--replay"){foreach(var item in JsonDocument.Parse(File.ReadAllText(args[1])).RootElement.EnumerateArray())Console.WriteLine(IsAd(item.GetProperty("response"),item.GetProperty("at").GetString())?"ad":"uncertain");return 0;}
  Health=new EngineHealth(Home,State);Timing=new DetectionTiming(Home);Build=DetectionTiming.BuildIdentity();
  try{Archive.Enabled=File.ReadAllText(Home+"/archive-continuation-enabled").Trim()=="1";}catch{Archive.Enabled=false;}
  SkipGuard=new YouTubeSkipGuard(ReadSkipAttempt());try{YouTubeAutoSkip=File.ReadAllText(Home+"/youtube-skip-enabled").Trim()=="1";}catch{}YouTubeSkipStatus=YouTubeAutoSkip?"ready":"off";
  AppDomain.CurrentDomain.UnhandledException+=(sender,eventArgs)=>Health.Error("unhandled",eventArgs.ExceptionObject as Exception);
  bool acquired=false;
  try{
   Directory.CreateDirectory(State);Themes=new ThemeSettings(Home);Config=JsonDocument.Parse(File.ReadAllText(Home+"/device.json")).RootElement.Clone();Token=Config.GetProperty("controlToken").GetString();
   using(var single=new FileStream(State+"/engine.lock",FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None)){
    acquired=true;Health.Pulse("startup");Health.Event("started");
    File.Copy(Home+"/libtzcapturec-probe.so",State+"/libtzcapturec-probe.so",true);
    Debug=new DebugRecords(Home,State,Now);var cleanup=Task.Run(DebugMaintenance);var artMonitor=Task.Run(ArtMonitor);
    try{LayoutEnabled=File.ReadAllText(Home+"/layout-enabled").Trim()=="1"&&File.Exists(Home+"/layout-model.json");}catch{LayoutEnabled=false;}
    AudioMode=ReadAudioMode();if(AudioMode!=0&&!File.Exists(Home+"/AudioSpliceObserver.dll")){AudioMode=0;AudioError="audio observer missing";}
    bool saved=EngineHealth.LoadEnabled(Home);
    OwnMute=File.Exists(State+"/owned-mute");Release("engine recovery");
    Enabled=saved&&!OtherActive();Message=Enabled?"Recovered — watching":"Off — Samsung + local Sponsored pill";
    // Observe every permanent task: an exited loop must never leave an On UI.
    var loop=Task.Run(Loop);var server=Task.Run(Serve);var audio=Task.Run(AudioPump);
    Task.WhenAny(loop,server,cleanup,artMonitor,audio).GetAwaiter().GetResult().GetAwaiter().GetResult();
    throw new InvalidOperationException("Permanent engine task returned");
   }
  }catch(Exception error){
   Health.Error("fatal",error);
   try{if(acquired)Release("engine failure");}catch(Exception releaseError){Health.Error("release",releaseError);}
   return 1;
  }
 }
}
