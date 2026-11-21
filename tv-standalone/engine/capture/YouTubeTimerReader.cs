using System;

// Reads only the yellow numeral glyphs in YouTube's already-detected ad control.
// Templates are 4x7 UI glyph samples, not pictures of programs or advertisements.
public static class YouTubeTimerReader {
 public const string Reader="youtube-yellow-digits-v1";
 public sealed class Reading { public int? seconds {get;set;} public int? maxSeconds {get;set;} public double score {get;set;} public double layoutMargin {get;set;} }
 static readonly byte[][] Digits={
  new byte[]{0,0,0,0,36,36,102,0,129,71,0,38,134,61,0,48,126,79,8,28,9,9,66,0,0,0,0,0},
  new byte[]{0,0,0,0,0,0,80,0,0,0,61,0,0,0,47,0,0,0,47,0,0,0,46,0,0,0,0,0},
  new byte[]{0,0,0,0,0,0,133,66,18,18,2,132,0,0,8,56,0,0,37,0,12,12,136,137,0,0,0,0},
  new byte[]{0,0,0,0,63,63,108,0,42,19,9,19,0,0,116,0,105,31,0,39,34,34,66,0,0,0,0,0},
  new byte[]{0,0,0,0,0,0,119,0,0,0,119,0,97,93,70,0,127,127,132,61,0,0,70,0,0,0,0,0},
  new byte[]{0,0,0,0,74,74,142,19,101,101,26,0,52,52,48,30,115,68,4,47,12,12,77,0,0,0,0,0},
  new byte[]{0,0,0,0,70,70,142,15,96,96,12,0,47,47,42,29,113,58,0,42,4,4,66,0,0,0,0,0},
  new byte[]{0,0,0,0,142,142,142,52,0,0,52,0,0,0,56,0,0,0,19,0,40,40,6,0,0,0,0,0},
  new byte[]{0,0,0,0,0,116,119,54,0,122,113,105,0,135,133,71,0,104,94,94,0,81,88,41,0,0,0,0},
  new byte[]{0,0,0,0,34,34,77,0,135,59,2,21,120,120,75,32,0,0,51,0,9,9,14,0,0,0,0,0}
 };
 public static byte Chroma(int r,int g,int b)=>(byte)Math.Max(0,Math.Min(255,Math.Min(r-b-20,g-b-10)));
 static double Match(ReadOnlySpan<byte> patch,int stride,int x,int y,byte[] glyph){
  double a=0,b=0,aa=0,bb=0,ab=0;int n=28;
  for(int j=0;j<7;j++)for(int i=0;i<4;i++){double v=patch[(y+j)*stride+x+i],t=glyph[j*4+i];a+=v;b+=t;aa+=v*v;bb+=t*t;ab+=v*t;}
  double va=aa-a*a/n,vb=bb-b*b/n;if(va/n<40||vb<1)return 0;
  return Math.Max(0,Math.Min(1,(ab-a*b/n)/Math.Sqrt(va*vb)));
 }
 static (int min,int max,double score) Digit(ReadOnlySpan<byte> patch,int stride,int x,int y){
  Span<double> scores=stackalloc double[10];double best=0;
  for(int d=0;d<10;d++){scores[d]=Match(patch,stride,x,y,Digits[d]);best=Math.Max(best,scores[d]);}
  int lo=10,hi=-1;for(int d=0;d<10;d++)if(scores[d]>=.94&&best-scores[d]<=.06){lo=Math.Min(lo,d);hi=Math.Max(hi,d);}
  return (lo,hi,best);
 }
 public static Reading Read(ReadOnlySpan<byte> patch,int stride,int ox,int oy){
  if(stride<56||patch.Length<stride*21)throw new ArgumentException("Expected bottom-right control region");
  var single=Digit(patch,stride,450-ox,240-oy);var tens=Digit(patch,stride,448-ox,240-oy);var units=Digit(patch,stride,452-ox,240-oy);
  double doubleScore=Math.Min(tens.score,units.score),singleScore=single.score;
  bool two=doubleScore>singleScore;int lo=two?tens.min*10+units.min:single.min,hi=two?tens.max*10+units.max:single.max;
  double best=Math.Max(doubleScore,singleScore),margin=Math.Abs(doubleScore-singleScore);
  // The small source glyphs for 5 and 6 can alias. Preserve an interval and use
  // its lower bound; never pretend that an ambiguous numeral is an exact read.
  bool valid=best>=.94&&margin>=.15&&lo>=1&&hi>=lo&&hi<=60&&hi-lo<=1&&(!two||tens.min>=1);
  return new Reading{seconds=valid?(int?)lo:null,maxSeconds=valid?(int?)hi:null,score=best,layoutMargin=margin};
 }
}
