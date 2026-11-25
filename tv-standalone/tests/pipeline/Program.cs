using System;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

static class Tests
{
    static int checks;
    static void Check(bool value, string description)
    {
        checks++;
        if (!value) throw new Exception(description);
    }

    static void Scheduling()
    {
        var lane = new RecognitionLane<bool>();
        var slow = new TaskCompletionSource<bool>();
        int requests = 0, localChecks = 0, localHits = 0;
        Func<CancellationToken, Task<bool>> request = token => { requests++; return slow.Task; };
        Check(lane.TryStart(0, request), "start first request");
        for (int now = 0; now < 2500; now += 500)
        {
            localChecks++;
            if (now == 1000) localHits++;
            Check(!lane.TryStart(now, request), "no second request or backlog while first waits");
            Check(lane.Take(now) == null, "unfinished request does not block caller");
        }
        Check(requests == 1 && localChecks == 5 && localHits == 1, "local positive remains available through slow request");
        slow.SetException(new TimeoutException());
        Check(lane.Take(2500).Error is TimeoutException, "failure is collected separately");
        Check(!lane.Ready(6499) && lane.Ready(6500), "first failure has four-second cloud-only backoff");
        for (int now = 2500; now < 6500; now += 500) localChecks++;
        Check(localChecks == 13, "cloud backoff does not schedule local checks");
        Check(lane.TryStart(6500, _ => Task.FromResult(true)), "retry after backoff");
        Check(lane.Take(6501).Value && lane.Ready(6501), "success resets cloud backoff");

        long time = 7000;
        foreach (int delay in new[] { 4000, 8000, 16000, 32000, 60000, 60000 })
        {
            Check(lane.TryStart(time, _ => throw new IOException()), "synchronous transport failure is bounded");
            Check(lane.Take(time).Error is IOException, "failure remains isolated");
            Check(!lane.Ready(time + delay - 1) && lane.Ready(time + delay), "bounded exponential cloud retry");
            time += delay;
        }
        lane.Cancel();
        var old = new TaskCompletionSource<bool>();
        CancellationToken cancelled = default;
        lane.TryStart(time, token => { cancelled = token; return old.Task; });
        lane.Cancel();
        Check(cancelled.IsCancellationRequested, "session invalidation signals transport cancellation");
        Check(!lane.TryStart(time, request), "cancelled operation keeps slot until actually stopped");
        old.SetResult(true);
        Check(lane.Take(time).Cancelled, "late positive after cancellation is discarded");
        Check(lane.TryStart(time, _ => Task.FromResult(false)), "new session can start after old operation drains");
        Check(!lane.Take(time).Value && lane.Ready(time), "no match is not a failure");
    }

    static void Sessions()
    {
        var session = new EvidenceSession { App = "test-tv-app", Generation = 1, Navigation = 2, Started = 100 };
        Check(session.Current("test-tv-app", 1, 2, 200, true), "fresh same-session result accepted");
        Check(!session.Current("other-app", 1, 2, 200, true), "app change rejects result");
        Check(!session.Current("test-tv-app", 1, 3, 200, true), "same-app navigation rejects result");
        Check(!session.Current("test-tv-app", 2, 2, 200, true), "Off/On generation rejects old result");
        Check(!session.Current("test-tv-app", 1, 2, 200, false), "disabled/maintenance rejects result");
        Check(!session.Current("test-tv-app", 1, 2, 99, true), "backward time rejects result");
        Check(!session.Current("test-tv-app", 1, 2, 5101, true), "expired positive cannot renew cover");
    }

    static void Diagnostics(string root)
    {
        var timing = new DetectionTiming(root);
        long id = timing.Begin();
        for (int i = 0; i < 300; i++) timing.Record(id, DetectionStage.CaptureStarted, 100, 101);
        var status = JsonSerializer.SerializeToElement(timing.Status());
        Check(status.GetProperty("pending").GetInt32() == 256 && status.GetProperty("dropped").GetInt32() == 44, "bounded diagnostic backlog");
        timing.Flush();
        string file = Path.Combine(root, "diagnostics", "timing.jsonl");
        string text = File.ReadAllText(file);
        Check(!text.Contains(root) && !text.Contains("Exception"), "logs contain no path or arbitrary exception payload");
        foreach (string line in File.ReadAllLines(file))
        {
            var row = JsonDocument.Parse(line).RootElement;
            Check(row.GetProperty("elapsedMs").GetInt64() == 1 && row.GetProperty("stage").GetString() == "CaptureStarted", "scalar trace is replayable");
        }
        timing.Record(id, DetectionStage.Accepted, 101, 100);
        Check(JsonSerializer.SerializeToElement(timing.Status()).GetProperty("pending").GetInt32() == 0, "invalid clock values omitted");
        File.WriteAllText(file, new string('x', 65536));
        timing.Record(id, DetectionStage.Accepted, 100, 101); timing.Flush();
        Check(new FileInfo(file + ".1").Length == 65536 && new FileInfo(file).Length < 1024, "timing log rotates");
        string blocked = Path.Combine(root, "not-a-directory"); File.WriteAllText(blocked, "x");
        var unavailable = new DetectionTiming(blocked);
        unavailable.Record(1, DetectionStage.LocalPositive, 100, 101); unavailable.Flush();
        Check(JsonSerializer.SerializeToElement(unavailable.Status()).GetProperty("dropped").GetInt32() == 1, "diagnostic IO failure is nonfatal");
        Check(JsonSerializer.SerializeToElement(DetectionTiming.BuildIdentity()).GetProperty("binarySha256").GetString().Length == 64, "running assembly identified by hash");

        string lease = Path.Combine(root, "overlay-lease");
        long started = Environment.TickCount64, previous = 0;
        File.WriteAllText(lease + ".request", "9 " + started);
        OverlayReceipt.Publish(lease, ref previous);
        Check(previous == 9 && OverlayReceipt.Read(lease, 9, started, Environment.TickCount64).HasValue, "renderer receipt correlates to request");
        Check(!OverlayReceipt.Read(lease, 10, started, Environment.TickCount64).HasValue, "old cover receipt rejected");
        Check(!OverlayReceipt.Read(lease, 9, Environment.TickCount64 + 1, Environment.TickCount64).HasValue, "old process receipt rejected");
        File.WriteAllText(lease + ".request", "10 " + (started - 9000));
        OverlayReceipt.Publish(lease, ref previous);
        Check(previous == 9, "expired show request not acknowledged");
        File.WriteAllText(lease + ".request", "invalid"); OverlayReceipt.Publish(lease, ref previous);
        Check(previous == 9, "invalid receipt cannot crash rendering");
    }

    static void Main()
    {
        string root = Path.Combine(Path.GetTempPath(), "commercial-break-pipeline-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try { Scheduling(); Sessions(); Diagnostics(root); }
        finally { Directory.Delete(root, true); }
        Console.WriteLine(checks + " pipeline, freshness and diagnostic checks passed");
    }
}
