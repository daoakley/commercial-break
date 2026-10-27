using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

internal static class Program
{
    [DllImport("libmobileclip-bench.so", EntryPoint = "benchmark_entry", CallingConvention = CallingConvention.Cdecl)]
    private static extern int BenchmarkEntry(int argc, IntPtr argv);

    [DllImport("libc.so.6", EntryPoint = "kill", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Kill(int pid, int signal);

    [DllImport("libdl.so.2", EntryPoint = "dlopen", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr Dlopen([MarshalAs(UnmanagedType.LPUTF8Str)] string path, int flags);

    [DllImport("libdl.so.2", EntryPoint = "dlerror", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr Dlerror();

    [DllImport("libdl.so.2", EntryPoint = "dlclose", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Dlclose(IntPtr handle);

    private static IntPtr LoadBenchmarkLibrary()
    {
        string absolute = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "libmobileclip-bench.so"));
        Console.Error.WriteLine("managed_native_library_absolute=" + absolute);
        try
        {
            // Absolute path bypasses loader search paths, including LD_LIBRARY_PATH
            // ignored when the dotnet host runs with executable capabilities.
            return NativeLibrary.Load(absolute);
        }
        catch (Exception error)
        {
            string detail = "";
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux))
            {
                try
                {
                    Dlerror(); // Clear this thread's previous loader error.
                    IntPtr handle = Dlopen(absolute, 2); // RTLD_NOW | RTLD_LOCAL.
                    if (handle == IntPtr.Zero)
                    {
                        IntPtr message = Dlerror();
                        detail = " dlopen: " + (Marshal.PtrToStringUTF8(message) ?? "no loader detail");
                    }
                    else
                    {
                        Dlclose(handle);
                        detail = " dlopen diagnostic succeeded despite NativeLibrary.Load failure";
                    }
                }
                catch (Exception diagnostic)
                {
                    detail = " dlopen diagnostic unavailable: " + diagnostic.GetType().Name + ": " + diagnostic.Message;
                }
            }
            throw new DllNotFoundException("Absolute native load failed: " + absolute + ". " + error.Message + detail, error);
        }
    }

    private static int BoundedEnvironment(string name, int fallback, int minimum, int maximum)
    {
        string? value = Environment.GetEnvironmentVariable(name);
        if (String.IsNullOrEmpty(value)) return fallback;
        if (!Int32.TryParse(value, out int parsed) || parsed < minimum || parsed > maximum)
            throw new ArgumentException(name + " must be between " + minimum + " and " + maximum);
        return parsed;
    }

    private static long ResidentBytes(Process process)
    {
        if (File.Exists("/proc/self/status"))
        {
            foreach (string line in File.ReadLines("/proc/self/status"))
            {
                if (!line.StartsWith("VmRSS:", StringComparison.Ordinal)) continue;
                string[] parts = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length >= 2 && Int64.TryParse(parts[1], NumberStyles.Integer,
                    CultureInfo.InvariantCulture, out long kilobytes)) return kilobytes * 1024;
            }
        }
        process.Refresh();
        return process.WorkingSet64;
    }

    private static void HardStop(Process process, string reason)
    {
        Console.Error.WriteLine("managed_watchdog_stop " + reason);
        Console.Error.Flush();
        try { Kill(process.Id, 9); } catch { }
        Environment.Exit(124);
    }

    public static int Main(string[] args)
    {
        if (args.Length != 6 || !Int32.TryParse(args[4], out int iterations) || iterations < 1 || iterations > 10 ||
            !Int32.TryParse(args[5], out int threads) || threads < 1 || threads > 4)
        {
            Console.Error.WriteLine("Usage: dotnet MobileClipBench.dll model.param model.bin input.f32 reference.f32 iterations(1..10) threads(1..4)");
            return 64;
        }
        IntPtr argv = IntPtr.Zero;
        IntPtr[] strings = new IntPtr[args.Length + 1];
        using var finished = new ManualResetEventSlim(false);
        using var process = Process.GetCurrentProcess();
        Thread? watchdog = null;
        try
        {
            NativeLibrary.SetDllImportResolver(typeof(Program).Assembly,
                (name, assembly, searchPath) => name == "libmobileclip-bench.so" ? LoadBenchmarkLibrary() : IntPtr.Zero);
            foreach (string path in new[] { args[0], args[1], args[2], args[3] })
                if (!File.Exists(path)) throw new FileNotFoundException("Benchmark input missing", path);
            int seconds = BoundedEnvironment("MOBILECLIP_DEADLINE_SECONDS", 30, 1, 30);
            long limit = (long)BoundedEnvironment("MOBILECLIP_MAX_RSS_MIB", 192, 64, 512) * 1024 * 1024;
            Stopwatch clock = Stopwatch.StartNew();
            watchdog = new Thread(() =>
            {
                while (!finished.Wait(100))
                {
                    if (clock.Elapsed.TotalSeconds >= seconds) HardStop(process, "deadline_seconds=" + seconds);
                    try
                    {
                        long resident = ResidentBytes(process);
                        if (resident > limit) HardStop(process, "rss_bytes=" + resident + " limit_bytes=" + limit);
                    }
                    catch (Exception error)
                    {
                        // Missing monitoring is a reason to stop this optional benchmark.
                        HardStop(process, "rss_monitor_failed=" + error.GetType().Name);
                    }
                }
            }) { IsBackground = true, Name = "benchmark-watchdog" };
            watchdog.Start();
            string[] nativeArgs = new string[strings.Length];
            nativeArgs[0] = "mobileclip-bench";
            Array.Copy(args, 0, nativeArgs, 1, args.Length);
            argv = Marshal.AllocHGlobal((strings.Length + 1) * IntPtr.Size);
            for (int i = 0; i < nativeArgs.Length; i++)
            {
                byte[] bytes = Encoding.UTF8.GetBytes(nativeArgs[i] + "\0");
                strings[i] = Marshal.AllocHGlobal(bytes.Length);
                Marshal.Copy(bytes, 0, strings[i], bytes.Length);
                Marshal.WriteIntPtr(argv, i * IntPtr.Size, strings[i]);
            }
            Marshal.WriteIntPtr(argv, strings.Length * IntPtr.Size, IntPtr.Zero);
            Console.Error.WriteLine("managed_benchmark_start deadline_seconds=" + seconds + " rss_limit_bytes=" + limit);
            return BenchmarkEntry(strings.Length, argv);
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("managed_benchmark_error " + error.GetType().Name + ": " + error.Message);
            return 70;
        }
        finally
        {
            finished.Set();
            watchdog?.Join(1000);
            foreach (IntPtr value in strings) if (value != IntPtr.Zero) Marshal.FreeHGlobal(value);
            if (argv != IntPtr.Zero) Marshal.FreeHGlobal(argv);
        }
    }
}
