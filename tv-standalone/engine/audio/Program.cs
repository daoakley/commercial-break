// AudioSpliceObserver: TV-resident shadow observer for the splice signature.
//
// Reads 48 kHz stereo S16_LE PCM from arecord (or a raw file for parity tests), computes per 10 ms
// frame the total energy and the mid/side energies exactly as the Mac reference (splice_replay.py),
// and applies the frozen rule:
//   run of frames <= -50 dBFS, length 60..1500 ms, floor <= -75 dBFS, and the mid/side ratio of the
//   first 1.0 s after the run < 40 dB (not exact mono)  ->  trigger, decided at run end + 1.0 s.
// It logs every deep dip (>= 60 ms, floor <= -60 dBFS) as a candidate so the rule can be re-tuned
// from the log, flags an all-zero stream ("tap silent") and reports its own CPU and memory.
// It controls nothing: no mute, no cover, no settings. Exit codes: 0 ok, 2 input failure, 3 usage.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;

static class Program
{
    const int Rate = 48000, Frame = 480, FrameBytes = Frame * 4, Ring = 1600;      // 16 s of frames
    const int PreFrames = 320, GapFrames = 20, PostFrames = 100, MinRunFrames = 4;  // reference context
    const double RunThresholdDb = -50.0, CandidateFloorDb = -60.0, MonoDb = 40.0;
    static double FloorDb = -75.0;                                                   // --floor; the research value is -75
    const int MinTriggerMs = 60, MaxTriggerMs = 1500, SilentFrames = 500;            // 5 s of zeros

    static readonly double[] ETot = new double[Ring], EMid = new double[Ring], ESide = new double[Ring];
    static StreamWriter Log;
    static string ResultPath, StatePath, LogPath;
    static long LogRows;
    static volatile bool Stop;
    static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    sealed class Pending { public long Start, End; public double Floor; }

    static double Db(double v) => 10.0 * Math.Log10(Math.Max(v, 1e-12));
    static long NowMs() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    static string F(double v) => double.IsNaN(v) ? "null" : v.ToString("0.###", Inv);

