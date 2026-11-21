# What Samsung's content-recognition endpoint returned on one Frame TV

This is a redacted account of bounded tests on one privately owned 2022 Samsung Frame (Tizen 6.5) in October 2026. It describes Samsung's underlying recognition interface, not the logic or performance of a commercial-blocking app. The tests used the TV's own visual-fingerprint functions and its existing recognition configuration. They contacted the TV-configured Samsung matching endpoint over a verified TLS WebSocket. The independent client did not start the stock ACR service. The original stock-service test was time-limited and its prior consent and service state were restored.

The raw requests, replies, screenshots, fingerprints and device-specific configuration are withheld because they contain viewing history and device identifiers. The counts and fields below are from retained, timestamped test records. A one-shot Python client **on the owner's Mac** sent TV-generated fingerprints to Samsung and recorded the two 27 ms examples below. The computer did not convert a PNG into a Samsung fingerprint: the TV's secure capture path did that first. The nearby saved screenshot was used to check what was playing, not as the API input. The [public client source](https://github.com/daoakley/commercial-break/blob/main/tv-standalone/engine/Program.cs) shows the same request construction without private values. The [fingerprint capture source](https://github.com/daoakley/commercial-break/blob/main/tv-standalone/engine/capture/SecureFingerprint.cs) shows where the TV-native fingerprint comes from.

## What went over the connection

The Frame exposed two relevant local capture paths in this experiment. `secvideo_api_capture_screen` from `libvideo-capture.so.0` produced a **local** 480×270 PNG used to check what was on screen. The recognition client instead called `VideoCapture::getVideoYUV` from `libcapi-video-capture.so.0` and an ACR trusted-app session through `libteec` to produce the visual fingerprint. The [capture implementation](https://github.com/daoakley/commercial-break/blob/main/tv-standalone/engine/capture/Program.cs) and [fingerprint implementation](https://github.com/daoakley/commercial-break/blob/main/tv-standalone/engine/capture/SecureFingerprint.cs) show these paths. They are separate from the `TZCAPTURE_Capture_screen` interface Sagar Mohan documented on a different Samsung model.

In the **normal recognition query**, the independent client sent an array of visual fingerprint regions computed on the TV, the capture time and time zone, source and foreground-app fields, model/vendor metadata, and a pseudonymous device identity. It did **not** send the PNG screenshot in this observed request. This does not establish that every mode of Samsung's stock service avoids image or audio uploads.

The normal response was richer than an ad/no-ad flag. It included per-frame match flags and distances, an aggregate recognition result, and content candidates with fields for title, content type, category, duration, validity period and broadcaster information when available. A candidate is a possible database match; it is not necessarily the actual channel selected by the viewer.

The following is a **schematic, redacted field map**, not a raw request or reply. It preserves observed field names and nesting while omitting identity, time, fingerprint and content identifiers. Empty objects and arrays mark removed data. The shown `PROGRAM` and `AD` types occurred together in the commercial example.

```json
{
  "search": {
    "am": {},
    "acr": {
      "query_type": 1,
      "query": [
        {
          "fps": [],
          "tvt": {}
        }
      ]
    }
  }
}
```

```json
{
  "result": {
    "query_type": 1,
    "acr": {
      "result_frames": [{ "matching": true, "dist": 5 }],
      "recog_content": {
        "matching": true,
        "main": { "content": { "type": "PROGRAM" } },
        "multi": [{ "content": { "type": "AD", "ccType": "AD" } }],
        "confidence": { "cc": [] }
      }
    },
    "queryIntervalSec": 60
  }
}
```

| Test input | Samsung normal-query result | Measured request-to-reply time |
| --- | --- | ---: |
| Three fingerprints from a visually corroborated Capital One commercial | Three close frame matches; five candidates typed `AD`. The same response also contained an ION/NCIS broadcast candidate. | 27 ms |
| Three fingerprints from visually corroborated NFL game footage | Three close frame matches; zero ad candidates; game title, sports category and scheduled start/end; four possible affiliate stations carrying that game. | 27 ms |

For a more concrete example, this is a **derived summary of the observed commercial reply**, not a verbatim server payload. The three `dist` values came from its three `result_frames` entries; identifying candidate IDs and timestamps have been removed:

```json
{
  "result_frames": [{"matching": true, "dist": 5}, {"matching": true, "dist": 11}, {"matching": true, "dist": 8}],
  "AD_candidate_count": 5,
  "other_program_candidate": {"title": "NCIS", "channel": "ION Television HD"},
  "queryIntervalSec": 60,
  "request_to_reply_ms": 27
}
```

The five ad candidates do **not** establish five different advertisements. The ION/NCIS candidate does **not** establish that the TV was tuned to ION. Likewise, four affiliates are not proof of which affiliate supplied the game. These are examples of the metadata the service can associate with a visual match, not a test of identification accuracy across channels.

## The separate ad-query format

The endpoint also accepted a distinct ad query. In a paired protocol probe, the independent client replayed one already captured commercial fingerprint to both the normal recognition format and the ad-query format. The normal response included an explicit `AD` match. The ad-query response contained an `AADResult` list of five `AD` records and `totalMatchedAdContent: 5`. Both replies came from the Samsung endpoint over verified TLS. Their durations were 37 ms and 28 ms, respectively. Since this replay used a **known positive fingerprint**, it is proof of the response format and a successful lookup for that input, not a live commercial-onset test.

The ad query used `query_type: 2` with a nested group of fingerprints. Its reply had a different top-level result shape. These are **schematic** request and reply excerpts, with all identifying fields and fingerprint values omitted; one of the five returned ad records is shown:

```json
{
  "search": { "am": {}, "acr": { "query_type": 2, "query": [[{ "fps": [], "tvt": {} }]] } }
}
```

```json
{
  "result": {
    "query_type": 2,
    "totalMatchedAdContent": 5,
    "AADResult": [{ "ccType": "AD" }],
    "queryIntervalSec": 120
  }
}
```

The normal reply advertised `queryIntervalSec: 60`; the ad-query reply advertised `queryIntervalSec: 120`. These values are returned pacing instructions, not the measured round-trip time. A separate 44-second test received 17 replies at median 2.03-second spacing without a recorded error, but that short result does not establish a supported or sustainable request rate.

### Three different clocks

| Device and path | Local capture or request timing | Upload/response timing | What was established |
| --- | --- | --- | --- |
| This Frame, independent live normal-query client | 131 and 125 captures in two bounded runs; median capture/request spacing **4.08 s** and **4.26 s** | Median Samsung reply **37 ms** in both runs | Observed timing of our client, not Samsung's stock collection cadence |
| This Frame, independent 44-second burst | 17 requests; median request spacing **2.03 s** | Median reply **37 ms**, no recorded error in that window | Brief successful burst, not a long-term rate test |
| This Frame, server replies to replayed fingerprints | No live capture cadence measured by the replay | Normal reply advertised **60 s**; separate ad-query reply advertised **120 s** | Server-returned query intervals, not measured reply times or proof of the stock process's schedule |
| This Frame, stock ACR process | **Not measured** in these tests | Parameter negotiation observed; no ad verdict | No basis here for a stock capture/upload frequency |
| [Sagar's different-model S90D](https://blog.sagar.systems/blog/acr/) | Its native `TZCAPTURE_Capture_screen` path sampled about **twice per second** | Sagar reports main uploads around **60 s** and an ad-query interval around **120 s**, with server control over intervals | Firmware/live-process evidence for an S90D, **not** a measurement on this Frame |

The Frame's stock-client parameter test also exposed an **8-second configured ad-query interval while that ad-query mode was off**. It should not be equated with the separate 120-second interval in the replayed ad-query reply or with an observed stock upload rate.

## What a live paired study showed

A later bounded study compared the normal format and the ad-query format on the **same newly captured frames**. Among 66 same-frame pairs, a retrospective, stricter normal-response interpretation and the ad query agreed in all 66 cases: 11 pairs returned an ad indication from both, and 55 pairs were uncertain from both. Median measured reply durations were 37 ms for normal queries and 28.5 ms for ad queries. The requests ran sequentially, so the 9 ms median duration difference is **not** evidence that ad queries identify a break earlier.

That study exposed a parsing trap. Its original live parser counted only **2 ad-positive normal replies out of 124 samples**. The saved responses also contained separate commercial-confidence records that the parser missed. A later offline re-read, requiring a close fingerprint match, matching capture timestamps, associated content and explicit `AD` types, counted **13 ad-positive normal replies out of the same 124 samples**. The correction was *retrospective*; it was not controlling the live test. It shows that treating the first content candidate as the whole answer can miss information already in a reply. It does **not** establish a prospective recall or false-positive rate.

An “uncertain” result means these tests did not obtain a usable current-frame classification. It does not mean the frame was a program, that there was no ad, or that the server failed to process it. Grouping three recent frames can also associate a hit with an **older** frame, so a grouped result is not automatically a verdict on the current picture.

## YouTube TV: an important distinction

During a separate bounded test, the **stock Samsung ACR process** established its server connection and obtained fingerprint parameters, but logged that ACR was unavailable for the YouTube TV app. It produced no ad verdict in that test. The independent client, using the TV's own fingerprint functions and recognition endpoint while YouTube TV was in the foreground, did obtain the commercial and football-program matches above.

This establishes that **the tested stock-client eligibility rule and the endpoint's ability to match an independently submitted fingerprint were different**. It does not prove that Samsung's stock ACR normally tracks YouTube TV, that all YouTube TV ads are in its database, or that other Samsung services do or do not process that viewing activity. A separate [smart-TV ACR network study](https://watchingthewatchers.github.io/watchingthewatchers/index.html) found Samsung ACR traffic consistent with video-based recognition on its tested Tizen TV and emphasized that encrypted traffic limits what can be inferred from packets alone. Our tests add a narrow view of the request and reply **for this Frame and independent client**; they do not generalize the stock behavior to every Samsung model.

## What these tests do not prove

- What Samsung retains, joins to an account, shares, or sells after a match.
- Whether the stock service uses other image, audio or telemetry paths. The observed independent query carried fingerprints, not a screenshot PNG.
- Broad ad coverage, exact-channel identification, false-alarm rate, or reliable detection across apps, regions and firmware.
- Time from the **start of an ad on screen** to an actionable match. Network replies took tens of milliseconds, but capture timing, sampling cadence, fingerprint generation, database coverage and candidate validation all add delay.

The reported observations are specific to one TV and a limited set of test inputs. They are meant to make the underlying recognition behavior more inspectable while keeping private device and viewing data out of the repository.
