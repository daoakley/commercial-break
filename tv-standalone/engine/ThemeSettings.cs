using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;

// Appearance only. No recognition, lease, capture, mute or debug operations.
public sealed class ThemeSettings {
 readonly string home;
 readonly HashSet<string> allowed = new HashSet<string> {
  "default", "spring", "summer", "autumn", "winter", "christmas", "valentines",
  "new-year", "independence", "halloween", "thanksgiving", "easter",
  "zen-dunes", "zen-water", "zen-mountains",
  "raleigh-day", "raleigh-night", "memphis-day", "memphis-night",
  "dc-day", "dc-night", "charlotte-day", "charlotte-night"
 };
 public string Selected { get; private set; } = "default";
 public ThemeSettings(string home) {
  this.home = home;
  try { using(var d=JsonDocument.Parse(File.ReadAllText(Path.Combine(home,"appearance.json")))) {
   string id=d.RootElement.GetProperty("theme").GetString();
   if(allowed.Contains(id) && ValidScene(id))Selected=id;
  }} catch { Selected="default"; }
 }
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
  if(!allowed.Contains(id)||!ValidScene(id))throw new ArgumentException("Theme is unavailable");
  string target=Path.Combine(home,"appearance.json"),temp=target+".tmp";
  File.WriteAllText(temp,JsonSerializer.Serialize(new{theme=id}));
  File.Move(temp,target,true);Selected=id;
 }
 public string ResolveScene() => ValidScene(Selected) ? PathFor(Selected) : PathFor("default");
 public string EffectiveTheme => ValidScene(Selected) ? Selected : "default";
}
