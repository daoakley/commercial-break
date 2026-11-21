// Shared by the capture helper, controller and replay tests.
public static class YouTubeDetectionPolicy {
 public const string Detector = "youtube-ad-controls-v2";
 public static bool LocalOnly(string app) => app == "com.samsung.tv.cobalt-yt";
 public static bool UsesSamsung(string app) => app == "com.samsung.tv.cobalt-yttv";
 public static int IntervalMs(string app) => LocalOnly(app) ? 500 : 1000;
 // Fixed YouTube timer position: yellow numerals inside a separated yellow arc.
 // A yellow patch, empty circle or numeral without an arc is insufficient.
 public static bool Circle(int digits,int ring,int rows,int columns,int sectors,int noise) =>
  digits>=5 && digits<=45 && ring>=4 && ring<=170 && rows>=4 && rows<=5 &&
  columns>=1 && columns<=8 && sectors>=2 && sectors<=4 && noise>=0 && noise<=2;
}
