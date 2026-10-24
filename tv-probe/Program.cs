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
    private const string OwnedBacklight = "/run/codex-commercial-muter/owned-backlight";
    private const string PanelMaskEnabled = "/run/codex-commercial-muter/panel-mask-enabled";
    private const string BacklightService = "org.tizen.tv.avoc";
    private const string BacklightObject = "/org/tizen/tv/avoc";
    private const string BacklightInterface = "org.tizen.tv.avoc.AvOutputControl";

    private static string Busctl(params string[] arguments)
    {
        var start = new ProcessStartInfo("/usr/bin/busctl")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (string common in new[] { "--system", "--timeout=2", "call", BacklightService,
                                           BacklightObject, BacklightInterface })
            start.ArgumentList.Add(common);
        foreach (string argument in arguments)
            start.ArgumentList.Add(argument);
        using (Process process = Process.Start(start))
        {
            if (process == null) return "";
            if (!process.WaitForExit(2500))
            {
                process.Kill();
                return "";
            }
            return process.ExitCode == 0 ? process.StandardOutput.ReadToEnd().Trim() : "";
        }
    }

    private static int ActiveBacklight()
    {
        string[] fields = Busctl("GetBacklight", "i", "0").Split(' ',
            StringSplitOptions.RemoveEmptyEntries);
        return fields.Length == 3 && fields[0] == "ii" && fields[2] == "0"
            && int.TryParse(fields[1], out int value) ? value : -1;
    }

    private static bool SetActiveBacklight(int value) =>
        Busctl("SetBacklight", "ii", value.ToString(), "0") == "i 0";

    private static int OwnedTargetBacklight()
    {
        string enabled = Environment.GetEnvironmentVariable("CAPTURE_PANEL_MASK_ENABLED_FILE")
            ?? PanelMaskEnabled;
        string owned = Environment.GetEnvironmentVariable("CAPTURE_PANEL_MASK_STATE_FILE")
            ?? OwnedBacklight;
        if (!File.Exists(enabled) || !File.Exists(owned)) return -1;
        string[] fields = File.ReadAllText(owned).Split(
            (char[])null, StringSplitOptions.RemoveEmptyEntries);
        if (fields.Length != 3 || !int.TryParse(fields[1], out int target)
            || target < 1 || target > 50 || ActiveBacklight() != target) return -1;
        return target;
    }

    private static Process StartPanelRescue(int target)
    {
        // A separate process restores the panel if this capture process dies.
        // It only writes when the active value is still zero.
        string script = "sleep 2; current=$(/usr/bin/busctl --system --timeout=2 call "
            + BacklightService + " " + BacklightObject + " " + BacklightInterface
            + " GetBacklight i 0 2>/dev/null); "
            + "if [ \"$current\" = 'ii 0 0' ]; then /usr/bin/busctl --system --timeout=2 call "
            + BacklightService + " " + BacklightObject + " " + BacklightInterface
            + " SetBacklight ii " + target + " 0 >/dev/null 2>&1; fi";
        var start = new ProcessStartInfo("/bin/sh")
        {
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        start.ArgumentList.Add("-c");
        start.ArgumentList.Add(script);
        return Process.Start(start);
    }

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
            Stopwatch masked = new Stopwatch();
            long captureMillis = 0;
            int rc;
            int maskedTarget = -1;
            Process rescue = null;
            try
            {
                if (cardActive)
                {
                    maskedTarget = OwnedTargetBacklight();
                    if (maskedTarget >= 0)
                    {
                        rescue = StartPanelRescue(maskedTarget);
                        if (rescue != null)
                        {
                            SetActiveBacklight(0);
                            if (ActiveBacklight() == 0)
                            {
                                masked.Start();
                                // Let the panel change take effect before uncovering video.
                                Thread.Sleep(50);
                            }
                            else maskedTarget = -1;
                        }
                        else maskedTarget = -1;
                    }
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
                // Restore the panel before touching overlay files: a file error
                // must not leave the viewer looking at a dark screen.
                if (rescue != null)
                {
                    int active = ActiveBacklight();
                    if (active == 0)
                    {
                        if (SetActiveBacklight(maskedTarget)) active = ActiveBacklight();
                    }
                    // If the read or restore failed, leave the independent
                    // timed rescue alive. Never cancel it on an unknown state.
                    if (active > 0 && !rescue.HasExited)
                        try { rescue.Kill(); } catch (InvalidOperationException) { }
                }
                if (masked.IsRunning) masked.Stop();
                if (cardActive)
                {
                    File.Delete(pauseFile);
                    if (uncovered.IsRunning) uncovered.Stop();
                }
                if (rescue != null) rescue.Dispose();
            }
            string path = Marshal.PtrToStringAnsi(IntPtr.Add(request, 0x28)) ?? "";
            Console.WriteLine($"rc={rc} width={Marshal.ReadInt32(request, 0x20)} height={Marshal.ReadInt32(request, 0x24)} path={path} uncovered_ms={uncovered.ElapsedMilliseconds} capture_ms={captureMillis} panel_mask_ms={masked.ElapsedMilliseconds}");
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
