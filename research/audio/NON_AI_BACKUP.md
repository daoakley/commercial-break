# Non-AI commercial backup: research and validation log

The backup remains **observation-only**. The TV's existing screenshot/Claude
detector still owns mute. A future audio cue might request a sooner screenshot,
but the present study code does not feed cues into the live detector. A
single silence or change in volume is not proof of a commercial. The TV keeps
playing and the current fail-safe unmutes when the computer is unavailable.

## Research applied to this TV

- Ramires et al. found that short low-energy intervals, their local context,
  and groups of boundaries can detect ad regions in 26 hours of Portuguese
  broadcast TV. Their reported overall Matthews correlation was 0.874. The
  detector used trained regression and a 150-second grouping window, so that
  result is not a measured accuracy for YouTube TV or a low-latency mute.
  https://arxiv.org/html/1811.02411v1
- Conejero and Anguera used 10–30 ms audio nulls, an acoustic-change check,
  and common ad durations. They found false boundaries during ordinary edits
  and channel-specific parameters, so a dip alone is unsafe.
  https://xavieranguera.com/papers/cimca_2008.pdf
- Liu's streaming-service study uses light audio to find segment boundaries
  and video classification to decide whether a segment is an ad; it includes
  Hulu and live sports. Its visual classifier is AI, so we cannot claim its
  accuracy for a non-AI backup.
  https://openaccess.thecvf.com/content/WACV2023/html/Liu_A_Deep_Neural_Framework_To_Detect_Individual_Advertisement_Ad_From_WACV_2023_paper.html
- Covell, Baluja and Fink used five-second acoustic repetition matches and
  visual confirmation to recognize known, repeated ads. That is the most
  promising route to a conservative backup after this TV has a validated
  local ad library. Their reported precision applies to their own broadcast
  dataset and method, not to our current prototype.
  https://www.mangolassi.org/covell/pubs/mmsp06_ads.pdf

## First paired YouTube TV break, 24 October 2026

The TV's internal 48 kHz stereo PCM capture remained non-silent while the
speakers were muted. A program-end-to-ad transition occurred around 07:04:25–
07:04:36 UTC. A screenshot at 07:04:28 showed end credits and a screenshot at
07:04:36 showed a USA Insulation ad. A local audio clip contained a 60 ms
low-energy interval around 07:04:24.8, roughly 12 seconds before the first
confident ad screenshot. The first boundary algorithm missed it because it
required loud audio on both sides; the revised candidate detector finds it.

Two further 120–140 ms deep intervals appeared at 07:04:42.57 and 07:05:07.32,
inside the visually confirmed ad block and about 25 seconds apart. The
initial strict detector found those two; it found none during the following
140 seconds of visually labeled program. In this short sample, median audio
level was slightly **lower** during ads than the program. Loudness is not a
usable stand-alone rule here.

The local audit stores selected 480×270 screenshots and verdict times under
`../../work/tv-audit/`, and audio features plus short transition clips under
`../../work/audio-study-20261024/`. These contain private viewing content and
are intentionally excluded from the release archive. The audio study is
bounded and does not change playback or mute state.

## First completed audio study

The first collector recorded 1,190 one-second audio summaries over roughly
24 minutes, with small gaps between its 10-second uploads. Of these, 240
seconds had a nearby confident screenshot label of ad, 851 had program, and
99 had no close confident label. Median audio RMS was 2,074 for ads and
2,065 for program, so overall level cannot distinguish them here.

The audio boundary code reported 10 short deep dips. Nine were nearest to an
ad screenshot; one at 07:19:30 was nearest to a program screenshot. Inspection
of the saved images showed an ad at 07:19:00 and program material at 07:19:23:
that dip was near an **ad-to-program return**, not evidence that a normal
program scene edit caused a false alarm. Conversely, several dips were inside
an ad block, where they cannot warn of its start. The code changed partway
through this first study, so these counts are descriptive, not a controlled
accuracy estimate.

Only three confident program-to-ad screenshot transitions had audio coverage
within a 15-second window. A recorded boundary fell within that window for
two; the 07:16:27 ad had no candidate until about 45 seconds later. Later
screenshot transitions occurred after the collector ended and must not be
counted as misses. Both nearby recorded candidates were **after** the first
ad screenshot, by about 6 and 13 seconds. Thus this recording does not show
that the live boundary rule can warn early. It remains a trigger hypothesis
for future testing, and it does not support audio-only muting.

## Second completed audio study

The near-continuous uploader delivered all 120 ten-second chunks, covering
1,200 audio seconds over 1,204 elapsed seconds. It found 21 boundary
candidates: 14 in one ten-second portion of an ad block, six in a later ad
block, and one at 08:00:27 while the screenshot classifier reported program.
The closest saved image to that last candidate was 54 seconds earlier, so it
is a **possible** program false alarm, not a visually confirmed one.

