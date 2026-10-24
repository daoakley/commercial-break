using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

internal static class Program
{
    [DllImport("libdisplay-capture-api.so.0", EntryPoint = "dc_request_capture_to_file_sync", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Capture(IntPtr request);

    // Keep the card hidden until the capture API actually returns. Guessing
    // the latch time sometimes captured the cover instead of the broadcast.
    private const int CaptureCompletionTimeoutMillis = 5000;
    // Let the physical panel mute settle before uncovering the video.
    // The overlay's resume acknowledgement can also precede the next scanout.
    private const int PanelDarkLeadMillis = 350;
    private const int PanelCardReturnMillis = 200;
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

    private static int LfdPanelMute()
    {
        string[] fields = Busctl("GetLfdPanelMute").Split(' ',
            StringSplitOptions.RemoveEmptyEntries);
        return fields.Length == 3 && fields[0] == "ii" && fields[2] == "0"
            && int.TryParse(fields[1], out int value) && (value == 0 || value == 1)
            ? value : -1;
    }

    private static bool SetLfdPanelMute(int value) =>
        Busctl("SetLfdPanelMute", "i", value.ToString()) == "i 0";

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

    private static Process StartPanelRescue()
    {
        // A separate process unmutes the physical panel if capture dies.
        // It only writes when this panel control still reports mute on.
        string script = "sleep 4; current=$(/usr/bin/busctl --system --timeout=2 call "
            + BacklightService + " " + BacklightObject + " " + BacklightInterface
            + " GetLfdPanelMute 2>/dev/null); "
            + "if [ \"$current\" = 'ii 1 0' ]; then /usr/bin/busctl --system --timeout=2 call "
            + BacklightService + " " + BacklightObject + " " + BacklightInterface
            + " SetLfdPanelMute i 0 >/dev/null 2>&1; fi";
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

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--serve")
        {
            Console.WriteLine("capture_ready");
            Console.Out.Flush();
            string command;
            while ((command = Console.ReadLine()) != null && command != "quit")
            {
                if (command != "clear" && command != "covered") return 2;
                int result = CaptureOnce(command == "covered");
                Console.Out.Flush();
                if (result != 0) return result;
            }
            return 0;
        }
        return args.Length == 0 ? CaptureOnce(null) : 2;
    }

    private static int CaptureOnce(bool? forceCovered)
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
            bool cardActive = (forceCovered ?? true) && !string.IsNullOrEmpty(pauseFile) && !string.IsNullOrEmpty(ackFile);
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
                    if (maskedTarget >= 0 && LfdPanelMute() == 0)
                    {
                        rescue = StartPanelRescue();
                        if (rescue != null)
                        {
                            SetLfdPanelMute(1);
                            if (LfdPanelMute() == 1)
                            {
                                masked.Start();
                                // Readback can precede the physical panel change.
                                Thread.Sleep(PanelDarkLeadMillis);
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
                    // The hide acknowledgement precedes compositor scanout.
                    Thread.Sleep(60);
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
                    // The physical panel is already masked. Wait for the real
                    // capture completion instead of guessing when it latched;
                    // showing the card after 225 ms sometimes captured our card.
                    if (!worker.Join(CaptureCompletionTimeoutMillis))
                        Environment.Exit(1);
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
                    if (masked.IsRunning)
                        Thread.Sleep(PanelCardReturnMillis);
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
                    int result = -1;
                    Exception error = null;
                    Thread worker = new Thread(() =>
                    {
                        try { result = Capture(request); }
                        catch (Exception caught) { error = caught; }
                    });
                    worker.IsBackground = true;
                    worker.Start();
                    if (!worker.Join(CaptureCompletionTimeoutMillis)) Environment.Exit(1);
                    if (error != null) return 1;
                    rc = result;
                }
                captureClock.Stop();
                captureMillis = captureClock.ElapsedMilliseconds;
            }
            finally
            {
                // Restore the panel before touching overlay files: a file error
                // must not leave the viewer looking at a black screen.
                if (rescue != null)
                {
                    int panel = LfdPanelMute();
                    if (panel == 1)
                    {
                        if (SetLfdPanelMute(0)) panel = LfdPanelMute();
                    }
                    // If the read or restore failed, leave the independent
                    // timed rescue alive. Never cancel it on an unknown state.
                    if (panel == 0 && !rescue.HasExited)
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
