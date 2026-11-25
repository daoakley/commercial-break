using System;
using System.Collections.Generic;
using System.Text.Json;

// A result is positive only when its AD candidate is tied to the submitted frame.
// Malformed siblings provide no evidence and cannot suppress a valid candidate.
internal static class SamsungVerdict
{
    static JsonElement Get(JsonElement value, string name) =>
        value.ValueKind == JsonValueKind.Object && value.TryGetProperty(name, out var item)
            ? item : default;

    static bool TextIs(JsonElement value, string text) =>
        value.ValueKind == JsonValueKind.String && value.GetString() == text;

    static bool IntegerIs(JsonElement value, int number) =>
        value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out int parsed) && parsed == number;

    static bool Current(JsonElement value, string at) => TextIs(Get(Get(value, "tvt"), "utc"), at);

    static string Id(JsonElement value)
    {
        var id = Get(value, "vid");
        if (id.ValueKind != JsonValueKind.String && id.ValueKind != JsonValueKind.Number) return null;
        string text = id.ToString();
        return string.IsNullOrWhiteSpace(text) ? null : text;
    }

    static IEnumerable<JsonElement> Items(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Array)
            foreach (var item in value.EnumerateArray()) yield return item;
    }

    static IEnumerable<JsonElement> Candidates(JsonElement value)
    {
        yield return Get(value, "main");
        foreach (var item in Items(Get(value, "multi"))) yield return item;
    }

    internal static bool IsAd(JsonElement response, string at)
    {
        if (string.IsNullOrEmpty(at)) return false;
        var acr = Get(Get(response, "result"), "acr");
        var content = Get(acr, "recog_content");
        if (Get(content, "matching").ValueKind != JsonValueKind.True) return false;

        var currentIds = new HashSet<string>(StringComparer.Ordinal);
        bool currentMatch = false, allMatchesCurrent = true;
        foreach (var frame in Items(Get(acr, "result_frames")))
        {
            if (Get(frame, "matching").ValueKind != JsonValueKind.True) continue;
            if (!Current(frame, at)) { allMatchesCurrent = false; continue; }
            var distance = Get(frame, "dist");
            if (distance.ValueKind != JsonValueKind.Number || !distance.TryGetInt32(out int dist) || dist < 0 || dist > 15) continue;
            currentMatch = true;
            foreach (var candidate in Candidates(frame))
            {
                string id = Id(candidate);
                if (id != null) currentIds.Add(id);
            }
        }
        if (!currentMatch) return false;

        foreach (var candidate in Candidates(content))
        {
            string id = Id(candidate);
            if (id != null && currentIds.Contains(id) && TextIs(Get(Get(candidate, "content"), "type"), "AD")) return true;
        }

        var confidence = Get(content, "confidence");
        if (!allMatchesCurrent || !Current(content, at) || !Current(confidence, at)) return false;
        var confidenceIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in Items(Get(confidence, "cc")))
        {
            string id = Id(item);
            if (id != null && IntegerIs(Get(item, "source"), 4) && IntegerIs(Get(item, "keepCnt"), 0)) confidenceIds.Add(id);
        }
        foreach (var candidate in Candidates(content))
        {
            string id = Id(candidate);
            var detail = Get(candidate, "content");
            if (id != null && confidenceIds.Contains(id) && IntegerIs(Get(candidate, "source"), 4) &&
                TextIs(Get(detail, "type"), "AD") && TextIs(Get(detail, "ccType"), "AD")) return true;
        }
        return false;
    }
}
