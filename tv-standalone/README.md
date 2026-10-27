# Commercial Break: standalone TV app

The local [Sponsored-pill fast path](SPONSORED_PILL.md) checks YouTube TV captures before Samsung recognition. It runs without an AI service and retains the existing theme, navigation, and release safeguards.

This source snapshot adds a **Break screen** selector to the standalone Samsung-only controller. It is separate from the computer-assisted blocker at the repository root. The feature branch has been built and tested offline and previewed in a browser; it has now been installed on the development Frame TV. The engine and controller installation and saved Original preference are verified; physical remote navigation and themed overlays still need viewer validation.

Open **Break screen**, choose a collection and scene, then select **Use this theme**. Browsing previews does not save. **Keep Original** previews the original graphic; save to restore it. Remote directional keys and Enter navigate; Back closes. The selection persists on the TV and applies when the next overlay starts. A visible break card is not restarted to change its artwork.

## Choices

- Original: the existing scene, unchanged.
- Seasons: Spring blossom, Summer shore, Autumn amber, Winter stillness.
- US holidays: New Year, Valentine's Day, Easter morning, Independence Day, Halloween moon, Thanksgiving harvest, Christmas woodland.
- Zen: Desert quiet, Quiet water, Mist & mountains.
- City skylines: Raleigh, Memphis, Washington DC, and Charlotte, each in Day and Night.

These are still geometric scenes rendered locally with the existing EFL overlay primitives. No cloud artwork, animation, image download, or new inference service is required. Themes are selected manually; there is no automatic calendar switching. Browser previews approximate SamsungOne typography and must be checked on-device before release.

## Safe preview

From the repository root:

```sh
python3 -m http.server 8797 --bind 127.0.0.1 --directory tv-standalone/app
```

Open http://127.0.0.1:8797/preview.html. This page loads neither device credentials nor the controller, and its Save action is an in-memory simulation. It cannot contact the TV.

## Implementation and maintenance

`scripts/build-themes.py` is the artwork source. Run it after an artwork change to regenerate `app/themes.js` and `engine/themes/*.json`. `engine/scene.json` is the original source of truth; the default renderer still uses that exact file. The scene catalog is bounded to 256 objects and 1 MiB per scene. Each scene starts with a full opaque background.

`ThemeSettings.cs` validates allowlisted IDs, rejects missing or invalid files, atomically saves `appearance.json`, and falls back to Original. Adding a theme requires updating both the generator and the allowlist. `/appearance` accepts authenticated POST JSON `{"theme":"winter"}`; `/status` reports the saved, effective, and active theme. The existing control token is reused without adding another credential. A failed HTTP request does not imply a confirmed save; inspect status again if a response is lost.

The browser UI is `app/appearance.js` and `app/appearance.css`. `preview.html` uses the same UI and generated scene data. Appearance is independent of enable/disable, recognition, debug retention, and mute ownership.

## Build and checks

The TV engine targets its existing .NET Core 3.1 runtime. An appropriate .NET SDK and target references are needed locally; the settings test targets .NET 6.

```sh
python3 tv-standalone/scripts/build-themes.py
python3 tv-standalone/tests/test_themes.py
node tv-standalone/tests/test_debug_ui.js
dotnet build tv-standalone/engine/CommercialBlock.csproj -c Release
dotnet run --project tv-standalone/tests/themes/ThemeTests.csproj -- tv-standalone/engine
python3 tv-standalone/tests/test_verdicts.py /path/to/dotnet
```

The verdict tests replay fixtures offline; they never connect to Samsung or a TV. Theme tests cover persistence, rejected IDs, missing/corrupt artwork, invalid preferences, and restoring Original.

## Deployment boundary

This directory includes the existing standalone engine/controller source needed to review the theme integration. It is **not a complete redistributable TV installer**. Device-specific provisioning, signing, icon assets, native capture libraries, credentials, root/bootstrap helpers, and firmware dependencies are not included. Existing native dependencies must be supplied from the authorized target TV. Do not publish `device.js`, `device.json`, `appearance.json`, captures, or native binaries.

