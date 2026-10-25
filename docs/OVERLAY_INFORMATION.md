# Information on the Commercial Break card

The optional information panel makes the otherwise quiet cover useful without
adding capture or model requests. It shows the current source, an inferred or
supplied show title when available, elapsed time since the detector observed
the covered break, recent covered-break count, learned typical duration, and a
sampled program/ad/coverage timeline. Brief context notes rotate every twelve
seconds. There is no animation or fabricated trivia.

## Meaning of the information

- Inferred titles begin with **Likely:**. Unknown titles use “Your viewing session.”
- Elapsed time starts at the detector's observation, not the actual broadcast
  boundary. Coverage means the controller requested a cover; it is not an
  independent optical measurement of the panel.
- Typical duration needs three completed, consistent observed breaks. Frequency
  needs three consistent inter-break gaps. Both use a median and dispersion
  check; neither is a promised countdown or an instruction to mute.
- The timeline separates program, observed ad, requested coverage and unknown
  time. It never fills more than thirty seconds after any single sample; longer
  outages remain unknown. At most 240 observations and 80 rendered segments
  are retained, within a window of at most thirty minutes.
- Context clears with the existing playback-generation/show reset. It is not
  durable viewing history and is lost when the detector restarts. First-observed
  time is not the scheduled program start.
- Native YouTube ad progress, ad counts and confirmed show metadata are not yet
  wired into this card. The pairing/event experiment remains observation-only.

## How it works and fails safely

The existing sequential `/v1/frame` response carries bounded base64 JSON in
`X-Overlay-Info`. The TV helper validates its size and alphabet, decodes it to a
private temporary file, and replaces `overlay-info.json` atomically. The
native renderer updates retained text and timeline objects once per second.
Text is plain Evas text, not executable markup. The main card's title and rule
stay in their original positions so the local own-card detector can recognize
it. The dark-surround check uses reserved outer margins, which the information
panel never occupies.

Information never renews the card lease, changes capture frequency or requests
mute. Malformed data or data older than 45 seconds removes only the optional
panel. Navigation, pause acknowledgments, expiring leases and normal fail-open
restoration retain their existing authority. Missing information does not
remove the basic Commercial Break title. The helper is still sequential;
this change does not enable experimental warm/persistent capture modes.

## Validation on the owner's TV

On 24 October 2026, 76 repository tests passed. New tests cover unknown values,
inference labels, context reset, outage gaps, error release, session rejection,
bounded storage/payload and shell transport. A native twelve-second preview
rendered the information panel, and the local detector recognized its captured
image as its own card. In 97 saved TV frames, the updated matcher found one
actual cover card and did not match the other 96 program/ad frames. This is a
regression check, not a general false-positive-rate estimate.

The updated helper then displayed fresh context during a real commercial
break. No runtime credentials or proprietary libraries changed. Rebuild both
the Docker detector and native overlay, stage the updated TV shell helpers,
and use the documented graceful stop/start procedure. Keep the previous image
and TV files for rollback. The existing card remains usable without this data.
