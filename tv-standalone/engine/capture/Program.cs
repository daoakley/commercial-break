using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Threading;

// Drop-in replacement for DisplayCaptureProbe that reads the video through
// Samsung's content-recognition capture path (secvideo_api_capture_screen).
// This path reads the composed picture on this Frame. The existing panel/card
// handshake remains necessary. An optional native fingerprint sample is taken
// during the same uncovered interval, at most at the backend's requested cadence.
// Output: 480x270 RGB PNG at the same path and with the same "rc=0 width=..."
// line the TV helper already parses. Requires the process-local allowlist
// library (LD_PRELOAD=/run/libtzcapturec-probe.so), exactly like the display probe.
internal static class Program
{
    [DllImport("libvideo-capture.so.0", EntryPoint = "secvideo_api_capture_screen", CallingConvention = CallingConvention.Cdecl)]
    private static extern int CaptureScreen(int width, int height, IntPtr parameter);

    private const int SourceWidth = 720, SourceHeight = 576;   // snapped by the API
    private const int OutWidth = 480, OutHeight = 270;
    private const int PlaneBytes = 2 * 1024 * 1024;

    // Covered-capture handshake (card on screen). Measured on this Frame on
    // 25 Oct 2026: the physical panel follows SetLfdPanelMute within <50 ms;
    // 0/0 ms margins let the picture show once in two trials, 50/30 and above
    // never did. Defaults are twice the last clean values.
    private static readonly int PanelDarkLeadMillis = EnvInt("ACR_PANEL_LEAD_MS", 100, 0, 1000);
    private static readonly int PanelCardReturnMillis = EnvInt("ACR_PANEL_RETURN_MS", 60, 0, 1000);
    private const string BacklightService = "org.tizen.tv.avoc";
    private const string BacklightObject = "/org/tizen/tv/avoc";
    private const string BacklightInterface = "org.tizen.tv.avoc.AvOutputControl";

    private static int EnvInt(string name, int fallback, int min, int max)
    {
        return int.TryParse(Environment.GetEnvironmentVariable(name), out int v) && v >= min && v <= max ? v : fallback;
    }

