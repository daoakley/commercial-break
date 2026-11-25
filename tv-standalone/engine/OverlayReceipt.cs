using System;
using System.IO;

// Window-show acknowledgement, not a claim that pixels reached the physical panel.
internal static class OverlayReceipt
{
    internal static bool Parse(string value, out long id, out long at)
    {
        id = at = 0;
        string[] fields = value.Split(' ');
        return fields.Length == 2 && long.TryParse(fields[0], out id) && id > 0 && long.TryParse(fields[1], out at) && at >= 0;
    }

    public static void Publish(string lease, ref long previous)
    {
        if (lease == null) return;
        try
        {
            if (!Parse(File.ReadAllText(lease + ".request"), out long id, out long started) || id == previous) return;
            long now = Environment.TickCount64;
            if (now < started || now - started > 8000) return;
            File.WriteAllText(lease + ".shown.tmp", id + " " + now);
            File.Move(lease + ".shown.tmp", lease + ".shown", true);
            previous = id;
        }
        catch { /* Diagnostics cannot prevent showing the window. */ }
    }

    public static long? Read(string lease, long expectedId, long started, long now)
    {
        try
        {
            if (Parse(File.ReadAllText(lease + ".shown"), out long id, out long at) && id == expectedId && at >= started && at <= now) return at;
        }
        catch { }
        return null;
    }
}
