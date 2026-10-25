# TV-internal audio capture findings

On the owner's 2022 Samsung Frame, `pactl list short sources` exposed
`tizenaudio-sink.monitor`, but a two-second 16 kHz mono capture from it
contained only zero samples during YouTube TV playback. That monitor is not a
usable playback feed in the tested state.

The ALSA capture device listed as `card 0, device 5: pcm dump0` did produce a
non-silent two-second sample while the game was playing. The capture format was
48 kHz, stereo, signed 16-bit PCM; the 384,000-byte result contained 191,927
nonzero values out of 192,000, with RMS amplitude about 1,770 on the 16-bit
scale. Capture did not change playback.

The same tap was then sampled during a classifier-controlled commercial mute.
The TV reported speaker mute on, yet the 384,000-byte capture contained
191,967 nonzero samples out of 192,000, with RMS amplitude about 2,666.
Thus the PCM signal remains available to the detector while the TV speakers
are silent. Both short raw samples were removed after measuring their signal
levels and are not included in the release archive.

A separate three-second capture was transferred to the Mac as a 48 kHz stereo
WAV file. This verified that the PCM can reach a local computer without
interrupting playback. The sample remains private and is not included in this repository.

Two short-lived trend runs measured one-second audio samples roughly every
2.2 seconds. The first run (mostly ad/uncertain visual labels) had an RMS
range of 1,135–3,597 and median of 2,446. The second run (program visual
labels) had an RMS range of 1,087–2,964 and median of 1,968. These overlap
substantially. Average level alone is not a reliable ad detector from this
evidence. Two completed longer studies and their four covered ad starts are
analyzed in `NON_AI_BACKUP.md`.

Published audio detection work points to very short low-energy intervals near
ad boundaries, acoustic changes on either side, and the spacing or repetition
of ad segments. Those 10–30 ms intervals would be blurred by the current
100 ms trend bins, so a future boundary detector should process the raw PCM
locally with roughly 10 ms analysis windows. See:

- https://arxiv.org/abs/1811.02411
- https://xavieranguera.com/papers/cimca_2008.pdf
- https://openaccess.thecvf.com/content/WACV2023/html/Liu_A_Deep_Neural_Framework_To_Detect_Individual_Advertisement_Ad_From_WACV_2023_paper.html

This establishes that an internal PCM signal is available before the speaker
mute is applied. It does not yet prove which point in the TV's audio path the
tap represents or whether an audio-only classifier can reliably distinguish
ads from program transitions. A low-risk first use
would be to trigger an earlier screenshot when the audio pattern changes;
the image classifier would still decide whether to mute.

The first paired break is detailed in `NON_AI_BACKUP.md`: a 60 ms dip near
program end preceded the first confident ad screenshot by roughly 12 seconds;
two 120–140 ms dips occurred between visually confirmed ads. The initial
strict detector found the latter two and zero during the following 140 seconds
of labeled program. Its false-negative at program end led to a revised
candidate threshold, which finds the dip in the saved clip. This is a useful
trigger hypothesis, not yet a validated commercial detector.

A separate five-second spectral-fingerprint experiment compared three saved
ad clips with the other ad clips and five screenshot-correlated program clips.
All other-clip scores were below 0.62; none provides a verified repeat of the
same ad. Rescaling and adding noise to a shifted copy of one clip scored 0.94
in an earlier synthetic check. This demonstrates a possible match method but
does **not** establish sensitivity or false-alarm performance on a real repeat.
The fingerprint experiment remains offline and does not control the TV. A
second set of saved clips still contained no visually confirmed replay of the
same ad. The revised uploader lost only five seconds across 1,200 seconds of
audio, improving temporal coverage for the comparison.

The third study subsequently captured a true replay of one campaign spot,
separated by roughly sixteen minutes. Both occurrences were checked against
saved screenshots. A five-second acoustic template from the first scored
0.9972 on the replay; the highest of 27 saved program-control scores was
0.4931. A subsequent one-hour shadow study scored every ten-second chunk
against this fixed template and found two more screenshot-confirmed replays,
with no program matches above 0.90. A subsequent 10-minute continuous-capture
pilot delivered 300 consecutive two-second chunks without a known-ad replay.
A second fast study captured a third prospective replay of the campaign spot:
its five-second template was reported 5.2 seconds after the matching audio
began, about 0.2 seconds before the first confident ad screenshot. A separate
injury-lawyer ad also had an independent replay with a 0.9991 retrospective
five-second match. Both known-ad templates remain observation-only. See
`NON_AI_BACKUP.md` for the study labels, timing limits, and validation gate.
