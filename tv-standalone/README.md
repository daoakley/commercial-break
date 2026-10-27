# Standalone TV app

This is the current Commercial Break controller, background engine and themed
card renderer. The engine runs on the TV and targets YouTube TV. It combines
Samsung recognition with the [local Sponsored-pill detector](SPONSORED_PILL.md)
and an optional [experimental spatial classifier](EXPERIMENTAL_LAYOUT.md).
It does not require the repository's computer-assisted detector or an LLM.
Samsung recognition still uses Samsung's network service.

## Controls and appearance

The installed **Commercial Break** app provides **On**, **Off**, **Start debug
recording**, and **Break screen** controls. Closing the controller leaves an
enabled background engine running. A TV reboot currently requires restarting
the privileged engine; the installed app alone cannot restore that access.

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
  and Night, plus automatic, day-only and night-only city rotation.

Custom scenes show only the clock in the upper-right, with no program metadata
or break statistics over the artwork. Original retains its original information
layout. **Rotate cities · Automatic** cycles Memphis → Washington DC → Raleigh →
Charlotte. Day/night follows Raleigh sunrise and sunset using NOAA solar-position
math and the TV clock, entirely offline. The location is currently fixed to Raleigh.
The current scene stays fixed until the break ends, including through capture
pauses and lease renewals. The next-city cursor survives engine restarts. A new
break means the detector enters covered state; if it releases and re-enters within
one broadcast ad pod, that counts as another break for rotation.

Day-only/night-only rotation and individual city choices remain available.
Holiday themes are selected manually. Missing or corrupt city assets are skipped;
if no valid scene exists for the selected lighting, Original is used. A cursor
write failure does not prevent ad covering.
The current Raleigh scenes use revised PNC and Wells Fargo silhouettes and a
wooded foreground. Artwork consists of original geometric compositions rendered
locally with EFL primitives; no downloaded art or animation service is needed.

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

## Provisioning and deployment

This is not a complete redistributable installer. A fresh device needs a working
[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) temporary root
route, a compatible `sdb`, the tested TV runtime/native APIs, Samsung recognition
configuration from that authorized device, and a signed Tizen controller package.
An ordinary app certificate does not grant the engine's capture privileges.

For an existing compatible installation:

1. Back up its engine/helper files and preserve its private configuration,
   selected appearance, enabled state and original debug expiry.
2. Build and stage the engine, capture helper, navigation observer and renderer
   with their runtime configuration files under the engine's configured home:
   `/opt/usr/home/owner/commercial-block`.
3. Include `scene.json`, the generated `themes/` directory and `scripts/watchdog.sh`.
   The renderer needs the coordinated clock-only update; replacing only the UI
   cannot hide its old information fields.
4. Package the controller from `app/`, including the generated `themes.js`,
   `appearance.js`, and `appearance.css`, with your signing profile, icon and
   private `device.js`. The latter supplies `window.COMMERCIAL_BLOCK_TOKEN`,
   matching the engine's private `device.json` control token. Neither file nor
   signing material belongs in Git. Retain the existing app identity when
   updating an installed controller.
5. Replace components together, restart only the blocker and its helpers, restore
   the previous enabled state, and inspect the authenticated `/status` response.
   Do not reset debug to obtain a fresh deadline. Verify navigation, appearance,
   a normal ad break and return to programming on the actual TV.

Device-specific recognition credentials, native Samsung libraries, private
control files, signing material, icon assets and trained layout weights are not
bundled. The optional layout model is not required for Samsung/Sponsored
operation. Source publication does not provide credentials or guarantee that
other firmware can be provisioned through the same path.

The controller manifest currently describes version 0.4.0. Internal names such
as `CommercialBlock.dll` remain for installation compatibility; the visible app
name is **Commercial Break**.

## Crash recovery

The on-TV engine now has [bounded private crash logs and a local recovery
supervisor](RECOVERY.md). It restarts after process exits, stalled detection or
repeated recognition failures while preserving your On/Off setting. Full reboot
recovery still requires temporary privileged access.

## Runtime controls and maintenance

The engine listens on `http://127.0.0.1:18764` on the TV and requires the private
Bearer control token. The controller calls it locally; it is not a LAN dashboard.

| Endpoint | Purpose |
| --- | --- |
| `GET /status` | Engine, capture, matches, debug and selected/active theme status |
| `POST /control` | Main On/Off, JSON `{"enabled":true}` or `false` |
| `POST /appearance` | Select an allowlisted theme, e.g. `{"theme":"raleigh-night"}` |
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
