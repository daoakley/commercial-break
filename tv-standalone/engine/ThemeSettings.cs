using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;

// Appearance only. No recognition, lease, capture, mute or debug operations.
public sealed class ThemeSettings {
 readonly string home;
 readonly Func<DateTimeOffset> clock;
 static readonly string[] Cities={"memphis","dc","raleigh","charlotte"};
 int nextCity=0;
 bool breakOpen=false;
 string breakScene=null;
 static bool IsRotation(string id)=>id=="cities-day"||id=="cities-night"||id=="cities-auto";
 readonly HashSet<string> allowed = new HashSet<string> {
  "default", "spring", "summer", "autumn", "winter", "christmas", "valentines",
  "new-year", "independence", "halloween", "thanksgiving", "easter",
  "zen-dunes", "zen-water", "zen-mountains",
  "raleigh-day", "raleigh-night", "memphis-day", "memphis-night",
  "dc-day", "dc-night", "charlotte-day", "charlotte-night", "cities-day", "cities-night", "cities-auto"
 };
 public string Selected { get; private set; } = "default";
 public ThemeSettings(string home, Func<DateTimeOffset> clock=null) {
  this.home = home; this.clock=clock??(()=>DateTimeOffset.UtcNow);
  try { using(var d=JsonDocument.Parse(File.ReadAllText(Path.Combine(home,"appearance.json")))) {
   string id=d.RootElement.GetProperty("theme").GetString();
   if(allowed.Contains(id) && Available(id))Selected=id;
   if(d.RootElement.TryGetProperty("nextCity",out var cursor)&&cursor.TryGetInt32(out int value)&&value>=0&&value<Cities.Length)nextCity=value;
  }} catch { Selected="default"; }
 }
 // NOAA solar position, Raleigh (35.7796 N, 78.6382 W). UTC avoids DST ambiguity.
 // https://gml.noaa.gov/grad/solcalc/solareqns.PDF
 public static bool IsRaleighDay(DateTimeOffset instant) {
  var t=instant.UtcDateTime; double hour=t.TimeOfDay.TotalHours;
  double g=2*Math.PI/(DateTime.IsLeapYear(t.Year)?366:365)*(t.DayOfYear-1+(hour-12)/24);
  double eq=229.18*(.000075+.001868*Math.Cos(g)-.032077*Math.Sin(g)-.014615*Math.Cos(2*g)-.040849*Math.Sin(2*g));
  double dec=.006918-.399912*Math.Cos(g)+.070257*Math.Sin(g)-.006758*Math.Cos(2*g)+.000907*Math.Sin(2*g)-.002697*Math.Cos(3*g)+.00148*Math.Sin(3*g);
  double ha=(hour*60+eq+4*(-78.6382))/4-180, lat=35.7796*Math.PI/180;
  return Math.Sin(lat)*Math.Sin(dec)+Math.Cos(lat)*Math.Cos(dec)*Math.Cos(ha*Math.PI/180)>=Math.Cos(90.833*Math.PI/180);
 }
 string Mode(string selection)=>selection=="cities-day"||selection=="cities-auto"&&IsRaleighDay(clock())?"day":"night";
 string CityAt(int i,string mode)=>Cities[i]+"-"+mode;
 bool Available(string id) {
  if(!IsRotation(id))return ValidScene(id);
  foreach(string mode in id=="cities-auto"?new[]{"day","night"}:new[]{Mode(id)})
   for(int i=0;i<Cities.Length;i++)if(ValidScene(CityAt(i,mode)))return true;
  return false;
 }
 string NextScene() {
  string mode=Mode(Selected);
  for(int offset=0;offset<Cities.Length;offset++){
   string id=CityAt((nextCity+offset)%Cities.Length,mode);
   if(ValidScene(id))return id;
  }
  return "default";
 }
 void Save(string id,int cursor) {
  string target=Path.Combine(home,"appearance.json"),temp=target+".tmp";
  File.WriteAllText(temp,JsonSerializer.Serialize(new{theme=id,nextCity=cursor}));
  File.Move(temp,target,true);
 }
 // Called once on uncovered -> covered, never on lease renewal or capture pause.
 public void BeginBreak() {
  if(breakOpen)return;
  breakScene=IsRotation(Selected)?NextScene():EffectiveTheme;
  breakOpen=true;
  if(IsRotation(Selected)&&breakScene!="default") {
   for(int i=0;i<Cities.Length;i++)if(breakScene.StartsWith(Cities[i]+"-",StringComparison.Ordinal))nextCity=(i+1)%Cities.Length;
   // A storage failure must never prevent the normal blocker from covering.
   try{Save(Selected,nextCity);}catch{}
  }
 }
 public void EndBreak(){breakOpen=false;breakScene=null;}
 string PathFor(string id) => id=="default" ? Path.Combine(home,"scene.json") : Path.Combine(home,"themes",id+".json");
 bool ValidScene(string id) {
  if(!allowed.Contains(id))return false;
  try {
   var f=new FileInfo(PathFor(id));if(!f.Exists||f.Length>1024*1024)return false;
   using(var d=JsonDocument.Parse(File.ReadAllText(f.FullName))){
    var a=d.RootElement.GetProperty("objects");if(a.GetArrayLength()<1||a.GetArrayLength()>256)return false;
    var b=a[0];
    return b.GetProperty("type").GetString()=="rectangle" && b.GetProperty("x").GetInt32()==0 && b.GetProperty("y").GetInt32()==0
     && b.GetProperty("width").GetInt32()==1920 && b.GetProperty("height").GetInt32()==1080
     && b.GetProperty("color").GetString().EndsWith("FF",StringComparison.OrdinalIgnoreCase);
   }
  } catch {return false;}
 }
 public void Set(string id) {
  if(!allowed.Contains(id)||!Available(id))throw new ArgumentException("Theme is unavailable");
  int cursor=IsRotation(id)&&!IsRotation(Selected)?0:nextCity;
  Save(id,cursor);Selected=id;nextCity=cursor;
 }
 public string ResolveScene() => PathFor(EffectiveTheme);
 public string EffectiveTheme {
  get {
   if(breakOpen&&breakScene!=null)return breakScene;
   if(IsRotation(Selected))return NextScene();
   return ValidScene(Selected)?Selected:"default";
  }
 }
}
