using System;
using System.Runtime.InteropServices;

// Fixed-position YouTube countdown/Skip recognition. No model, OCR or network.
// Sponsored is diagnostic only: it can be unreadable over the advertiser's video.
// Samples use the same 480x270 mapping as the native capture PNG.
public static class YouTubeAdUi {
 public const string Detector=YouTubeDetectionPolicy.Detector;
 public const double LabelThreshold=.92, CountdownThreshold=.90, SkipThreshold=.95;
 public sealed class Result {
  public double sponsoredScore {get;set;}
  public double countdownScore {get;set;}
  public double skipScore {get;set;}
  public int? skipX {get;set;}
  public int? skipY {get;set;}
  public int yellowPixels {get;set;}
  public int circleDigitPixels {get;set;}
  public int circleRingPixels {get;set;}
  public int circleRows {get;set;}
  public int circleColumns {get;set;}
  public int circleSectors {get;set;}
  public int circleNoise {get;set;}
  public string controlKind {get;set;}
  public string timerReader {get;set;}
  public int? timerSeconds {get;set;}
  public int? timerMaxSeconds {get;set;}
  public double timerScore {get;set;}
  public double timerLayoutMargin {get;set;}
  public bool hit {get;set;}
  public bool skipReady {get;set;}
  public string state {get;set;}
 }
 static readonly byte[] Label={31,32,31,32,32,33,33,33,32,33,33,32,33,33,33,33,33,32,32,33,33,33,33,34,34,34,34,34,34,34,34,34,30,31,60,50,31,31,31,31,31,31,32,31,31,31,31,31,32,31,31,32,32,33,33,32,33,33,33,32,32,173,34,32,29,194,134,57,71,216,210,73,32,219,206,72,216,220,106,182,217,55,48,218,182,120,210,66,129,213,84,184,218,185,32,30,28,29,111,212,67,197,33,191,124,28,101,70,207,120,190,215,142,29,183,29,160,111,194,70,217,168,204,193,32,185,30,28,27,214,100,158,182,205,36,181,103,37,131,70,207,118,191,110,35,138,157,31,185,112,192,62,216,34,60,203,35,185,29,28,25,28,122,121,28,202,143,31,26,174,125,54,167,90,148,87,176,30,28,177,86,90,150,26,46,157,43,91,170,143,27,27,22,23,23,24,21,198,26,23,22,21,21,18,18,22,24,21,22,22,23,17,20,24,22,21,23,22,19,22,17,25,25,21,26,25,25,25,25,26,26,25,25,25,25,24,25,25,25,25,25,26,26,23,24,25,25,25,26,25,25,26,25,25,26,27};
 static readonly byte[] SimpleLabel={0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,14,10,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,159,2,0,0,180,171,198,139,8,7,0,0,9,5,1,8,9,1,2,9,0,0,9,2,3,8,2,1,6,0,2,8,182,2,0,0,129,215,14,0,214,83,150,42,115,190,49,218,182,165,213,69,109,109,106,213,101,218,34,209,164,169,219,116,182,2,0,0,30,5,192,145,194,5,194,124,0,66,49,205,103,187,118,208,34,184,0,135,96,189,61,219,181,159,181,2,182,2,0,0,163,211,217,123,219,179,124,26,182,213,49,205,103,187,216,124,101,88,178,218,102,190,9,199,183,162,217,151,182,2,0,0,0,0,0,0,194,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,94,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
 static readonly byte[] Countdown={34,33,27,21,19,21,21,19,20,20,22,22,21,21,25,21,21,21,22,55,55,32,30,32,28,20,18,19,19,17,18,20,20,19,20,22,21,20,20,20,52,52,36,33,33,33,31,30,21,18,17,16,17,19,17,18,20,20,18,19,20,49,50,43,37,115,216,143,170,100,25,26,44,17,17,16,16,18,164,17,17,18,46,47,38,55,207,37,102,170,100,206,50,43,179,217,135,15,16,172,35,161,213,45,46,27,26,44,215,132,169,187,31,37,55,181,17,172,15,16,175,36,16,58,41,42,27,63,178,27,175,168,127,89,35,53,180,29,182,15,16,173,35,15,53,37,43,26,26,69,205,114,152,87,191,81,48,181,204,112,24,18,159,31,15,48,33,41,32,32,33,26,25,23,23,25,25,25,182,25,23,23,22,24,18,14,14,31,40,30,29,31,33,30,24,23,25,25,24,24,24,23,22,23,23,21,21,17,27,34};
 static readonly byte[] Skip={5,5,193,219,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,4,119,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,150,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,219,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,221,220,220,220,220,220,220,220,220,220,220,217,168,221,220,220,220,214,216,220,220,220,220,220,220,220,220,220,220,125,15,101,219,157,220,213,28,220,220,220,220,220,220,220,203,7,9,218,220,220,201,206,220,220,220,220,220,220,220,220,221,220,16,208,141,191,157,154,204,23,62,57,87,218,220,220,220,203,7,7,7,51,220,201,206,220,220,221,220,220,220,220,220,220,220,199,63,109,219,53,53,215,21,61,141,65,135,220,220,220,203,7,7,7,7,24,186,206,220,220,220,220,220,220,220,220,220,220,64,219,51,143,121,31,215,21,61,138,58,137,220,220,220,203,7,7,7,21,221,201,206,220,220,220,220,220,220,220,220,220,220,173,41,129,219,163,209,170,38,61,82,115,219,220,220,220,203,7,7,206,220,220,201,206,220,220,220,220,220,220,220,220,220,220,220,220,220,220,221,220,221,220,61,142,220,221,220,220,220,214,117,220,220,221,220,209,213,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,221,178,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,6,158,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,5,4,213,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220};

 const int LeftX=18,LeftY=238,LeftW=59,LeftH=17;
 const int RightX=400,RightY=234,RightW=64,RightH=21;
 static byte Clamp(double v)=>v<0?(byte)0:v>255?(byte)255:(byte)v;
 static byte Gray(int r,int g,int b)=>(byte)((299*r+587*g+114*b+500)/1000);
 static bool Yellow(int r,int g,int b)=>r>115&&g>80&&r>b+45&&g>b+25&&r>=g;
 public static Result ScoreRgb(byte[] rgb,int width=480,int height=270){
  if(rgb==null)throw new ArgumentNullException(nameof(rgb));
  if(width!=480||height!=270||rgb.Length!=480*270*3)throw new ArgumentException("Expected 480x270 RGB");
  Span<byte> left=stackalloc byte[LeftW*LeftH];Span<byte> right=stackalloc byte[RightW*RightH];Span<byte> yellowMask=stackalloc byte[RightW*RightH];Span<byte> chroma=stackalloc byte[RightW*RightH];int yellow=0;
  for(int y=0;y<LeftH;y++)for(int x=0;x<LeftW;x++){int at=((y+LeftY)*480+x+LeftX)*3;left[y*LeftW+x]=Gray(rgb[at],rgb[at+1],rgb[at+2]);}
  for(int y=0;y<RightH;y++)for(int x=0;x<RightW;x++){int at=((y+RightY)*480+x+RightX)*3;int r=rgb[at],g=rgb[at+1],b=rgb[at+2];right[y*RightW+x]=Gray(r,g,b);bool isYellow=Yellow(r,g,b);yellowMask[y*RightW+x]=isYellow?(byte)1:(byte)0;if(x+RightX>=438&&x+RightX<463&&y+RightY<254&&isYellow)yellow++;}
  for(int y=0;y<RightH;y++)for(int x=0;x<RightW;x++){int at=((y+RightY)*480+x+RightX)*3;chroma[y*RightW+x]=YouTubeTimerReader.Chroma(rgb[at],rgb[at+1],rgb[at+2]);}
  return Score(left,right,yellow,yellowMask,chroma);
 }
 public static Result ScoreNv12(IntPtr y,IntPtr uv,int width,int height,int pitch){
  if(width<2||width>4096||height<2||height>2304||(width&1)!=0||(height&1)!=0||pitch<width||(pitch&1)!=0||pitch>int.MaxValue/height)throw new ArgumentException("Invalid NV12 geometry");
  if(y==IntPtr.Zero||uv==IntPtr.Zero)throw new ArgumentException("Null capture plane");
  Span<byte> left=stackalloc byte[LeftW*LeftH];Span<byte> right=stackalloc byte[RightW*RightH];Span<byte> yellowMask=stackalloc byte[RightW*RightH];Span<byte> chroma=stackalloc byte[RightW*RightH];int yellow=0;
  Sample(y,uv,width,height,pitch,LeftX,LeftY,LeftW,LeftH,left,Span<byte>.Empty,Span<byte>.Empty,ref yellow);
  Sample(y,uv,width,height,pitch,RightX,RightY,RightW,RightH,right,yellowMask,chroma,ref yellow);
  return Score(left,right,yellow,yellowMask,chroma);
 }
 static void Sample(IntPtr yp,IntPtr uv,int width,int height,int pitch,int ox,int oy,int w,int h,Span<byte> data,Span<byte> yellowMask,Span<byte> chroma,ref int yellow){
  for(int yy=0;yy<h;yy++){int sy=(oy+yy)*height/270;for(int xx=0;xx<w;xx++){
   int sx=(ox+xx)*width/480,pair=(sy/2)*pitch+(sx/2)*2;
   double l=Marshal.ReadByte(yp,sy*pitch+sx),u=Marshal.ReadByte(uv,pair)-128,v=Marshal.ReadByte(uv,pair+1)-128;
   int r=Clamp(l+1.402*v),g=Clamp(l-.344*u-.714*v),b=Clamp(l+1.772*u);
   data[yy*w+xx]=Gray(r,g,b);
   if(!chroma.IsEmpty)chroma[yy*w+xx]=YouTubeTimerReader.Chroma(r,g,b);
   if(!yellowMask.IsEmpty){bool isYellow=Yellow(r,g,b);yellowMask[yy*w+xx]=isYellow?(byte)1:(byte)0;if(ox+xx>=438&&ox+xx<463&&oy+yy<254&&isYellow)yellow++;}
  }}
 }
 static double Correlation(ReadOnlySpan<byte> patch,int stride,byte[] template,int w,int h,int x,int y,out double mean){
  double a=0,b=0,aa=0,bb=0,ab=0;int n=w*h;
  for(int j=0;j<h;j++)for(int i=0;i<w;i++){double v=patch[(y+j)*stride+x+i],t=template[j*w+i];a+=v;b+=t;aa+=v*v;bb+=t*t;ab+=v*t;}
  mean=a/n;double variance=aa-a*a/n,reference=bb-b*b/n;
  // Require real text contrast, not amplified numerical noise on flat video.
  return variance/n<100||reference<1?0:(ab-a*b/n)/Math.Sqrt(variance*reference);
 }
 static Result Score(ReadOnlySpan<byte> left,ReadOnlySpan<byte> right,int yellow,ReadOnlySpan<byte> yellowMask,ReadOnlySpan<byte> chroma){
  double label=0,countdown=0,skip=0;int skipX=0,skipY=0;
  for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
   label=Math.Max(label,Correlation(left,LeftW,Label,32,8,43+dx-LeftX,246+dy-LeftY,out _));
   label=Math.Max(label,Correlation(left,LeftW,SimpleLabel,32,8,19+dx-LeftX,239+dy-LeftY,out _));
  }
  for(int dy=-1;dy<=1;dy++)for(int dx=-8;dx<=1;dx++)countdown=Math.Max(countdown,Correlation(right,RightW,Countdown,21,10,419+dx-RightX,238+dy-RightY,out _));
  // YouTube's QR/Send-to-phone end card shifts this same highlighted Skip
  // control six pixels left. Match its text and arrow, excluding the badge.
  for(int dy=-1;dy<=1;dy++)for(int dx=-8;dx<=2;dx++){double s=Correlation(right,RightW,Skip,33,15,410+dx-RightX,236+dy-RightY,out double mean);if(mean>=140&&s>skip){skip=s;skipX=410+dx;skipY=236+dy;}}
  int digits=0,ring=0,noise=0,rowBits=0,columnBits=0,sectorBits=0;
  for(int y=234;y<255;y++)for(int x=438;x<463;x++){
   if(yellowMask[(y-RightY)*RightW+x-RightX]==0)continue;
   int radius=(x-452)*(x-452)+(y-243)*(y-243);
   bool core=x>=448&&x<=456&&y>=241&&y<=245;
   if(core){digits++;rowBits|=1<<(y-241);columnBits|=1<<(x-448);}
   if(radius>=49&&radius<=100){ring++;sectorBits|=1<<((x>=452?1:0)+(y>=243?2:0));}
   if(radius<49&&!core)noise++;
  }
  int rows=Bits(rowBits),columns=Bits(columnBits),sectors=Bits(sectorBits);
  bool circle=YouTubeDetectionPolicy.Circle(digits,ring,rows,columns,sectors,noise);
  bool ready=skip>=SkipThreshold,timer=countdown>=CountdownThreshold&&yellow>=5;
  var reading=(timer||circle)&&!ready?YouTubeTimerReader.Read(chroma,RightW,RightX,RightY):new YouTubeTimerReader.Reading();
  return new Result{sponsoredScore=label,countdownScore=countdown,skipScore=skip,skipX=ready?(int?)skipX:null,skipY=ready?(int?)skipY:null,yellowPixels=yellow,
   circleDigitPixels=digits,circleRingPixels=ring,circleRows=rows,circleColumns=columns,circleSectors=sectors,circleNoise=noise,
   timerReader=YouTubeTimerReader.Reader,timerSeconds=reading.seconds,timerMaxSeconds=reading.maxSeconds,timerScore=reading.score,timerLayoutMargin=reading.layoutMargin,
   controlKind=ready?"skip":timer?"skip-in":circle?"circle":"none",hit=ready||timer||circle,skipReady=ready,state=ready?"skip":timer||circle?"countdown":"unknown"};
 }
 static int Bits(int value){int n=0;while(value!=0){n+=value&1;value>>=1;}return n;}
}
