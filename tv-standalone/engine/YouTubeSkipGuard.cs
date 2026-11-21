using System;

// One attempt per observed ad break, with a persisted minimum interval. Missing
// observations, card frames and errors cannot rearm the latch. No key IO here.
public sealed class YouTubeSkipGuard {
 public long LastAttempt {get;private set;}
 public bool Attempted {get;private set;}
 long clearSince,lastClear;
 public YouTubeSkipGuard(long lastAttempt=0){LastAttempt=lastAttempt;Attempted=lastAttempt>0;}
 public void Observe(long now,bool currentUncoveredEvidence,bool adControls){
  if(!currentUncoveredEvidence){clearSince=lastClear=0;return;}
  if(adControls){clearSince=lastClear=0;return;}
  if(clearSince==0||now-lastClear>3000)clearSince=now;
  lastClear=now;
  if(now-clearSince>=8000)Attempted=false;
 }
 public bool TryAttempt(long now,long frameAt,bool enabled,bool regularYouTube,bool highlightedSkip,long navigationAge,bool sameSession){
  if(!enabled||!regularYouTube||!highlightedSkip||!sameSession||navigationAge<3000||now<frameAt||now-frameAt>1500||Attempted||(LastAttempt>0&&(now<LastAttempt||now-LastAttempt<60000)))return false;
  Attempted=true;LastAttempt=now;clearSince=lastClear=0;return true;
 }
}