    private static string Busctl(params string[] arguments)
    {
        var start = new ProcessStartInfo("/usr/bin/busctl") { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (string common in new[] { "--system", "--timeout=2", "call", BacklightService, BacklightObject, BacklightInterface })
            start.ArgumentList.Add(common);
        foreach (string argument in arguments) start.ArgumentList.Add(argument);
        using (Process process = Process.Start(start))
        {
            if (process == null) return "";
            if (!process.WaitForExit(2500)) { process.Kill(); return ""; }
            return process.ExitCode == 0 ? process.StandardOutput.ReadToEnd().Trim() : "";
        }
    }

    private static int LfdPanelMute()
    {
        string[] fields = Busctl("GetLfdPanelMute").Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return fields.Length == 3 && fields[0] == "ii" && fields[2] == "0" && int.TryParse(fields[1], out int value) && (value == 0 || value == 1) ? value : -1;
    }

    private static bool SetLfdPanelMute(int value) => Busctl("SetLfdPanelMute", "i", value.ToString()) == "i 0";

    // This isolated app never changes brightness. Only its own current cover
    // permits a brief physical-panel mask during the capture handshake.
    private static bool PanelMaskWanted() => File.Exists("/run/commercial-block/overlay-lease");

    private static Process StartPanelRescue()
    {
        // Independent process: un-mutes the physical panel if this one dies mid-handshake.
        string script = "sleep 4; current=$(/usr/bin/busctl --system --timeout=2 call " + BacklightService + " " + BacklightObject + " " + BacklightInterface
            + " GetLfdPanelMute 2>/dev/null); if [ \"$current\" = 'ii 1 0' ]; then /usr/bin/busctl --system --timeout=2 call "
            + BacklightService + " " + BacklightObject + " " + BacklightInterface + " SetLfdPanelMute i 0 >/dev/null 2>&1; fi";
        var start = new ProcessStartInfo("/bin/sh") { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add("-c"); start.ArgumentList.Add(script);
        return Process.Start(start);
    }

    private static bool KeepCardWindowActive()
    {
        // An expired or malformed test window always returns to the verified
        // panel-mask path, even if the diagnostic controller disappears.
        try {
            return long.TryParse(File.ReadAllText("/run/commercial-block/native-fingerprint-underlay-until"), out long until)
                && DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() < until;
        } catch { return false; }
    }

    private static readonly uint[] CrcTable = BuildCrcTable();

    private static uint[] BuildCrcTable()
    {
        var table = new uint[256];
        for (uint n = 0; n < 256; n++)
        {
            uint c = n;
            for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            table[n] = c;
        }
        return table;
    }

    private static uint Crc(byte[] data, int offset, int count)
    {
        uint c = 0xFFFFFFFFu;
        for (int i = offset; i < offset + count; i++) c = CrcTable[(c ^ data[i]) & 0xFF] ^ (c >> 8);
        return c ^ 0xFFFFFFFFu;
    }

    private static void WriteChunk(Stream stream, string type, byte[] body)
    {
        byte[] length = { (byte)(body.Length >> 24), (byte)(body.Length >> 16), (byte)(body.Length >> 8), (byte)body.Length };
        byte[] typed = new byte[4 + body.Length];
        for (int i = 0; i < 4; i++) typed[i] = (byte)type[i];
        Buffer.BlockCopy(body, 0, typed, 4, body.Length);
        uint crc = Crc(typed, 0, typed.Length);
        stream.Write(length, 0, 4);
        stream.Write(typed, 0, typed.Length);
        stream.Write(new[] { (byte)(crc >> 24), (byte)(crc >> 16), (byte)(crc >> 8), (byte)crc }, 0, 4);
    }

    private static byte[] Zlib(byte[] raw)
    {
        using (var output = new MemoryStream())
        {
            output.WriteByte(0x78); output.WriteByte(0x9C);
            using (var deflate = new DeflateStream(output, CompressionLevel.Fastest, true))
                deflate.Write(raw, 0, raw.Length);
            uint a = 1, b = 0;
            foreach (byte value in raw) { a = (a + value) % 65521; b = (b + a) % 65521; }
            uint adler = (b << 16) | a;
            output.Write(new[] { (byte)(adler >> 24), (byte)(adler >> 16), (byte)(adler >> 8), (byte)adler }, 0, 4);
            return output.ToArray();
        }
    }

    private static byte Clamp(double v) => v < 0 ? (byte)0 : v > 255 ? (byte)255 : (byte)v;

    private static int Main(string[] args)
    {
        if(args.Length==2&&args[0]=="--layout-worker"&&int.TryParse(args[1],out int parentPid)&&parentPid>1)return LayoutDetector.Worker(parentPid);
        string basename = Environment.GetEnvironmentVariable("CAPTURE_FILE_BASENAME") ?? "commercial-block-frame";
        if (basename.Length == 0 || basename.IndexOfAny(new[] { '/', '\\' }) >= 0) return 2;
        string path = "/opt/usr/home/owner/commercial-block/" + basename + ".png";
        string debugId=Environment.GetEnvironmentVariable("CAPTURE_DEBUG_ID");
        bool debugImage=debugId!=null&&debugId.Length==32&&System.Linq.Enumerable.All(debugId,ch=>"0123456789abcdef".IndexOf(ch)>=0);
        if(debugImage)path="/run/commercial-block/debug-"+debugId+".png";
        IntPtr parameter = Marshal.AllocHGlobal(256);
        IntPtr y = Marshal.AllocHGlobal(PlaneBytes);
        IntPtr c = Marshal.AllocHGlobal(PlaneBytes);
        try
        {
            for (int i = 0; i < 256; i += 4) Marshal.WriteInt32(parameter, i, 0);
            Marshal.WriteInt32(parameter, 0x00, PlaneBytes);
            Marshal.WriteInt32(parameter, 0x04, PlaneBytes);
            Marshal.WriteIntPtr(parameter, 0x10, y);
            Marshal.WriteIntPtr(parameter, 0x14, c);
            string pauseFile = Environment.GetEnvironmentVariable("CAPTURE_OVERLAY_PAUSE_FILE");
            string ackFile = Environment.GetEnvironmentVariable("CAPTURE_OVERLAY_ACK_FILE");
            // Opt-in, TV-local experiment: secure fingerprints may read the video
            // independently of the composed screenshot. Do not hide the card
            // when this mode has been explicitly selected and only fingerprints
            // are requested. Image exports still use the established handshake.
            bool keepCard = Environment.GetEnvironmentVariable("CAPTURE_FINGERPRINT_ONLY") == "1"
                && (Environment.GetEnvironmentVariable("CAPTURE_KEEP_CARD") == "1" || KeepCardWindowActive());
            bool cardActive = !keepCard && !string.IsNullOrEmpty(pauseFile) && !string.IsNullOrEmpty(ackFile);
            var clock = Stopwatch.StartNew();
            var uncovered = new Stopwatch();
            var masked = new Stopwatch();
            Process rescue = null;
            int rc;
            long captureMillis;
            long imageAt = 0;
            bool pillHit = false;
            byte[] layoutRgb = null;
            bool layoutQueued=false;
            try
            {
                if (cardActive)
                {
                    // 1. Blank the physical panel (only while this app owns the cover), wait for it to go dark.
                    if (PanelMaskWanted() && LfdPanelMute() == 0)
                    {
                        rescue = StartPanelRescue();
                        if (rescue != null && SetLfdPanelMute(1) && LfdPanelMute() == 1)
                        {
                            masked.Start();
                            Thread.Sleep(PanelDarkLeadMillis);
                        }
                    }
                    // 2. Hide the card; the overlay acknowledges when it is gone.
                    File.Delete(ackFile);
                    uncovered.Start();
                    File.WriteAllText(pauseFile, "pause");
                    for (int i = 0; !File.Exists(ackFile) && i < 100; i++) Thread.Sleep(10);
                    if (!File.Exists(ackFile))
                    {
                        Console.Error.WriteLine("overlay_pause_timeout");
                        Console.WriteLine("rc=-101 width=0 height=0 backend=acr");
                        return 1;
                    }
                }
                // 3. Capture: the frame is latched inside this call (~150 ms).
                var captureClock = Stopwatch.StartNew();
                imageAt = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                rc = CaptureScreen(SourceWidth, SourceHeight, parameter);
                captureMillis = captureClock.ElapsedMilliseconds;
                if (rc == 0 && !keepCard && Environment.GetEnvironmentVariable("CAPTURE_CHECK_SPONSORED") == "1")
                {
                    // Inspect only 924 reference pixels directly from the existing NV12 planes.
                    // This path needs neither a full RGB frame nor a PNG, and works with debug off.
                    try
                    {
                        int w = Marshal.ReadInt32(parameter, 0x08), h = Marshal.ReadInt32(parameter, 0x0c), stride = Marshal.ReadInt32(parameter, 0x2c);
                        if ((long)stride * h > PlaneBytes) throw new ArgumentException("capture plane bounds");
                        var pillClock = Stopwatch.StartNew();
                        double score = SponsoredPill.ScoreNv12(y, c, w, h, stride);
                        double elapsedMs = pillClock.Elapsed.TotalMilliseconds;
                        bool hit = score >= SponsoredPill.Threshold;
                        string resultPath = "/run/commercial-block/sponsored-pill.json";
                        File.WriteAllText(resultPath + ".tmp", System.Text.Json.JsonSerializer.Serialize(new {
                            at = imageAt, score, hit, keepCard, elapsedMs, width = w, height = h,
                            threshold = SponsoredPill.Threshold, detector = "youtube-tv-sponsored-v1"
                        }));
                        File.Move(resultPath + ".tmp", resultPath, true);
                        pillHit = hit;
                    }
                    catch { /* Optional local check failure preserves the existing Samsung path. */ }
                }
                if (rc == 0 && !pillHit) SecureFingerprint.TryCaptureDue(imageAt);
            }
            finally
            {
                if (cardActive)
                {
                    // 4. Card back, wait for its acknowledgement, then the return margin, then panel on.
                    File.Delete(pauseFile);
                    for (int i = 0; File.Exists(ackFile) && i < 100; i++) Thread.Sleep(10);
                    uncovered.Stop();
                    if (masked.IsRunning) Thread.Sleep(PanelCardReturnMillis);
                }
                if (rescue != null)
                {
                    int panel = LfdPanelMute();
                    if (panel == 1 && SetLfdPanelMute(0)) panel = LfdPanelMute();
                    if (masked.IsRunning) masked.Stop();
                    // Unknown or still-muted state: leave the timed rescue alive.
                    if (panel == 0 && !rescue.HasExited) { try { rescue.Kill(); } catch (InvalidOperationException) { } }
                    rescue.Dispose();
                }
            }
            int width = Marshal.ReadInt32(parameter, 0x08), height = Marshal.ReadInt32(parameter, 0x0c), pitch = Marshal.ReadInt32(parameter, 0x2c);
            if (rc != 0)
            {
                Console.WriteLine($"rc={rc} width=0 height=0 backend=acr capture_ms={captureMillis} uncovered_ms={uncovered.ElapsedMilliseconds} panel_mask_ms={masked.ElapsedMilliseconds}");
                return 1;
            }
            if (width <= 0 || height <= 0 || pitch < width || width > 4096 || height > 2304)
            {
                Console.WriteLine($"rc=-100 width={width} height={height} pitch={pitch} backend=acr");
                return 1;
            }
            // Feed the separately warmed, isolated worker AFTER panel restoration.
            // Atomic latest-frame handoff; no image history is kept by this path.
            if (!keepCard && !pillHit && Environment.GetEnvironmentVariable("CAPTURE_CHECK_LAYOUT") == "1")
            {
                try {
                    layoutRgb = LayoutDetector.RgbNv12(y,c,width,height,pitch,PlaneBytes);
                    string pending="/run/commercial-block/layout-frame.bin";
                    using(var file=new FileStream(pending+".tmp",FileMode.Create,FileAccess.Write)){
                        byte[] at=BitConverter.GetBytes(imageAt);file.Write(at,0,at.Length);file.Write(layoutRgb,0,layoutRgb.Length);
                    }
                    File.Move(pending+".tmp",pending,true);layoutQueued=true;
                }catch(Exception){ /* existing fingerprint/Sponsored result remains valid */ }
            }
            if (Environment.GetEnvironmentVariable("CAPTURE_FINGERPRINT_ONLY") == "1")
            {
                File.WriteAllText("/run/commercial-block/capture-diagnostics.json",
                    System.Text.Json.JsonSerializer.Serialize(new {
                        at = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), keepCard,
                        cardHidden = cardActive, captureMillis,
                        panelMaskMillis = masked.ElapsedMilliseconds,
                        totalMillis = clock.ElapsedMilliseconds
                    }));
                if(!debugImage)return pillHit || layoutQueued || File.Exists("/run/commercial-block/acr-fingerprint") ? 0 : 1;
            }
            try {
            // NV12 (BT.601) -> RGB, nearest-neighbour resample to 480x270.
            byte[] raw = new byte[(OutWidth * 3 + 1) * OutHeight];
            byte[] rgb = layoutRgb ?? LayoutDetector.RgbNv12(y,c,width,height,pitch,PlaneBytes);
            for(int row=0;row<OutHeight;row++)
                Buffer.BlockCopy(rgb,row*OutWidth*3,raw,row*(OutWidth*3+1)+1,OutWidth*3);
            byte[] ihdr = { 0, 0, (byte)(OutWidth >> 8), unchecked((byte)OutWidth), 0, 0, (byte)(OutHeight >> 8), unchecked((byte)OutHeight), 8, 2, 0, 0, 0 };
            string temp = path + ".tmp";
            using (var file = new FileStream(temp, FileMode.Create, FileAccess.Write))
            {
                file.Write(new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A }, 0, 8);
                WriteChunk(file, "IHDR", ihdr);
                WriteChunk(file, "IDAT", Zlib(raw));
                WriteChunk(file, "IEND", new byte[0]);
            }
            File.Move(temp, path, true);
            Console.WriteLine($"rc=0 width={OutWidth} height={OutHeight} path={path} uncovered_ms={uncovered.ElapsedMilliseconds} capture_ms={captureMillis} total_ms={clock.ElapsedMilliseconds} panel_mask_ms={masked.ElapsedMilliseconds} backend=acr source={width}x{height}");
            return 0;
            } catch(Exception) when(debugImage) {
                // Debug disk/encoding failures never invalidate recognition.
                try{File.Delete(path);File.Delete(path+".tmp");}catch{}
                Console.Error.WriteLine("debug_image_unavailable");
                return pillHit || layoutQueued || File.Exists("/run/commercial-block/acr-fingerprint")?0:1;
            }
        }
        finally
        {
            Marshal.FreeHGlobal(c);
            Marshal.FreeHGlobal(y);
            Marshal.FreeHGlobal(parameter);
        }
    }
}
