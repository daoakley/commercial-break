using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;

// Appearance only. No recognition, lease, capture, mute or debug operations.
public sealed class ThemeSettings {
 readonly string home;
 static readonly string[] Cities={"memphis","dc","raleigh","charlotte"};
 int nextCity=0;
 bool breakOpen=false;
 string breakScene=null;
 static bool IsRotation(string id)=>id=="cities-day"||id=="cities-night";
 readonly HashSet<string> allowed = new HashSet<string> {
  "default", "spring", "summer", "autumn", "winter", "christmas", "valentines",
  "new-year", "independence", "halloween", "thanksgiving", "easter",
  "zen-dunes", "zen-water", "zen-mountains",
  "raleigh-day", "raleigh-night", "memphis-day", "memphis-night",
  "dc-day", "dc-night", "charlotte-day", "charlotte-night", "cities-day", "cities-night"
 };
 public string Selected { get; private set; } = "default";
 public ThemeSettings(string home) {
  this.home = home;
  try { using(var d=JsonDocument.Parse(File.ReadAllText(Path.Combine(home,"appearance.json")))) {
   string id=d.RootElement.GetProperty("theme").GetString();
   if(allowed.Contains(id) && Available(id))Selected=id;
   if(d.RootElement.TryGetProperty("nextCity",out var cursor)&&cursor.TryGetInt32(out int value)&&value>=0&&value<Cities.Length)nextCity=value;
  }} catch { Selected="default"; }
 }
 string CityAt(int i,string selection)=>Cities[i]+(selection=="cities-day"?"-day":"-night");
 bool Available(string id) {
  if(!IsRotation(id))return ValidScene(id);
  for(int i=0;i<Cities.Length;i++)if(ValidScene(CityAt(i,id)))return true;
  return false;
 }
 string NextScene() {
  for(int offset=0;offset<Cities.Length;offset++){
   string id=CityAt((nextCity+offset)%Cities.Length,Selected);
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
   for(int i=0;i<Cities.Length;i++)if(CityAt(i,Selected)==breakScene)nextCity=(i+1)%Cities.Length;
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
