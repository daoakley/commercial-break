# Findings, failed approaches and evidence limits

## Capture and display

On the tested 2022 Frame, `dc_request_capture_to_file_sync` in `libdisplay-capture-api.so.0` provides display frames. A hash-checked process-local copy of `libtzcapturec.so` changes an executable allowlist entry for the .NET probe. Original firmware files remain unchanged. The direct video-plane capture attempt did not produce protected YouTube TV video. Ordinary app signing did not establish capture privileges.

Backlight 0/50 still showed the image. LFD physical panel mute made it black in an owner-confirmed 30-second test while internal screenshots remained readable. Panel mute is therefore used while the card briefly drops. The one-shot capture restores the card after a 225 ms latch delay; contamination remains a risk. The alternative completion-handshake/persistent/warm trial caused visible black/show loops and was rolled back. Do not interpret throughput alone as success.

## YouTube events

DIAL/Lounge access disproved the assumption that the app was completely opaque. A live test saw six inserted-ad events with state 1081. Durations converged on a shared pod end within 0.30 seconds. Broadcast commercials appeared before and after that inserted pod. Some ad breaks produced no native event at all. Native positives may accelerate onset; absence/end cannot release a visual cover. Cached ad IDs and program IDs must not be confused with current playback transitions.

The metadata observer had a Python 3.9 exception mismatch: `socket.timeout` was not caught by `except TimeoutError`. Fixed by handling socket timeouts and wrapped URL errors inside the poll loop, preserving one session, correcting command sequence, and retaining the cloud session while clearing old local metadata on navigation. Five minutes of stable playback followed. The exact TV app-exit mechanism remains unknown.

## Non-AI signals

A narrow Sponsored-pill template was useful on matching YouTube TV frames; many ads lack the pill. Sports scoreboards, news banners, tune-in bugs and split-screen sponsorship are hard negatives. Brightness, scene cuts, logo loss and loudness are not independently reliable commercial proof.

PulseAudio monitor capture was silent. ALSA `hw:0,5` (48 kHz stereo S16_LE) yielded PCM during playback and speaker mute. Loudness distributions overlapped. Deep silence also occurred during ordinary DIY content. The initial boundary rule did not precede any of four covered ad starts in two studies; later studies found some earlier candidates but visually confirmed program false cues. Do not mute on silence/volume alone.

Repeated-ad audio fingerprints were more promising:

- One fixed five-second ad template scored ~0.997 on an independently captured repeat, with selected program controls below 0.50.
- A prospective one-hour run recognized two repeats of that ad (~0.995 and ~0.999); limited program controls stayed below the 0.90 candidate threshold.
- A second advertiser spot independently repeated at ~0.999 but lacked prospective validation.
- Two-second uploads were feasible. One later known-ad match was reported 5.2 seconds after the start of its five-second matching audio. This is not exact ad-onset latency; the first saved ad screenshot was ~0.2 seconds after that report, with the preceding screenshot ~10 seconds earlier.
- Nearest-single-screenshot labeling initially misassigned a transition as program. Correct analysis marks conflicting-label intervals as transition and uses the first received match, not a later duplicate.

These are a few known creative matches, not a generalized non-AI classifier or a calibrated very low false-alarm rate. The study stopped when the TV stopped answering. No collector should be restarted automatically during handoff.

## Research source trail

- [Watching the Watchers](https://watchingthewatchers.github.io/watchingthewatchers/index.html): motivation for owner control and ACR research; encrypted traffic consistent with ACR is not decoded viewing payload. It does not establish a local commercial-start API on this TV.
- [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root): temporary root dependency; ordinary retail `sdb shell` closing does not alone rule out the documented root route.
- [pyytlounge implementation](https://pyytlounge.readthedocs.io/en/stable/_modules/pyytlounge/wrapper.html): session/poll/command sequence reference for the metadata repair.
- Audio literature previously examined: [arXiv 1811.02411](https://arxiv.org/abs/1811.02411), [Anguera et al. paper](https://xavieranguera.com/papers/cimca_2008.pdf), [WACV 2023 ad detection paper](https://openaccess.thecvf.com/content/WACV2023/html/Liu_A_Deep_Neural_Framework_To_Detect_Individual_Advertisement_Ad_From_WACV_2023_paper.html).

The study reports in `research/audio/` retain chronological observations. Their “collecting” statements are historical; current collection is stopped. Research methods and datasets from papers are not automatically validated on this TV. No current runtime dependency on Samsung ACR results has been established, and this app does not disable Samsung tracking.