For an existing compatible installation, a coordinated release needs the rebuilt engine, the original `scene.json`, the generated `themes/` directory beneath the engine home, and a signed controller package including `themes.js`, `appearance.js`, and `appearance.css`. Preserve its private device configuration. Check font/layout, remote focus, persistence, and one normal commercial break on-device before merging/deploying. Deployment to the development Frame TV completed after explicit user approval. The Original scene hash was unchanged, the new engine hash matched the local build, and the existing enabled state and debug expiry/records were preserved. No themed overlay was forced over viewing. Physical theme navigation and appearance remain to be confirmed.

### v0.3.2 TV compatibility correction

The first deployed UI used CSS `inset`, unsupported by the Frame's Chromium 85 browser, so the fixed panel remained below the main document. Explicit top/right/bottom/left and width/height replace it. The preview now also loads the controller stylesheet. The viewer confirmed that preview, categories and Save are fully visible after this correction.

Private packaging must preserve `device.js` from the prior signed package or generate it from the installation's existing private control token; the public source placeholder cannot authenticate. v0.3.2 restores the exact pre-update credential file, with no token rotation or new permissions. Verify package identity, nonempty credential and equality to the existing installation credential **before** installing. Do not print or commit the credential.

### Warm-renderer theme changes

The renderer remains alive in standby between breaks. The engine now retires a stale renderer before starting a new break when its loaded theme differs from the saved effective theme. Saving during an active break keeps that card stable; the next break uses the new scene. Unchanged themes retain the warm process.

`dotnet run --project tv-standalone/tests/theme-lifecycle/LifecycleTests.csproj -- tv-standalone/engine` exercises the engine helper with a real temporary child process, without accessing TV services: unchanged renderer stays alive, active cover stays alive after selection changes, idle stale renderer exits, and saved settings survive.

### v0.4.0: city silhouettes and clock-only custom artwork

All custom scenes specify `infoMode: "clock"`. The native renderer shows only the time of day in the upper-right, without program metadata, reassurance text, break counters, elapsed time or daily totals over the art. Original retains its prior information layout. The browser preview draws the same clock placement; day/night versions are manually selected.

The 23-theme catalog includes eight original vector city compositions. `scripts/skyline-art.py` defines each city's landmark geometry and paired palettes, called by `build-themes.py`. Skyline geometry stays below the central typography. Raleigh uses PNC's offset spire and Wells Fargo's terraced crown; Memphis uses the Pyramid and Hernando de Soto Bridge; DC uses the Capitol, Washington Monument and Lincoln Memorial; Charlotte uses Corporate Center's crown and 550 South Tryon's angular cutout. These are stylized landmark compositions, not surveyed silhouettes or literal views from one location.

Architectural references were studied, not bundled or traced as raster assets: [Raleigh photograph](https://raleighskyline.com/2015/downtown-raleigh-in-the-spring-2015/3340/raleigh-aerial-of-pnc-plaza/), [Charlotte office photograph](https://www.parkerpoe.com/offices/charlotte), [Memphis tourism](https://www.memphistravel.com/neighborhoods/downtown), [DC landmark view-plane study](https://planning.dc.gov/am/page/capital-landmarks-view-plane-study).

Updating existing custom scenes to clock-only requires both the generated JSON and the rebuilt native overlay. A controller-only update cannot hide native stats. The coordinated v0.4.0 deployment preserves private configuration and the saved theme; it includes the engine allowlist, renderer, theme JSON and signed controller.

## Optional experimental advertising-layout pilot

See [EXPERIMENTAL_LAYOUT.md](EXPERIMENTAL_LAYOUT.md) for the separately switchable TV-local pilot, its measured cost, limitations, and off command.
