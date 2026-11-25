# Standalone TV app

Commercial Break runs its controller, background engine and card renderer on
the TV. It supports regular YouTube (`com.samsung.tv.cobalt-yt`) and YouTube TV
(`com.samsung.tv.cobalt-yttv`). Neither requires a computer or an LLM during viewing.

Regular YouTube uses the [local countdown/Skip detector](YOUTUBE_AD_CONTROLS.md)
and makes no Samsung recognition requests. YouTube TV combines Samsung recognition,
the [Sponsored-pill detector](SPONSORED_PILL.md) and an optional
[experimental layout classifier](EXPERIMENTAL_LAYOUT.md). Samsung recognition
requires network access. The [audio experiment](AUDIO_SPLICE.md) is optional and
disabled on fresh installations.

## Controls and appearance

The installed **Commercial Break** app provides **On**, **Off**, **Start debug
recording**, and **Break screen** controls. Closing the controller leaves an
enabled background engine running. The optional [boot recovery widget](recovery/README.md)
can restore privileged access and restart the engine after a full reboot when
Developer Mode Host PC IP is `127.0.0.1` and the widget starts. With Developer
Mode pointed at a computer, use [computer-assisted recovery](RECOVERY.md#full-tv-reboot)
after a full reboot. The controller alone does not provide boot recovery.

Open **Break screen**, choose a collection and scene, then select **Use this
theme**. Browsing previews does not save. **Keep Original** previews the original
graphic; save it to restore that design. Remote directional keys and Enter
navigate; Back closes the selector. A saved theme applies to the next break.
An active break card keeps its current artwork.

The 26 choices are:

- Original.
- Seasons: Spring blossom, Summer shore, Autumn amber, Winter stillness.
- US holidays: New Year, Valentine's Day, Easter morning, Independence Day,
  Halloween moon, Thanksgiving harvest, Christmas woodland.
- Zen: Desert quiet, Quiet water, Mist & mountains.
- City skylines: Raleigh, Memphis, Washington DC and Charlotte, each in Day
  and Night.
- City rotation: Day, Night and Auto. Each covered break advances to the next city.
  Auto chooses day/night using a fixed Raleigh sunrise/sunset calculation.

Custom scenes show only the clock in the upper-right, with no program metadata
or break statistics over the artwork. Original retains its original information
layout. Individual scenes and holidays are manual. Only city Auto changes day/night
automatically; artwork remains fixed for an active break.
The city scenes use simplified landmark compositions, not surveyed panoramas.
Memphis separates the Pyramid's riverbank from the bridge and water; DC preserves
the Lincoln Memorial's rectangular roofline and the Washington Monument's slender
proportions. Raleigh and Charlotte use their distinctive tower crowns and connected
foregrounds. Day and night share the same landmark geometry, without vertical-only
compression. Artwork is rendered locally with EFL primitives; no downloaded art or
animation service is needed.

## Preview without a TV

```sh
python3 -m http.server 8797 --bind 127.0.0.1 --directory tv-standalone/app
```

Open http://127.0.0.1:8797/preview.html. It uses the actual theme selector and
scene data, but loads no device credentials or control connection. Save is an
in-memory simulation. Browser fonts approximate SamsungOne, so preview alone
cannot establish the exact physical TV appearance.

## Build

The TV projects target .NET Core 3.1; use an SDK with the corresponding targeting
references. Python 3 builds the theme data; Node runs the UI test.

```sh
python3 tv-standalone/scripts/build-themes.py
dotnet build tv-standalone/engine/CommercialBlock.csproj -c Release
dotnet build tv-standalone/engine/capture/AcrFrameProbe.csproj -c Release
dotnet build tv-standalone/engine/overlay/CommercialOverlayProbe.csproj -c Release
dotnet build tv-standalone/engine/navigation/NavigationObserver.csproj -c Release
```

The generated `app/themes.js` and `engine/themes/*.json` are checked in because
the controller and renderer need them at runtime. `scripts/build-themes.py` and
`scripts/skyline-art.py` are their editable sources. Do not edit generated assets
independently. `engine/scene.json` is the original graphic's source of truth.

## Installation and recovery

Follow [INSTALL.md](INSTALL.md) for prerequisites, private configuration, building
and signing both widgets, engine deployment, automatic boot setup, validation,
updates and removal. The build tool requires the owner's native capture library
and Samsung recognition configuration. It refuses an unrecognized library hash.
No signing keys, device identities, proprietary binaries or private layout model
are included.

The main controller, engine and helpers must come from the same source revision.
The visible name is **Commercial Break**; existing internal names and app IDs
are retained for upgrade compatibility. The optional experimental layout model
is not required for Samsung/Sponsored operation.

[Crash recovery](RECOVERY.md) handles process exits, stalled detection and
repeated exceptions. The separate [boot recovery service](recovery/README.md)
reacquires root after power loss and preserves the main app's On/Off setting.
An [optional firmware update lock](FIRMWARE_UPDATE_LOCK.md) can be enabled by
the TV owner and is independent of ad detection.

## Runtime controls and maintenance

The engine listens on `http://127.0.0.1:18764` on the TV and requires the private
Bearer control token. The controller calls it locally; it is not a LAN dashboard.

| Endpoint | Purpose |
| --- | --- |
| `GET /status` | Engine, capture, matches, debug and selected/active theme status |
| `POST /control` | Main On/Off, JSON `{"enabled":true}` or `false` |
| `POST /appearance` | Select an allowlisted theme, e.g. `{"theme":"raleigh-night"}` |
| `POST /maintenance` | Pause/resume with `{"paused":true/false}`; wait for `recognitionInProgress:false` before updating |
| `POST /youtube-skip` | Enable/disable guarded automatic Skip with `{"enabled":true/false}`; defaults off |
| `POST /audio` | Experimental audio mode `0` (off), `1` (observe), `2` (trigger) or `3` (recognition burst) |
| `POST /debug` | Start a debug session or stop and clear its records |
| `POST /layout` | Enable/disable only the experimental spatial classifier |

`ThemeSettings.cs` validates allowlisted scene IDs, bounds scene sizes, saves
`appearance.json` atomically, and falls back to Original on invalid configuration.
The engine replaces a stale standby renderer before the next break, while leaving
an active card stable. The UI uses explicit CSS edges rather than `inset` for
compatibility with the tested Frame's older browser.

Debug sessions expire after 48 hours and are limited to 128 MiB. Oldest records
are evicted when storage reaches the cap. Stopping debug deletes session pictures
and metadata. Expiry is checked while the engine runs and again after restart;
files cannot be cleaned while the engine/TV is off. Metadata records unavailable
channel/show values as unknown instead of inventing them.

## Tests

```sh
python3 tv-standalone/tests/test_themes.py
node tv-standalone/tests/test_debug_ui.js
dotnet run --project tv-standalone/tests/themes/ThemeTests.csproj -- tv-standalone/engine
dotnet run --project tv-standalone/tests/theme-lifecycle/LifecycleTests.csproj -- tv-standalone/engine
python3 tv-standalone/tests/test_apps.py /path/to/dotnet
python3 tv-standalone/tests/test_youtube_evidence.py /path/to/dotnet
python3 tv-standalone/tests/test_verdicts.py /path/to/dotnet
python3 tv-standalone/tests/test_pill_evidence.py /path/to/dotnet
python3 tv-standalone/tests/test_layout_evidence.py /path/to/dotnet
```

Theme harnesses use .NET 6 on the development computer. Additional pixel/model
parity tests and their dependencies are documented in the detector guides. These
tests replay local fixtures; they do not submit requests to Samsung or change
TV controls. Passing them does not establish a live ad-detection accuracy rate.

## Artwork references

Architectural references were studied, not bundled or traced as raster assets: [Raleigh photograph](https://raleighskyline.com/2015/downtown-raleigh-in-the-spring-2015/3340/raleigh-aerial-of-pnc-plaza/), [Charlotte office photograph](https://www.parkerpoe.com/offices/charlotte), [Memphis tourism](https://www.memphistravel.com/neighborhoods/downtown), [DC landmark view-plane study](https://planning.dc.gov/am/page/capital-landmarks-view-plane-study).

Landmark details: [PNC Plaza](https://www.dpr.com/projects/pnc-plaza),
[Corporate Center crown](https://www.focuslighting.com/bank-of-america-corporate-center),
[Lincoln Memorial](https://www.nps.gov/linc/learn/publications.htm),
[Washington Monument dimensions](https://www.nps.gov/wamo/faqs.htm), and
[Memphis bridges](https://www.memphistravel.com/trip-ideas/mighty-lights).