The single confident program-to-ad change with complete audio coverage began
at the 07:51:45 screenshot. There was no boundary candidate within 15 seconds;
the first appeared about 20 seconds later, within the ad block. Across both
completed studies, none of four covered ad starts had an audio boundary that
preceded its first ad screenshot. Two had only later candidates and two had
none within 15 seconds. This is evidence against using the present boundary
rule as an early or independent mute trigger.

The studies have no confirmed repeat of an identical commercial yet. Offline
five-second spectral comparisons among four saved ad clips and eleven program
controls produced a highest non-self score below 0.65; that only tests
nonmatches. A synthetic shifted/noisy copy matched at 0.94, but it cannot
stand in for a real replay. A third bounded study is collecting more private
ad and program samples for a held-out repeat test. Those samples remain
observation-only and never alter the TV mute decision.

### Third-study interim check, 08:40 UTC

At 1,550 captured audio seconds, the detector had reported 47 dips, with 37
nearest to program screenshots. In particular, 300 ms and 260 ms deep dips at
08:36:34 and 08:37:56 occurred during the same continuous DIY program; saved
screenshots immediately beside both dips show the host working at his bench.
These are visually confirmed **false commercial cues** for any rule that
treats deep silence as an ad. Increasing the minimum dip duration would not
remove them. Two of four covered ad starts in this interim period had a dip
before the first ad screenshot, but ordinary program content produced similar
or stronger dips. Boundary detection can remain a timing hint; it must not
control mute by itself.

The saved ad clips have not yet shown a real replay. Three 1.00 fingerprint
matches were overlapping recordings from the **same** ad break, which check
that the implementation recognizes identical audio but are not held-out
repeats. Among 92 ad-clip pairs separated by at least two minutes, the
highest score was 0.61. The study continues to look for a genuine replay.

### First visually confirmed repeat, 09:10 UTC

The same campaign spot appeared around 08:53 and again around 09:09. Saved
screenshots from both breaks show the same woman and the same H.R. 15 message.
A five-second acoustic template from the first occurrence scored **0.9972**
against the later, independently captured break. That is a real replay on
this TV, not an overlapping recording of one break. The fixed template's
highest score was 0.4931 among 27 saved program control clips and 0.4166
among 13 other saved ad clips. The score separation is promising, but these
short, selected controls do not establish a very low false-alarm rate across
long, varied viewing. The repeat was found retrospectively, so prospective
shadow testing remains necessary.

`fingerprint_shadow.py` can record a score for each incoming 10-second audio
chunk using an owner-validated local template. It combines adjacent chunks to
avoid missing a match at an upload boundary and flags scores at or above 0.90
in its study CSV. It has no path to the TV mute control. The validated template
and screenshots are private files under `work/`, not in the release archive.

A fourth bounded study began at 09:15 UTC with the fixed template loaded in
the local receiver. It records every ten-second chunk's best score, including
program footage, for a prospective false-alarm and replay check. The first
program chunk scored 0.3623. This receiver still cannot send mute commands.

At the 09:40 UTC interim check, 152 prospective chunks had been scored with
zero matches above 0.90. Nearby screenshot labels marked 117 as program and
35 as ads; their maximum scores were 0.5358 and 0.5105, respectively. One of
the ad blocks was a **different** spot for the same political campaign as the
template. Its saved image and audio score around 0.43–0.51 show that the
matcher did not confuse the campaign name with the exact known clip. No new
replay of the template has been observed yet. These are encouraging negative
controls, not a proven long-run false-alarm rate.

### Prospective replay detected, 10:10 UTC

During the fourth study, the fixed template scored 0.9946 on another airing
around 09:47:36. The saved screenshot at that instant shows the same woman
and H.R. 15 message as the original template, confirming a second independent
replay. Across the first 328 scored chunks, this was the only score at or
above 0.90. The maximum among 245 nearby program-labeled chunks was 0.5358;
57 ad-labeled chunks included the true match. Thus the matcher recognized a
real replay prospectively without a false match in this limited run. It still
does not meet the evidence needed for TV mute control.

The match was reported after a complete 10-second upload, so it cannot yet
be assumed to mute promptly. The next experiment should keep one audio
capture open and upload shorter slices; this would test both detection delay
and score stability without touching the current mute policy.

