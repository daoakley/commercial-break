using System;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

// Used exclusively by RecognitionLane: no concurrent send/receive or socket disposal.
internal sealed class SamsungRecognitionClient
{
    ClientWebSocket socket;
    internal sealed class Reply
    {
        public JsonElement Response;
        public long RequestAt, ResponseAt;
        public double RoundTripMs;
        public bool Ad;
    }

    async Task<JsonElement> Exchange(object request, CancellationToken cancellation)
    {
        byte[] data = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request));
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        stop.CancelAfter(2500);
        await socket.SendAsync(new ArraySegment<byte>(data), WebSocketMessageType.Text, true, stop.Token);
        using var all = new MemoryStream();
        var bytes = new byte[32768];
        WebSocketReceiveResult part;
        do
        {
            part = await socket.ReceiveAsync(new ArraySegment<byte>(bytes), stop.Token);
            if (part.MessageType != WebSocketMessageType.Text) throw new IOException("Recognition socket closed");
            all.Write(bytes, 0, part.Count);
            if (all.Length > 1048576) throw new IOException("Recognition response too large");
        } while (!part.EndOfMessage);
        using var document = JsonDocument.Parse(all.ToArray());
        return document.RootElement.Clone();
    }

    public async Task<Reply> Query(JsonElement config, JsonElement fingerprint, string app, CancellationToken cancellation)
    {
        try
        {
            if (socket == null || socket.State != WebSocketState.Open)
            {
                socket?.Dispose();
                socket = new ClientWebSocket();
                using var stop = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                stop.CancelAfter(2500);
                await socket.ConnectAsync(new Uri("wss://acr-us-prd.samsungcloud.tv/getacrinfo"), stop.Token);
                var parameters = await Exchange(config.GetProperty("parameters"), cancellation);
                if (parameters.GetProperty("server").GetProperty("fpVersion").GetDouble() != 1.2 ||
                    !parameters.GetProperty("scte35Param").GetProperty("isMainQueryEnabled").GetBoolean())
                    throw new IOException("Recognition unavailable");
            }

            cancellation.ThrowIfCancellationRequested();
            long at = fingerprint.GetProperty("at").GetInt64();
            long age = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - at;
            if (age > 5000 || age < -2000) throw new IOException("Stale fingerprint");
            int count = fingerprint.GetProperty("roi_count").GetInt32();
            byte[] raw = Convert.FromBase64String(fingerprint.GetProperty("raw_base64").GetString());
            if (count < 1 || count > 10 || raw.Length != 180) throw new IOException("Invalid fingerprint");
            var fingerprints = new List<object>();
            for (int i = 0; i < count; i++)
            {
                var values = new List<uint>();
                for (int j = 0; j < 8; j += 2)
                {
                    int offset = i * 18 + 2 + j * 2;
                    values.Add(((uint)BitConverter.ToUInt16(raw, offset) << 16) | BitConverter.ToUInt16(raw, offset + 2));
                }
                fingerprints.Add(new { roi = i, raws = values });
            }
            var identity = config.GetProperty("identity");
            var metadata = new Dictionary<string, object>();
            foreach (string key in new[] { "psid", "vdvendorcode", "modelID" }) metadata[key] = identity.GetProperty(key).Clone();
            metadata["power"] = 1;
            metadata["tv_source"] = int.Parse(identity.GetProperty("sourceInfo").ToString());
            metadata["source_APP_Id"] = app;
            var frame = new { fps = fingerprints, tvt = new { utc = at.ToString(), tz = (int)TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow).TotalMinutes } };
            var reply = new Reply { RequestAt = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() };
            var elapsed = System.Diagnostics.Stopwatch.StartNew();
            reply.Response = await Exchange(new { api = 1, search = new { msg_ver = "3.3", am = metadata,
                acr = new { retry_cnt = 0, mtype = 1, fp_ver = "1.200000", query_type = 1, query = new[] { frame } } } }, cancellation);
            reply.RoundTripMs = elapsed.Elapsed.TotalMilliseconds;
            reply.ResponseAt = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            if (!reply.Response.TryGetProperty("result", out var body) || !body.TryGetProperty("acr", out _))
                throw new IOException("Invalid recognition response");
            reply.Ad = SamsungVerdict.IsAd(reply.Response, at.ToString());
            return reply;
        }
        catch
        {
            socket?.Dispose();
            socket = null;
            throw;
        }
    }
}
