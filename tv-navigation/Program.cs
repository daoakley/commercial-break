using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;

// Passive evdev observer. Never grabs, suppresses, forwards or injects keys.
// Stores only an opaque navigation generation, not a key history or text.
internal static class Program
{
    const string State = "/run/codex-commercial-muter";
    [DllImport("libc.so.6", SetLastError = true)] static extern int open(string path, int flags);
    [DllImport("libc.so.6", SetLastError = true)] static extern int read(int fd, byte[] data, int count);
    [DllImport("libc.so.6")] static extern int close(int fd);

    static bool IsNavigation(ushort code) =>
        code == 28 || code == 103 || code == 105 || code == 106 || code == 108 ||
        code == 102 || code == 139 || code == 158 || code == 172 || code == 174 ||
        code == 352 || code == 353 || code == 358 || code == 362 || code == 365 ||
        code == 402 || code == 403 || code == 405;

    static IEnumerable<string> Devices(string description)
    {
        foreach (string block in description.Split(new[] { "\n\n" }, StringSplitOptions.RemoveEmptyEntries))
        {
            string name = Regex.Match(block, "N: Name=\"([^\"]+)\"").Groups[1].Value;
            if (name != "Smart Control" && name != "Smart Control 2016" &&
                name != "Smart Control 2016 Keyboard" && name != "wt61p807 rc device" &&
                name != "Remote-Input(Keyboard)" && name != "voice_app_keyboard") continue;
            var match = Regex.Match(block, @"H: Handlers=.*\b(event[0-9]+)\b");
            if (match.Success) yield return "/dev/input/" + match.Groups[1].Value;
        }
    }

    static void ReleaseOwnedControls()
    {
        // Fixed script, no key text or user-provided values interpolated.
        var start = new ProcessStartInfo("/bin/sh") { UseShellExecute = false };
        start.ArgumentList.Add("-c");
        start.ArgumentList.Add("STATE_DIR=/run/codex-commercial-muter; " +
            "rm -f \"$STATE_DIR/overlay-lease\"; " +
            "if [ -f \"$STATE_DIR/owned-mute\" ]; then " +
            "/usr/bin/busctl --system --timeout=2 call org.tizen.speakermanager " +
            "/Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b false >/dev/null; " +
            "rm -f \"$STATE_DIR/owned-mute\"; fi; " +
            ". /home/owner/share/tmp/sdk_tools/tv-backlight.sh; release_owned_backlight");
        using (var process = Process.Start(start))
            if (process != null && !process.WaitForExit(10000)) process.Kill();
    }

    static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test")
        {
            if (!IsNavigation(402) || !IsNavigation(28) || IsNavigation(113) ||
                IsNavigation(114) || IsNavigation(115) || IsNavigation(30)) return 1;
            var names = new List<string>(Devices("N: Name=\"Smart Control 2016\"\nH: Handlers=kbd event4 \n\nN: Name=\"Other Keyboard\"\nH: Handlers=kbd event5\n"));
            return names.Count == 1 && names[0] == "/dev/input/event4" ? 0 : 1;
        }
        var descriptors = new List<int>();
        try
        {
            foreach (string path in Devices(File.ReadAllText("/proc/bus/input/devices")))
            {
                int fd = open(path, 2048); // O_RDONLY | O_NONBLOCK
                if (fd >= 0) descriptors.Add(fd);
            }
            Console.WriteLine("navigation_observer_devices=" + descriptors.Count);
            if (descriptors.Count == 0) return 1;
            int eventSize = IntPtr.Size == 8 ? 24 : 16;
            int offset = IntPtr.Size == 8 ? 16 : 8;
            byte[] buffer = new byte[eventSize * 32];
            long last = 0;
            while (!File.Exists(State + "/stop") && File.Exists(State + "/heartbeat") &&
                   DateTime.UtcNow - File.GetLastWriteTimeUtc(State + "/heartbeat") < TimeSpan.FromSeconds(50))
            {
                bool navigation = false;
                foreach (int fd in descriptors)
                {
                    int count;
                    // Bound work per node so one noisy device cannot starve safety.
                    for (int batch = 0; batch < 4 && (count = read(fd, buffer, buffer.Length)) > 0; batch++)
                        for (int at = 0; at + eventSize <= count; at += eventSize)
                            if (BitConverter.ToUInt16(buffer, at + offset) == 1 &&
                                BitConverter.ToInt32(buffer, at + offset + 4) == 1 &&
                                IsNavigation(BitConverter.ToUInt16(buffer, at + offset + 2))) navigation = true;
                }
                long now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                if (navigation && now - last > 100)
                {
                    last = now;
                    File.WriteAllText(State + "/navigation.tmp", now.ToString());
                    File.Move(State + "/navigation.tmp", State + "/navigation", true);
                    File.Delete(State + "/overlay-lease");
                    ReleaseOwnedControls();
                    Console.WriteLine("navigation_reset");
                }
                Thread.Sleep(25);
            }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error.GetType().Name); return 1; }
        finally { foreach (int fd in descriptors) close(fd); }
    }
}
