using System;
using System.Collections.Generic;
using System.Text.Json;

// Additional continuation evidence, never authority to start or resurrect a cover.
internal sealed class ArchiveContinuation
{
    public const long LeaseMs = 8000, BudgetMs = 45000, QuietMs = 60000;
    readonly Queue<(long at, bool hit)> pending = new Queue<(long, bool)>();
    readonly Queue<bool> baseline = new Queue<bool>();
    long excludedUntil, lastStrong;
    bool frozenEligible;
    int hits;
    public bool Enabled;
    public long Until { get; private set; }
    public long Qualifying, Renewals, WouldRenew, BudgetBlocked, BaselineBlocked, UncoveredPairs;
    bool previousUncovered;
    public int BaselineCount => baseline.Count;
    public double BaselineShare => baseline.Count == 0 ? 0 : (double)hits / baseline.Count;
    public bool BaselineEligible => baseline.Count >= 40 && BaselineShare <= .05;
    public void ResetSession()
    {
        pending.Clear(); baseline.Clear(); hits=0; lastStrong=Until=0;
        excludedUntil=0; frozenEligible=false; previousUncovered=false;
    }
    void Mature(long now)
    {
        while(pending.Count>0 && now-pending.Peek().at>=QuietMs)
        {
            var item=pending.Dequeue(); baseline.Enqueue(item.hit); if(item.hit)hits++;
            if(baseline.Count>200 && baseline.Dequeue())hits--;
        }
    }
    public void Strong(long now, bool starting)
    {
        if(starting){Mature(now);frozenEligible=BaselineEligible;pending.Clear();}
        lastStrong=now;Until=0;previousUncovered=false;
    }
    public void Released(long now)
    {
        Until=lastStrong=0;frozenEligible=false;pending.Clear();previousUncovered=false;
        excludedUntil=now+QuietMs;
    }
    public void BreakSequence(){previousUncovered=false;}
    public long Observe(long now, bool qualifies, bool covered, long strongExpiry, bool liveLease)
    {
        if(qualifies)Qualifying++;
        if(!covered)
        {
            if(qualifies && previousUncovered)UncoveredPairs++;
            previousUncovered=qualifies;
            Mature(now);
            if(now>=excludedUntil){pending.Enqueue((now,qualifies));while(pending.Count>512)pending.Dequeue();}
            return 0;
        }
        previousUncovered=false;
        if(!qualifies || !liveLease || lastStrong<=0 || now>=Math.Max(strongExpiry,Until))return 0;
        if(!frozenEligible){BaselineBlocked++;return 0;}
        long deadline=lastStrong+BudgetMs;
        if(now>=deadline){BudgetBlocked++;return 0;}
        WouldRenew++;
        if(!Enabled)return 0;
        Until=Math.Min(now+LeaseMs,deadline);Renewals++;return Until;
    }
    public object Status()=>new{enabled=Enabled,budgetMs=BudgetMs,qualifyingReplies=Qualifying,renewals=Renewals,
        wouldRenew=WouldRenew,blockedByBudget=BudgetBlocked,blockedByBaseline=BaselineBlocked,
        baselineCount=BaselineCount,baselineShare=BaselineShare,baselineEligible=BaselineEligible,
        coverBaselineEligible=frozenEligible,uncoveredConsecutivePairs=UncoveredPairs,until=Until};

    static JsonElement Get(JsonElement value,string name)=>value.ValueKind==JsonValueKind.Object && value.TryGetProperty(name,out var v)?v:default;
    public static bool Qualifies(JsonElement response,string at)=>TryRead(response,at,out bool qualifies)&&qualifies;
    public static bool TryRead(JsonElement response,string at,out bool qualifies)
    {
        qualifies=false;
        if(string.IsNullOrEmpty(at))return false;
        var frames=Get(Get(Get(response,"result"),"acr"),"result_frames");
        if(frames.ValueKind!=JsonValueKind.Array)return false;
        foreach(var f in frames.EnumerateArray())
        {
            var utc=Get(Get(f,"tvt"),"utc");var dist=Get(f,"dist");var mm=Get(f,"mm_count");
            if(utc.ValueKind!=JsonValueKind.String || utc.GetString()!=at || Get(f,"matching").ValueKind!=JsonValueKind.True ||
                dist.ValueKind!=JsonValueKind.Number || !dist.TryGetInt32(out int d) || d<0 || d>15 || mm.ValueKind!=JsonValueKind.Array || mm.GetArrayLength()!=4)continue;
            int[] n=new int[4];bool valid=true;int i=0;
            foreach(var v in mm.EnumerateArray()){if(v.ValueKind!=JsonValueKind.Number || !v.TryGetInt32(out n[i]) || n[i]<0)valid=false;i++;}
            if(valid){qualifies=n[2]>=2 && n[2]>n[1];return true;}
        }
        return false;
    }
}

internal sealed class MaskedLookPolicy
{
    long deadline,lastAttempt;int attempts;bool deferred;
    public long Looks,Deferrals;
    public void Reset(){deadline=lastAttempt=0;attempts=0;deferred=false;}
    public bool Begin(long now,long expiry)
    {
        if(expiry!=deadline){deadline=expiry;attempts=0;deferred=false;}
        long remaining=expiry-now;
        if(remaining<=0 || remaining>2500 || attempts>=(deferred?2:1) || now-lastAttempt<500 || (attempts>0 && remaining<1200))return false;
        attempts++;lastAttempt=now;Looks++;return true;
    }
    public void Complete(bool safelyDeferred){deferred=safelyDeferred;if(safelyDeferred)Deferrals++;}
}
