using System;
using System.Threading;
using System.Threading.Tasks;

// One remote operation, no queue. Native capture remains owned by the main loop.
// This lane's failures/backoff never change the local capture deadline.
internal sealed class RecognitionLane<T>
{
    internal sealed class Completion
    {
        public T Value;
        public Exception Error;
        public bool Cancelled;
    }

    readonly object gate = new object();
    Task<T> pending;
    CancellationTokenSource cancellation;
    long nextAttempt;
    int failures;

    public bool Busy { get { lock (gate) return pending != null; } }
    public bool Ready(long now) { lock (gate) return pending == null && now >= nextAttempt; }

    public bool TryStart(long now, Func<CancellationToken, Task<T>> operation)
    {
        lock (gate)
        {
            if (pending != null || now < nextAttempt) return false;
            cancellation = new CancellationTokenSource();
            try { pending = operation(cancellation.Token); }
            catch (Exception error) { pending = Task.FromException<T>(error); }
            return true;
        }
    }

    public void Cancel()
    {
        lock (gate)
        {
            // Do not free the slot before the old operation has actually stopped.
            cancellation?.Cancel();
            failures = 0;
            nextAttempt = 0;
        }
    }

    public Completion Take(long now)
    {
        lock (gate)
        {
            if (pending == null || !pending.IsCompleted) return null;
            var result = new Completion { Cancelled = cancellation.IsCancellationRequested };
            try { result.Value = pending.GetAwaiter().GetResult(); }
            catch (Exception error) { result.Error = error; }
            cancellation.Dispose();
            cancellation = null;
            pending = null;
            if (result.Cancelled) return result;
            if (result.Error == null) { failures = 0; nextAttempt = 0; }
            else
            {
                failures = Math.Min(failures + 1, 5);
                nextAttempt = now + Math.Min(60000, 2000 * (1 << failures));
            }
            return result;
        }
    }

    public object Status(long now)
    {
        lock (gate) return new { inFlight = pending != null, failures, retryInMs = Math.Max(0, nextAttempt - now) };
    }
}

internal sealed class EvidenceSession
{
    public string App;
    public long Generation, Navigation, Started;

    public bool Current(string app, long generation, long navigation, long now, bool enabled)
    {
        return enabled && app == App && generation == Generation && navigation == Navigation &&
               now >= Started && now - Started <= 5000;
    }
}
