using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

internal static class Program
{
    [DllImport("libdisplay-capture-api.so.0", EntryPoint = "dc_request_capture_to_file_sync", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Capture(IntPtr request);

    // The display service latches the frame before its synchronous PNG write
    // finishes. Keep the card hidden through that latch, then restore it while
    // encoding continues. A shorter 100 ms test captured the card; 200 ms
    // captured video on this Frame, so leave a small margin.
    private const int CaptureLatchMillis = 225;
    private const int CaptureCompletionTimeoutMillis = 5000;

    private static int Main()
    {
        string basename = Environment.GetEnvironmentVariable("CAPTURE_FILE_BASENAME") ?? "codex-display-sample.png";
        if (basename.Length == 0 || basename.IndexOfAny(new[] { '/', '\\' }) >= 0)
            return 2;
        IntPtr request = Marshal.AllocHGlobal(296);
        IntPtr directory = Marshal.StringToHGlobalAnsi("/home/owner/share/tmp/sdk_tools");
        IntPtr filename = Marshal.StringToHGlobalAnsi(basename);
        try
        {
            for (int i = 0; i < 296; i++) Marshal.WriteByte(request, i, 0);
            Marshal.WriteInt32(request, 0x00, 4); // app type
            Marshal.WriteInt32(request, 0x04, 0); // mode
            Marshal.WriteInt32(request, 0x08, 0); // PNG
            Marshal.WriteInt32(request, 0x0c, 90);
            Marshal.WriteIntPtr(request, 0x10, directory);
            Marshal.WriteIntPtr(request, 0x14, filename);
            Marshal.WriteInt32(request, 0x18, 480);
            Marshal.WriteInt32(request, 0x1c, 270);
            string pauseFile = Environment.GetEnvironmentVariable("CAPTURE_OVERLAY_PAUSE_FILE");
            string ackFile = Environment.GetEnvironmentVariable("CAPTURE_OVERLAY_ACK_FILE");
            bool cardActive = !string.IsNullOrEmpty(pauseFile) && !string.IsNullOrEmpty(ackFile);
            Stopwatch uncovered = new Stopwatch();
            Stopwatch captureClock = new Stopwatch();
            long captureMillis = 0;
            int rc;
            try
            {
                if (cardActive)
                {
                    File.Delete(ackFile);
                    uncovered.Start();
                    File.WriteAllText(pauseFile, "pause");
                    for (int i = 0; !File.Exists(ackFile) && i < 100; i++)
                        Thread.Sleep(10);
                    if (!File.Exists(ackFile))
                    {
                        Console.Error.WriteLine("overlay_pause_timeout");
                        return 1;
                    }
                    int workerResult = -1;
                    Exception workerError = null;
                    Thread worker = new Thread(() =>
                    {
                        try { workerResult = Capture(request); }
                        catch (Exception error) { workerError = error; }
                    });
                    worker.IsBackground = true;
                    captureClock.Start();
                    worker.Start();
                    Thread.Sleep(CaptureLatchMillis);
                    File.Delete(pauseFile);
                    for (int i = 0; File.Exists(ackFile) && i < 100; i++)
                        Thread.Sleep(10);
                    uncovered.Stop();
                    if (File.Exists(ackFile))
                    {
                        Console.Error.WriteLine("overlay_resume_timeout");
                        if (!worker.Join(CaptureCompletionTimeoutMillis))
                            Environment.Exit(1);
                        return 1;
                    }
                    if (!worker.Join(CaptureCompletionTimeoutMillis))
                    {
                        Console.Error.WriteLine("capture_timeout");
                        Environment.Exit(1); // Do not free a request still used by native code.
                    }
                    if (workerError != null)
                    {
                        Console.Error.WriteLine("capture_error: " + workerError.GetType().Name);
                        return 1;
                    }
                    rc = workerResult;
                }
                else
                {
                    captureClock.Start();
                    rc = Capture(request);
                }
                captureClock.Stop();
                captureMillis = captureClock.ElapsedMilliseconds;
            }
            finally
            {
                if (cardActive)
                {
                    File.Delete(pauseFile);
                    if (uncovered.IsRunning) uncovered.Stop();
                }
            }
            string path = Marshal.PtrToStringAnsi(IntPtr.Add(request, 0x28)) ?? "";
            Console.WriteLine($"rc={rc} width={Marshal.ReadInt32(request, 0x20)} height={Marshal.ReadInt32(request, 0x24)} path={path} uncovered_ms={uncovered.ElapsedMilliseconds} capture_ms={captureMillis}");
            return rc == 0 ? 0 : 1;
        }
        finally
        {
            Marshal.FreeHGlobal(filename);
            Marshal.FreeHGlobal(directory);
            Marshal.FreeHGlobal(request);
        }
    }
}
