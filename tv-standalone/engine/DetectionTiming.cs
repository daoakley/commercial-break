using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;

internal enum DetectionStage { CaptureStarted, CaptureFinished, LocalPositive, RemoteSubmitted, RemoteFinished, RemoteError, Accepted, CoverRequested, MuteCompleted, WindowShown, Released, Discarded }

// Bounded, scalar-only diagnostics. Capture/control paths enqueue; maintenance flushes.
internal sealed class DetectionTiming
{
    readonly object gate = new object();
    readonly Queue<object> pending = new Queue<object>();
    readonly string path;
    long sequence, dropped;
    object latest;
    public static long Clock => Environment.TickCount64;
    public DetectionTiming(string home) { path = Path.Combine(home, "diagnostics", "timing.jsonl"); }
    public long Begin() { lock (gate) return ++sequence; }
    public void Record(long id, DetectionStage stage, long started, long? completed = null)
    {
        long elapsed = (completed ?? Clock) - started;
        if (id <= 0 || elapsed < 0 || elapsed > 86400000) return;
        lock (gate)
        {
            latest = new { at = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), captureId = id, stage = stage.ToString(), elapsedMs = elapsed };
            if (pending.Count == 256) { pending.Dequeue(); dropped++; }
            pending.Enqueue(latest);
        }
    }
    public object Status() { lock (gate) return new { latest, dropped, pending = pending.Count }; }
    public void Flush()
    {
        var batch = new List<object>();
        lock (gate) { while (pending.Count > 0) batch.Add(pending.Dequeue()); }
        if (batch.Count == 0) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            if (File.Exists(path) && new FileInfo(path).Length >= 65536)
            {
                if (File.Exists(path + ".1")) File.Move(path + ".1", path + ".2", true);
                File.Move(path, path + ".1", true);
            }
            using var output = new StreamWriter(path, true);
            foreach (var item in batch) output.WriteLine(JsonSerializer.Serialize(item));
        }
        catch { lock (gate) dropped += batch.Count; }
    }

    public static string Version => Assembly.GetExecutingAssembly().GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;

    public static object BuildIdentity()
    {
        var assembly = Assembly.GetExecutingAssembly();
        string hash = null;
        try
        {
            using var file = File.OpenRead(assembly.Location);
            using var sha = SHA256.Create();
            hash = BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
        }
        catch { }
        return new { version = Version,
                     binarySha256 = hash };
    }
}