The completed fourth study delivered all 360 ten-second chunks: 3,600 audio
seconds over 3,619 elapsed seconds. It produced two distinct high-score
events, 0.9946 at 09:47 and 0.9986 at 10:11. Saved screenshots at both times
show the same H.R. 15 spot. The other 357 chunk scores stayed below 0.6438;
256 program-labeled chunks topped out at 0.5358. This is a useful prospective
result for **one known ad**, not evidence that arbitrary commercials can be
recognized without the vision model. The TV mute policy was unchanged.

A bounded ten-minute pilot began at 10:16 UTC using one continuous TV audio
capture divided into two-second uploads. Its local receiver records both the
audio match time and the time the score became available, allowing detection
latency to be measured if the known ad replays. It remains observation-only.

The pilot completed 300 consecutive two-second uploads (600 audio seconds).
The 298 scored windows were exactly two seconds apart. The median time from a
chunk's recorded start to its score being available was 1.74 seconds (95th
percentile 1.91 seconds), including the time needed to capture that chunk.
No repeat of the known H.R. 15 ad occurred, so this is **upload and scoring
latency**, not a measured ad-detection delay. No window crossed the 0.90
candidate threshold. Among screenshot-labeled windows, 211 program windows
scored at most 0.4433 and 87 other-ad windows scored at most 0.4469. The
continuous TV tap and two-second uploader worked without observed gaps in
this pilot, and the existing muter continued operating normally. A longer
bounded shadow run is needed to catch a real replay at this upload rate.

### Second independently repeated ad, 10:42 UTC

A separate offline comparison of saved ad samples found a **0.9991** five-
second match between a Riddle & Riddle injury-lawyer spot captured at 08:15
and another airing at 09:40. Screenshots from both breaks show the same
advertiser and visual creative at different points in the spot. The fixed
template scored at most 0.5675 across 47 selected program clips and 0.5472
across 26 other ad clips; the independent replay scored 0.9992 in a separate
full-clip check. The private template library now includes this second
owner-visible ad. This repeat was found retrospectively, so its template has
not yet passed a prospective shadow run. It is also only a second *known ad*,
not a general ad detector.

A 30-minute continuous-audio shadow run began at 10:42 UTC. It uses two-
second uploads and the original H.R. 15 template already loaded when the run
started. The updated two-template library will load on the next bounded run.
Neither template can currently command the TV.

### Prospective fast replay, 11:10 UTC review

The TV supplied 604 consecutive two-second uploads from 10:42:07 to 11:02:12,
then stopped sending audio and frames. Its network address no longer answered
at 11:10, so collection stopped and the overnight schedule was paused. The
audio receiver scored 602 windows. A single cluster of eight candidate rows
was one replay of the H.R. 15 spot: the first report scored **0.9998** at
10:50:10.875 for matching audio beginning 10:50:05.720, a **5.2-second**
report delay from the start of that five-second template. The first ad
screenshot was 10:50:11.081, about 0.2 seconds after the report. The prior
10:50:00.517 screenshot showed the weather segment, and the 10:50:11 frame
showed the H.R. 15 spot. The match falls inside that program-to-ad transition;
the screenshots do not establish the exact first ad frame.

An initial analysis incorrectly assigned the match to `program` because it
picked the nearest single screenshot. It also reported a 9.2-second delay by
keeping a later duplicate report with a slightly earlier matched-audio
offset. The corrected report marks the interval between conflicting labels
as `transition` and uses the **first received** report for delay. Of the 602
scored windows, 256 were program-labeled with a maximum score of 0.4553, 219
were ad-labeled with a maximum of 0.5182 apart from the transition match, 22
were transition-labeled, and 105 had no close confident screenshot. No
program-labeled window crossed the 0.90 candidate threshold in this bounded
run. The candidate remains evidence for only this known ad, not a general
commercial classifier or a sufficiently established false-alarm rate for
audio-controlled muting.

## Validation gate before audio can control mute

1. Capture several breaks and long stretches of program on this TV, including
   different channels, shows, and ad formats. Pair each candidate with an
   actual screenshot. Track missed starts and false program triggers.
2. Use boundary dips to speed up screenshots. For independent mute when Claude
   is down, prefer a *known-ad* audio fingerprint that matches for several
   seconds; corroborate it with a saved visual fingerprint when possible.
3. Test the resulting rule in shadow mode on held-out viewing sessions. It
   must avoid muting program material before it gets TV control. If evidence
   is insufficient, the backup should abstain and leave sound on.

`audio_boundary.py`, `audio_study_receiver.py`, `analyze_audio_study.py`,
`analyze_fingerprint_shadow.py`, `audio_fingerprint_trial.py`, and
`fingerprint_shadow.py` are study tools. The
fingerprint tools require NumPy on the analysis computer; they are not part of
the Docker runtime. None of these tools currently affects the mute decision.
