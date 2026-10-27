using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;

// Only the TV's installed library is loaded. All handles are opaque C API pointers;
// no ncnn C++ object layout or custom native library is required.
internal static class Program
{
    private const string Library = "/usr/lib/libncnn.so";
    private static long PeakRss;
    [DllImport("libc.so.6", EntryPoint = "kill", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Kill(int pid, int signal);
    [DllImport("libc.so.6", EntryPoint = "setpriority", CallingConvention = CallingConvention.Cdecl)]
    private static extern int SetPriority(int which, int who, int priority);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Create();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void Destroy(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Pointer(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Integer(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate UIntPtr Size(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void SetInt(IntPtr p, int value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int StringIndex([MarshalAs(UnmanagedType.LPUTF8Str)] string value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr StringCreate([MarshalAs(UnmanagedType.LPUTF8Str)] string value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr IndexCreate(int value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Load(IntPtr net, [MarshalAs(UnmanagedType.LPUTF8Str)] string path);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Mat3D(int w, int h, int c, IntPtr allocator);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Channel(IntPtr mat, int c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Input(IntPtr ex, [MarshalAs(UnmanagedType.LPUTF8Str)] string name, IntPtr mat);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Extract(IntPtr ex, [MarshalAs(UnmanagedType.LPUTF8Str)] string name, out IntPtr mat);

    private static readonly string[] Operators = {
        "Input", "Convolution", "GELU", "ConvolutionDepthWise", "Split", "MemoryData", "BinaryOp",
        "Reduction", "BatchNorm", "Reshape", "Permute", "Gemm", "Slice", "MatMul", "Softmax", "Pooling", "InnerProduct"
    };
    private static readonly string[] Required = {
        "ncnn_net_create", "ncnn_net_destroy", "ncnn_net_get_option", "ncnn_option_set_num_threads",
        "ncnn_option_set_use_vulkan_compute", "ncnn_option_set_use_packing_layout",
        "ncnn_option_set_use_fp16_packed", "ncnn_option_set_use_fp16_storage", "ncnn_option_set_use_fp16_arithmetic",
        "ncnn_option_set_use_bf16_storage", "ncnn_net_load_param", "ncnn_net_load_model",
        "ncnn_mat_create_3d", "ncnn_mat_destroy", "ncnn_mat_get_channel_data", "ncnn_mat_get_dims",
        "ncnn_mat_get_w", "ncnn_mat_get_h", "ncnn_mat_get_c", "ncnn_mat_get_elemsize", "ncnn_mat_get_elempack",
        "ncnn_mat_get_data", "ncnn_extractor_create", "ncnn_extractor_destroy", "ncnn_extractor_input", "ncnn_extractor_extract"
    };
    private static readonly string[] Optional = {
        "ncnn_version", "ncnn_layer_type_to_index", "ncnn_layer_create_by_type", "ncnn_layer_create_by_typeindex", "ncnn_layer_destroy"
    };

    private static T Function<T>(Dictionary<string, IntPtr> symbols, string name) where T : Delegate =>
        Marshal.GetDelegateForFunctionPointer<T>(symbols[name]);
    private static void Report(object value) { Console.WriteLine(JsonSerializer.Serialize(value)); Console.Out.Flush(); }
    private static int Env(string name, int fallback, int min, int max)
    {
        string? value = Environment.GetEnvironmentVariable(name);
        if (String.IsNullOrEmpty(value)) return fallback;
        if (!Int32.TryParse(value, out int n) || n < min || n > max) throw new ArgumentException(name + " out of bounds");
        return n;
    }
    private static long Rss(Process process)
    {
        long rss = 0;
        if (File.Exists("/proc/self/status"))
        {
            foreach (string line in File.ReadLines("/proc/self/status"))
            {
                if (!line.StartsWith("VmRSS:", StringComparison.Ordinal)) continue;
                string[] parts = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
                rss = Int64.Parse(parts[1], CultureInfo.InvariantCulture) * 1024;
            }
            if (rss <= 0) throw new IOException("VmRSS unavailable");
        }
        else { process.Refresh(); rss = process.WorkingSet64; }
        long prior;
        do { prior = Interlocked.Read(ref PeakRss); if (rss <= prior) break; }
        while (Interlocked.CompareExchange(ref PeakRss, rss, prior) != prior);
        return rss;
    }
    private static void Stop(Process process, string reason)
    {
        Console.Error.WriteLine("stock_probe_watchdog_stop " + reason);
        Console.Error.Flush();
        try { Kill(process.Id, 9); } catch { }
        Environment.Exit(124);
    }
    private static float[] ReadFloats(string path, int count)
    {
        if (!BitConverter.IsLittleEndian) throw new PlatformNotSupportedException("Requires little endian float32 input");
        if (new FileInfo(path).Length != count * 4L) throw new InvalidDataException("Incorrect float32 file length: " + path);
        byte[] bytes = File.ReadAllBytes(path);
        float[] values = new float[count]; Buffer.BlockCopy(bytes, 0, values, 0, bytes.Length);
        if (values.Any(v => Single.IsNaN(v) || Single.IsInfinity(v))) throw new InvalidDataException("Nonfinite input/reference");
        return values;
    }

    public static int Main(string[] args)
    {
        int iterations = 1;
        bool graphOnly = args.Length == 2 && args[0] == "--graph-only";
        if (!graphOnly && ((args.Length != 0 && args.Length != 4 && args.Length != 5 && args.Length != 6) ||
            (args.Length >= 5 && (!Int32.TryParse(args[4], out iterations) || iterations < 1 || iterations > 3)) ||
            (args.Length == 6 && args[5] != "1")))
        {
            Console.Error.WriteLine("Usage: dotnet StockNcnnProbe.dll [model.param model.bin input.f32 reference.f32 [iterations(1..3) [threads(1)]]]");
            Console.Error.WriteLine("       dotnet StockNcnnProbe.dll --graph-only model.param");
            return 64;
        }
        IntPtr library = IntPtr.Zero;
        using var done = new ManualResetEventSlim(false);
        using var process = Process.GetCurrentProcess();
        Thread? watchdog = null;
        try
        {
            int deadline = Env("MOBILECLIP_DEADLINE_SECONDS", 30, 1, 30);
            long limit = (long)Env("MOBILECLIP_MAX_RSS_MIB", 192, 64, 512) * 1024 * 1024;
            Stopwatch wall = Stopwatch.StartNew();
            watchdog = new Thread(() => {
                while (!done.Wait(100))
                {
                    if (wall.Elapsed.TotalSeconds >= deadline) Stop(process, "deadline_seconds=" + deadline);
                    try { if (Rss(process) > limit) Stop(process, "rss_limit_bytes=" + limit); }
                    catch (Exception e) { Stop(process, "rss_monitor_failed=" + e.GetType().Name); }
                }
            }) { IsBackground = true, Name = "stock-ncnn-watchdog" };
            watchdog.Start();
            if (Rss(process) > limit) Stop(process, "initial_rss_limit_bytes=" + limit);
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux)) SetPriority(0, 0, 15);
            Report(new { stage = "start", library = Library, deadline_seconds = deadline, rss_limit_bytes = limit, threads = 1 });
            library = NativeLibrary.Load(Library);
            var symbols = new Dictionary<string, IntPtr>();
            if (graphOnly)
            {
                string[] graphApi = { "ncnn_net_create", "ncnn_net_destroy", "ncnn_net_load_param" };
                foreach (string name in graphApi)
                    if (NativeLibrary.TryGetExport(library, name, out IntPtr address)) symbols[name] = address;
                Report(new { stage = "graph_api_probe", symbols = graphApi.ToDictionary(name => name, name => symbols.ContainsKey(name)) });
                if (symbols.Count != graphApi.Length) return 3;
                return ProbeGraph(symbols, args[1], process);
            }
            foreach (string name in Required.Concat(Optional))
                if (NativeLibrary.TryGetExport(library, name, out IntPtr p)) symbols[name] = p;
            var presence = Required.Concat(Optional).ToDictionary(name => name, name => symbols.ContainsKey(name));
            string? version = symbols.ContainsKey("ncnn_version") ? Marshal.PtrToStringUTF8(Function<Create>(symbols, "ncnn_version")()) : null;
            Report(new { stage = "api_probe", version, symbols = presence });
            bool allSupported = true;
            foreach (string op in Operators)
            {
                int? index = symbols.ContainsKey("ncnn_layer_type_to_index") ? Function<StringIndex>(symbols, "ncnn_layer_type_to_index")(op) : (int?)null;
                string support = index.HasValue && index.Value < 0 ? "unsupported" : "unknown";
                string method = index.HasValue ? "type_index" : "unavailable";
                IntPtr layer = IntPtr.Zero;
                if (symbols.ContainsKey("ncnn_layer_destroy"))
                {
                    if (symbols.ContainsKey("ncnn_layer_create_by_type"))
                    {
                        layer = Function<StringCreate>(symbols, "ncnn_layer_create_by_type")(op);
                        support = layer != IntPtr.Zero ? "supported" : "unsupported"; method = "create_by_type";
                    }
                    else if (index.HasValue && index.Value >= 0 && symbols.ContainsKey("ncnn_layer_create_by_typeindex"))
                    {
                        layer = Function<IndexCreate>(symbols, "ncnn_layer_create_by_typeindex")(index.Value);
                        support = layer != IntPtr.Zero ? "supported" : "unsupported"; method = "create_by_typeindex";
                    }
                    if (layer != IntPtr.Zero) Function<Destroy>(symbols, "ncnn_layer_destroy")(layer);
                }
                // A registry index alone cannot prove this build enables the operator.
                allSupported &= support == "supported";
                Report(new { stage = "operator_probe", name = op, index, support, method });
            }
            string[] missing = Required.Where(name => !symbols.ContainsKey(name)).ToArray();
            bool ready = missing.Length == 0 && allSupported;
            Report(new { stage = "capability_result", inference_eligible = ready, missing_apis = missing,
                operators_all_supported = allSupported, inference_requested = args.Length != 0,
                caveat = "Operator creation does not establish graph parameter compatibility; numerical validation is still required." });
            if (!ready) return 3;
            if (args.Length == 0) return 0;
            return Benchmark(symbols, args, iterations, process);
        }
        catch (Exception e) { Report(new { stage = "error", error = e.GetType().Name, message = e.Message }); return 70; }
        finally
        {
            // Keep watchdog active through native library cleanup.
            if (library != IntPtr.Zero) NativeLibrary.Free(library);
            done.Set(); watchdog?.Join(1000);
        }
    }

    private static int ProbeGraph(Dictionary<string, IntPtr> symbols, string path, Process process)
    {
        var file = new FileInfo(path);
        if (!file.Exists || file.Length == 0 || file.Length > 1024 * 1024)
            throw new InvalidDataException("Graph parameter file must exist and be between 1 byte and 1 MiB");
        IntPtr net = Function<Create>(symbols, "ncnn_net_create")();
        if (net == IntPtr.Zero) throw new InvalidOperationException("Net allocation failed");
        try
        {
            // No options access, operator introspection, weights, input or extractor APIs.
            Report(new { stage = "graph_load_start", param_bytes = file.Length, weights_loaded = false, inference_attempted = false });
            Stopwatch timer = Stopwatch.StartNew();
            int result = Function<Load>(symbols, "ncnn_net_load_param")(net, Path.GetFullPath(path));
            double elapsed = timer.Elapsed.TotalMilliseconds;
            Report(new { stage = "graph_result", load_param_return = result, graph_accepted = result == 0,
                load_param_ms = elapsed, rss_bytes = Rss(process), sampled_peak_rss_bytes = Interlocked.Read(ref PeakRss),
                weights_loaded = false, inference_attempted = false,
                caveat = "Graph acceptance does not establish weight or numerical compatibility. A nonzero return establishes graph-load failure; inspect native diagnostics for its cause." });
            return result == 0 ? 0 : 4;
        }
        finally { Function<Destroy>(symbols, "ncnn_net_destroy")(net); }
    }

    private static int Benchmark(Dictionary<string, IntPtr> s, string[] args, int iterations, Process process)
    {
        float[] input = ReadFloats(args[2], 3 * 256 * 256), reference = ReadFloats(args[3], 512);
        IntPtr net = IntPtr.Zero, mat = IntPtr.Zero;
        try
        {
            net = Function<Create>(s, "ncnn_net_create")();
            if (net == IntPtr.Zero) throw new InvalidOperationException("Net allocation failed");
            IntPtr opt = Function<Pointer>(s, "ncnn_net_get_option")(net); // Borrowed: never destroy.
            if (opt == IntPtr.Zero) throw new InvalidOperationException("Net option unavailable");
            Function<SetInt>(s, "ncnn_option_set_num_threads")(opt, 1);
            foreach (string option in new[] { "vulkan_compute", "packing_layout", "fp16_packed", "fp16_storage", "fp16_arithmetic", "bf16_storage" })
                Function<SetInt>(s, "ncnn_option_set_use_" + option)(opt, 0);
            Stopwatch timer = Stopwatch.StartNew();
            int paramResult = Function<Load>(s, "ncnn_net_load_param")(net, args[0]);
            if (paramResult != 0) throw new InvalidDataException("load_param returned " + paramResult);
            int modelResult = Function<Load>(s, "ncnn_net_load_model")(net, args[1]);
            if (modelResult != 0) throw new InvalidDataException("load_model returned " + modelResult);
            double loadMs = timer.Elapsed.TotalMilliseconds;
            Report(new { stage = "model_loaded", load_ms = loadMs, rss_bytes = Rss(process) });
            mat = Function<Mat3D>(s, "ncnn_mat_create_3d")(256, 256, 3, IntPtr.Zero);
            if (mat == IntPtr.Zero) throw new InvalidOperationException("Input allocation failed");
            for (int c = 0; c < 3; c++)
            {
                IntPtr data = Function<Channel>(s, "ncnn_mat_get_channel_data")(mat, c);
                if (data == IntPtr.Zero) throw new InvalidOperationException("Input data unavailable");
                Marshal.Copy(input, c * 65536, data, 65536);
            }
            var times = new List<double>();
            double firstMs = 0, minCosine = 1, maxError = 0;
            for (int i = 0; i <= iterations; i++)
            {
                IntPtr ex = IntPtr.Zero, output = IntPtr.Zero;
                float[] vector = new float[512];
                try
                {
                    timer.Restart();
                    ex = Function<Pointer>(s, "ncnn_extractor_create")(net);
                    if (ex == IntPtr.Zero) throw new InvalidOperationException("Extractor allocation failed");
                    int status = Function<Input>(s, "ncnn_extractor_input")(ex, "in0", mat);
                    if (status != 0) throw new InvalidDataException("extractor_input returned " + status);
                    status = Function<Extract>(s, "ncnn_extractor_extract")(ex, "out0", out output);
                    double ms = timer.Elapsed.TotalMilliseconds;
                    if (status != 0 || output == IntPtr.Zero) throw new InvalidDataException("extractor_extract returned " + status);
                    // Export is explicitly a flat 512-vector. Reject unexpected shape/layout.
                    if (Function<Integer>(s, "ncnn_mat_get_dims")(output) != 1 || Function<Integer>(s, "ncnn_mat_get_w")(output) != 512 ||
                        Function<Integer>(s, "ncnn_mat_get_elempack")(output) != 1 || Function<Size>(s, "ncnn_mat_get_elemsize")(output).ToUInt64() != 4)
                        throw new InvalidDataException("Output must be unpacked float32, dims=1, w=512");
                    IntPtr data = Function<Pointer>(s, "ncnn_mat_get_data")(output);
                    if (data == IntPtr.Zero) throw new InvalidDataException("Output data unavailable");
                    Marshal.Copy(data, vector, 0, 512);
                    if (i == 0) firstMs = ms; else times.Add(ms);
                }
                finally
                {
                    if (output != IntPtr.Zero) Function<Destroy>(s, "ncnn_mat_destroy")(output);
                    if (ex != IntPtr.Zero) Function<Destroy>(s, "ncnn_extractor_destroy")(ex);
                }
                if (vector.Any(v => Single.IsNaN(v) || Single.IsInfinity(v))) throw new InvalidDataException("Nonfinite output");
                double a = Math.Sqrt(vector.Sum(v => (double)v * v)), b = Math.Sqrt(reference.Sum(v => (double)v * v));
                if (a == 0 || b == 0) throw new InvalidDataException("Zero embedding norm");
                double cosine = 0, error = 0;
                for (int j = 0; j < 512; j++) { cosine += vector[j] / a * (reference[j] / b); error = Math.Max(error, Math.Abs(vector[j] / a - reference[j] / b)); }
                minCosine = Math.Min(minCosine, cosine); maxError = Math.Max(maxError, error);
                Report(new { stage = "inference", iteration = i, warmup = i == 0, cosine, normalized_max_abs_error = error, rss_bytes = Rss(process) });
                if (cosine <= .999) { Report(new { stage = "numeric_check_failed", cosine }); return 8; }
            }
            double[] sorted = times.OrderBy(v => v).ToArray();
            double median = sorted.Length % 2 == 1 ? sorted[sorted.Length / 2] : (sorted[sorted.Length / 2 - 1] + sorted[sorted.Length / 2]) / 2;
            Report(new { stage = "benchmark_result", numeric_check_passed = true, load_ms = loadMs, first_inference_ms = firstMs,
                median_ms = median, max_ms = sorted.Last(), times_ms = times, min_cosine = minCosine,
                max_normalized_abs_error = maxError, sampled_peak_rss_bytes = Interlocked.Read(ref PeakRss), threads = 1,
                timing_scope = "extractor creation, input binding, and extraction; excludes file reads, output copy, numeric comparison and destruction" });
            return 0;
        }
        finally
        {
            if (mat != IntPtr.Zero) Function<Destroy>(s, "ncnn_mat_destroy")(mat);
            if (net != IntPtr.Zero) Function<Destroy>(s, "ncnn_net_destroy")(net);
        }
    }
}