    static StreamWriter OpenLog(string path) =>
        new StreamWriter(new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.Read), new UTF8Encoding(false)) { AutoFlush = true };

    static void Write(string json)
    {
        Log.WriteLine(json);
        if (LogPath != null && ++LogRows % 200 == 0) Rotate();
    }

    // Keep the on-TV log bounded: roll once past 1 MB, keeping one previous file.
    static void Rotate()
    {
        try
        {
            var info = new FileInfo(LogPath);
            if (!info.Exists || info.Length <= 1_000_000) return;
            Log.Flush(); Log.Dispose();
            File.Move(LogPath, LogPath + ".1", true);
            Log = OpenLog(LogPath);
        }
        catch { }
    }

    // Small liveness/silence summary for the engine, replaced atomically.
    static void WriteState(long now, bool silent, long frames, double cpuMs, string lagMs)
    {
        if (StatePath == null) return;
        try
        {
            File.WriteAllText(StatePath + ".tmp", "{\"at\":" + now + ",\"silent\":" + (silent ? "true" : "false") + ",\"frames\":" + frames + ",\"streamS\":" + F(frames * 0.01) +
                                                 ",\"cpuMs\":" + F(cpuMs) + ",\"rssKb\":" + Rss() + ",\"lagMs\":" + lagMs + ",\"pid\":" + Process.GetCurrentProcess().Id + "}");
            File.Move(StatePath + ".tmp", StatePath, true);
        }
        catch { }
    }

    static long Rss()
    {
        try
        {
            foreach (var line in File.ReadAllLines("/proc/self/status"))
                if (line.StartsWith("VmRSS:", StringComparison.Ordinal))
                    return long.Parse(line.Substring(6).Trim().Split(' ')[0], Inv);
        }
        catch { }
        return Environment.WorkingSet / 1024;
    }

    static int Main(string[] args)
    {
        string device = "hw:0,5", input = null, logPath = null, statsEvery = "10";
        long seconds = 0, t0Override = -1;
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i], v = i + 1 < args.Length ? args[i + 1] : null;
            switch (a)
            {
                case "--device": device = v; i++; break;
                case "--input": input = v; i++; break;
                case "--log": logPath = v; i++; break;
                case "--result": ResultPath = v; i++; break;
                case "--state": StatePath = v; i++; break;
                case "--floor": FloorDb = double.Parse(v, Inv); i++; break;
                case "--seconds": seconds = long.Parse(v, Inv); i++; break;
                case "--t0": t0Override = long.Parse(v, Inv); i++; break;
                case "--stats-every": statsEvery = v; i++; break;
                default: Console.Error.WriteLine("usage: --device hw:0,5 | --input raw.s16le  [--log file.jsonl] [--result latest.json] [--state state.json] [--floor dBFS] [--seconds N] [--t0 unixms] [--stats-every S]"); return 3;
            }
        }
        int statsSec = int.Parse(statsEvery, Inv);
        LogPath = logPath;
        Log = logPath == null ? new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true } : OpenLog(logPath);
        Console.CancelKeyPress += (s, e) => { e.Cancel = true; Stop = true; };
        AppDomain.CurrentDomain.ProcessExit += (s, e) => { Stop = true; };

        Process arecord = null;
        Stream stream;
        long startedWall = NowMs();
        if (input != null)
        {
            stream = new FileStream(input, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16);
        }
        else
        {
            try
            {
                arecord = Process.Start(new ProcessStartInfo("/usr/bin/arecord", "-D " + device + " -f S16_LE -r 48000 -c 2 -t raw")
                { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true });
                arecord.BeginErrorReadLine();
                arecord.ErrorDataReceived += (s, e) => { if (e.Data != null) Write("{\"type\":\"arecord\",\"at\":" + NowMs() + ",\"text\":\"" + e.Data.Replace("\"", "'") + "\"}"); };
            }
            catch (Exception ex)
            {
                Write("{\"type\":\"error\",\"at\":" + NowMs() + ",\"text\":\"arecord start failed: " + ex.GetType().Name + "\"}");
                return 2;
            }
            stream = arecord.StandardOutput.BaseStream;
        }
        Write("{\"type\":\"start\",\"at\":" + startedWall + ",\"source\":\"" + (input ?? device) + "\",\"rule\":\"deep75_60-1500ms_post_not_mono\",\"floorDb\":" + F(FloorDb) + ",\"pid\":" + Process.GetCurrentProcess().Id + "}");
        WriteState(startedWall, false, 0, 0, "null");

        var buf = new byte[FrameBytes];
        long frames = 0, t0 = -1, runStart = -1, zeroRun = 0, candidates = 0, triggers = 0, lastStats = NowMs();
        double runFloor = 0;
        bool silent = false;
        var pending = new List<Pending>();
        var proc = Process.GetCurrentProcess();
        int code = 0;

        while (!Stop)
        {
            int got = 0;
            while (got < FrameBytes)
            {
                int n = stream.Read(buf, got, FrameBytes - got);
                if (n <= 0) break;
                got += n;
            }
            if (got < FrameBytes)
            {
                if (input == null) { Write("{\"type\":\"error\",\"at\":" + NowMs() + ",\"text\":\"audio stream ended\"}"); code = 2; }
                break;
            }
            long now = NowMs();
            if (t0 < 0) t0 = t0Override >= 0 ? t0Override : now;      // stream origin = first frame's arrival

            // ---- per-frame energies, identical definitions to the reference
            double sTot = 0, sMid = 0, sSide = 0;
            bool allZero = true;
            for (int k = 0; k < FrameBytes; k += 4)
            {
                short l = (short)(buf[k] | (buf[k + 1] << 8)), r = (short)(buf[k + 2] | (buf[k + 3] << 8));
                if (l != 0 || r != 0) allZero = false;
                double x = l / 32768.0, y = r / 32768.0, m = (x + y) * 0.5, d = (x - y) * 0.5;
                sTot += x * x + y * y; sMid += m * m; sSide += d * d;
            }
            int slot = (int)(frames % Ring);
            ETot[slot] = sTot / (2.0 * Frame); EMid[slot] = sMid / Frame; ESide[slot] = sSide / Frame;
            double lvl = Db(ETot[slot]);

            // ---- tap silence
            zeroRun = allZero ? zeroRun + 1 : 0;
            if (!silent && zeroRun >= SilentFrames)
            {
                silent = true;
                Write("{\"type\":\"silent\",\"at\":" + now + ",\"streamMs\":" + (t0 + (frames - SilentFrames + 1) * 10) + ",\"text\":\"tap delivers exact zeros; no verdicts\"}");
                proc.Refresh(); WriteState(now, true, frames, proc.TotalProcessorTime.TotalMilliseconds, input == null ? (now - (t0 + frames * 10)).ToString(Inv) : "null");
            }
            if (silent && !allZero)
            {
                silent = false;
                Write("{\"type\":\"signal\",\"at\":" + now + ",\"streamMs\":" + (t0 + frames * 10) + "}");
                proc.Refresh(); WriteState(now, false, frames, proc.TotalProcessorTime.TotalMilliseconds, input == null ? (now - (t0 + frames * 10)).ToString(Inv) : "null");
            }

            // ---- run tracking (frames at or below -50 dBFS)
            if (lvl <= RunThresholdDb)
            {
                if (runStart < 0) { runStart = frames; runFloor = lvl; } else if (lvl < runFloor) runFloor = lvl;
            }
            else if (runStart >= 0)
            {
                long len = frames - runStart;
                if (len >= MinRunFrames && runStart >= PreFrames) pending.Add(new Pending { Start = runStart, End = frames, Floor = runFloor });
                runStart = -1;
            }

            // ---- evaluate runs whose 1.0 s post window is complete
            for (int p = pending.Count - 1; p >= 0; p--)
            {
                var c = pending[p];
                if (frames + 1 < c.End + PostFrames) continue;
                pending.RemoveAt(p);
                double postTot = 0, postMid = 0, postSide = 0;
                for (long f = c.End; f < c.End + PostFrames; f++) { int s2 = (int)(f % Ring); postTot += ETot[s2]; postMid += EMid[s2]; postSide += ESide[s2]; }
                double postLvl = Db(postTot / PostFrames), postMs = Math.Min(Db(postMid / Math.Max(postSide, 1e-12)), 60.0);
                double preLvl = double.NaN, preMs = double.NaN;
                if (c.Start - PreFrames >= frames - Ring + 1)
                {
                    double preTot = 0, preMid = 0, preSide = 0;
                    for (long f = c.Start - PreFrames; f < c.Start - GapFrames; f++) { int s2 = (int)(f % Ring); preTot += ETot[s2]; preMid += EMid[s2]; preSide += ESide[s2]; }
                    preLvl = Db(preTot / (PreFrames - GapFrames)); preMs = Math.Min(Db(preMid / Math.Max(preSide, 1e-12)), 60.0);
                }
                long durMs = (c.End - c.Start) * 10;
                bool trigger = durMs >= MinTriggerMs && durMs <= MaxTriggerMs && c.Floor <= FloorDb && postMs < MonoDb;
                if (!trigger && !(durMs >= MinTriggerMs && c.Floor <= CandidateFloorDb)) continue;
                long dipStart = t0 + c.Start * 10, dipEnd = t0 + c.End * 10, decision = dipEnd + 1000;
                if (trigger) triggers++; else candidates++;
                string row = "{\"type\":\"" + (trigger ? "trigger" : "candidate") + "\",\"dipStartMs\":" + dipStart + ",\"dipEndMs\":" + dipEnd + ",\"decisionMs\":" + decision +
                             ",\"wallMs\":" + now + ",\"durMs\":" + durMs + ",\"floorDb\":" + F(c.Floor) + ",\"postLevelDb\":" + F(postLvl) + ",\"postMidSideDb\":" + F(postMs) +
                             ",\"preLevelDb\":" + F(preLvl) + ",\"preMidSideDb\":" + F(preMs) + ",\"streamS\":" + F(c.Start * 0.01) + "}";
                Write(row);
                if (trigger && ResultPath != null)
                {
                    try { File.WriteAllText(ResultPath + ".tmp", row); File.Move(ResultPath + ".tmp", ResultPath, true); } catch { }
                }
            }

            frames++;
            if (statsSec > 0 && now - lastStats >= statsSec * 1000L)
            {
                lastStats = now;
                proc.Refresh();
                string lag = input == null ? (now - (t0 + frames * 10)).ToString(Inv) : "null";
                Write("{\"type\":\"stats\",\"at\":" + now + ",\"frames\":" + frames + ",\"streamS\":" + F(frames * 0.01) + ",\"cpuMs\":" + F(proc.TotalProcessorTime.TotalMilliseconds) +
                      ",\"rssKb\":" + Rss() + ",\"lagMs\":" + lag + ",\"silent\":" + (silent ? "true" : "false") +
                      ",\"candidates\":" + candidates + ",\"triggers\":" + triggers + "}");
                WriteState(now, silent, frames, proc.TotalProcessorTime.TotalMilliseconds, lag);
            }
            if (seconds > 0 && frames >= seconds * 100) break;
        }

        try { if (arecord != null && !arecord.HasExited) { arecord.Kill(); arecord.WaitForExit(2000); } } catch { }
        proc.Refresh();
        Write("{\"type\":\"end\",\"at\":" + NowMs() + ",\"frames\":" + frames + ",\"streamS\":" + F(frames * 0.01) + ",\"cpuMs\":" + F(proc.TotalProcessorTime.TotalMilliseconds) +
              ",\"cpuMsPerAudioSecond\":" + F(frames > 0 ? proc.TotalProcessorTime.TotalMilliseconds / (frames * 0.01) : 0) + ",\"rssKb\":" + Rss() + ",\"candidates\":" + candidates + ",\"triggers\":" + triggers + ",\"exit\":" + code + "}");
        Log.Flush();
        return code;
    }
}
