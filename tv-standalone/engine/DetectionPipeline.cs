using System;
using System.IO;
using System.Text.Json;

partial class Program
{
    static readonly RecognitionLane<SamsungRecognitionClient.Reply> SamsungLane = new RecognitionLane<SamsungRecognitionClient.Reply>();
    static readonly SamsungRecognitionClient SamsungClient = new SamsungRecognitionClient();
    static DetectionTiming Timing;
    static object Build;
    static string SamsungError = "";
    static bool RemoteNeedsMaskedCapture;
    static long ActiveCaptureId, ActiveCaptureStarted, CoverCaptureId, CoverCaptureStarted;
    static bool CoverReceiptSeen;

    sealed class RemoteRecognition
    {
        public EvidenceSession session;
        public long captureId;
        public bool keepCard;
        public string mode;
        public JsonElement fingerprint;
        public PendingDebug debug;
    }
    static RemoteRecognition RemoteJob;
    static long lastAppPoll = -200;
    static string polledApp = "";

    static string PollApp()
    {
        long now = DetectionTiming.Clock;
        if (now - lastAppPoll >= 200)
        {
            polledApp = App();
            lastAppPoll = DetectionTiming.Clock;
        }
        return polledApp;
    }

    static void InvalidateRemote()
    {
        SamsungLane.Cancel();
        RemoteNeedsMaskedCapture = false;
    }

    static void ObserveOverlay()
    {
        if (!Covered || CoverReceiptSeen || CoverCaptureId == 0) return;
        long? at = OverlayReceipt.Read(State + "/overlay-lease", CoverCaptureId, CoverCaptureStarted, DetectionTiming.Clock);
        if (!at.HasValue) return;
        Timing.Record(CoverCaptureId, DetectionStage.WindowShown, CoverCaptureStarted, at);
        CoverReceiptSeen = true;
    }

    static void AcceptAd(EvidenceSession session, long captureId)
    {
        lock (Gate)
        {
            if (!session.Current(App(), Generation, NavigationAt(), DetectionTiming.Clock, Enabled && !MaintenancePaused))
            {
                Timing.Record(captureId, DetectionStage.Discarded, session.Started);
                return;
            }
            if (OtherActive() || (ArtMode == "on" && Now() - ArtObserved < 6000)) return;
            if (TryYouTubeSkip(session.Navigation, session.Generation)) return;
            ActiveCaptureId = captureId;
            ActiveCaptureStarted = session.Started;
            Timing.Record(captureId, DetectionStage.Accepted, session.Started);
            Matches++;
            LastAccepted = LastAd = Now();
            if (Covered && CoverSource == "audio-splice")
            {
                Record("confirm", LastMatchSource + " confirmed audio cover");
                CoverSource = LastMatchSource;
                AudioCoverConfirmed = true;
            }
            Cover();
            Message = "Commercial matched";
            if (IsRegularYouTube(session.App) && Covered && Countdown.Observe(TimerEvidence, Now()))
            {
                Next = DetectionTiming.Clock + Math.Max(0, Countdown.CheckAt - Now());
                CountdownHolds++;
                Message = "YouTube countdown — card held steady";
            }
        }
    }

    static void FinishRemote(bool allowActions, string app)
    {
        var completion = SamsungLane.Take(DetectionTiming.Clock);
        if (completion == null) return;
        var job = RemoteJob;
        RemoteJob = null;
        if (job == null) return;
        var debug = job.debug;
        if (debug != null) debug.remotePending = false;
        bool current = !completion.Cancelled && job.session.Current(app, Generation, NavigationAt(), DetectionTiming.Clock,
            allowActions && Enabled && !MaintenancePaused);
        if (completion.Value != null)
        {
            Queries++;
            var reply = completion.Value;
            if (debug != null)
            {
                debug.requestAt = reply.RequestAt;
                debug.responseAt = reply.ResponseAt;
                debug.response = reply.Response;
                debug.verdict = current ? (reply.Ad ? "ad" : "unknown") : "discarded_session_or_expiry";
            }
        }
        if (!current)
        {
            if (debug != null) debug.verdict = "discarded_session_or_expiry";
            Timing.Record(job.captureId, DetectionStage.Discarded, job.session.Started);
            return;
        }
        if (completion.Error != null)
        {
            // This is a cloud failure, not evidence against a recent local positive.
            // Existing leases still expire; no failed request can renew a cover.
            SamsungError = completion.Error.GetType().Name;
            if (debug != null) debug.error = "samsung: " + SamsungError;
            Health?.Error("samsung", completion.Error);
            Timing.Record(job.captureId, DetectionStage.RemoteError, job.session.Started);
            Record("samsung-error", SamsungError);
            return;
        }
        SamsungError = "";
        var result = completion.Value;
        Timing.Record(job.captureId, DetectionStage.RemoteFinished, job.session.Started);
        try
        {
            File.WriteAllText(State + "/last-reply.json", JsonSerializer.Serialize(new {
                at = job.fingerprint.GetProperty("at").GetInt64().ToString(), receivedAt = result.ResponseAt,
                captureMode = job.mode, response = result.Response }));
        }
        catch (IOException error) { Health?.Error("reply-write", error); }
        if (result.Ad)
        {
            if (job.keepCard) SteadyCardMatches++;
            LastMatchSource = "samsung";
            AcceptAd(job.session, job.captureId);
        }
        else if (Covered && job.keepCard)
        {
            RemoteNeedsMaskedCapture = true;
            Next = 0;
        }
        Record("reply", result.Ad ? "ad" : "unknown");
    }
}
