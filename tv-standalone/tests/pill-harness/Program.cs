using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;

internal static class Program
{
    private static void Throws(Action action)
    {
        try { action(); } catch (ArgumentException) { return; }
        throw new Exception("Expected argument rejection");
    }
    private static int Main(string[] args)
    {
        IntPtr native = IntPtr.Zero;
        try
        {
            if (args.Length == 1 && args[0] == "--self-test")
            {
                Throws(() => SponsoredPill.ScoreRgb(null!));
                Throws(() => SponsoredPill.ScoreRgb(new byte[1]));
                Throws(() => SponsoredPill.ScoreRgb(new byte[480*270*3], 270, 480));
                Throws(() => SponsoredPill.ScoreNv12(IntPtr.Zero, IntPtr.Zero, 480, 270, 480));
                // Non-null dummy pointers must never be read when geometry is invalid.
                foreach (int[] g in new[] { new[]{0,270,480}, new[]{481,270,482}, new[]{480,271,480},
                    new[]{4098,270,4098}, new[]{480,2306,480}, new[]{480,270,479}, new[]{480,270,481}, new[]{480,270,Int32.MaxValue-1} })
                    Throws(() => SponsoredPill.ScoreNv12(new IntPtr(1), new IntPtr(1), g[0], g[1], g[2]));
                Console.WriteLine("{\"self_test\":true}"); return 0;
            }
            bool nv12 = args.Length > 0 && args[0] == "--nv12";
            int baseCount = nv12 ? 5 : 1;
            if (args.Length != baseCount && args.Length != baseCount + 2)
                throw new ArgumentException("Usage: PillHarness.dll RGB_FILE [--bench 1..10000] OR --nv12 Y_UV_FILE width height pitch [--bench 1..10000]");
            int repeats = 1;
            if (args.Length > baseCount && (args[baseCount] != "--bench" || !Int32.TryParse(args[baseCount+1], out repeats) || repeats < 1 || repeats > 10000))
                throw new ArgumentException("Invalid benchmark count");
            int width = nv12 ? Int32.Parse(args[2]) : 480, height = nv12 ? Int32.Parse(args[3]) : 270, pitch = nv12 ? Int32.Parse(args[4]) : 480;
            string path = args[nv12 ? 1 : 0];
            long bytes = new FileInfo(path).Length;
            if (bytes <= 0 || bytes > 64*1024*1024) throw new ArgumentException("Fixture must be 1 byte..64 MiB");
            byte[] data = File.ReadAllBytes(path);
            Func<double> score;
            if (nv12)
            {
                long yBytes = (long)pitch * height;
                if (width < 2 || height < 2 || pitch < width || yBytes > Int32.MaxValue || data.LongLength != yBytes + yBytes/2)
                    throw new ArgumentException("Invalid NV12 fixture geometry/length");
                native = Marshal.AllocHGlobal(data.Length);
                Marshal.Copy(data, 0, native, data.Length);
                IntPtr uv = IntPtr.Add(native, (int)yBytes);
                score = () => SponsoredPill.ScoreNv12(native, uv, width, height, pitch);
            }
            else score = () => SponsoredPill.ScoreRgb(data);
            double value = score(); // Warm JIT before timing; no IO or fixture preparation timed.
            Stopwatch timer = Stopwatch.StartNew();
            long allocatedBefore = GC.GetAllocatedBytesForCurrentThread();
            int completed = 0;
            while (completed < repeats && timer.ElapsedMilliseconds < 5000) { value = score(); completed++; }
            long allocated = GC.GetAllocatedBytesForCurrentThread() - allocatedBefore;
            double elapsed = timer.Elapsed.TotalMilliseconds;
            Console.WriteLine(JsonSerializer.Serialize(new { score=value, present=value>=SponsoredPill.Threshold,
                threshold=SponsoredPill.Threshold, template_sha256=SponsoredPill.TemplateSha256, iterations=completed,
                elapsed_ms=elapsed, mean_ms=completed>0 ? elapsed/completed : 0, allocated_bytes=allocated,
                timing_scope="score only; warmed JIT; excludes file IO and fixture preparation", source=nv12 ? "nv12" : "rgb" }));
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error.GetType().Name + ": " + error.Message); return 1; }
        finally { if (native != IntPtr.Zero) Marshal.FreeHGlobal(native); }
    }
}
