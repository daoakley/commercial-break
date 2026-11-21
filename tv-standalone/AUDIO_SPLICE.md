# Optional audio splice experiment

`engine/audio/AudioSpliceObserver.csproj` is a TV-local signal observer. It reads
48 kHz stereo PCM from the tested `hw:0,5` audio tap through `arecord`, measures
short low-energy gaps and post-gap stereo energy, and reports candidate splices.
A splice is not proof of a commercial. This experiment has no established general
ad-detection accuracy and is not required for YouTube or YouTube TV blocking.

The normal build bundle includes the helper; fresh installations leave it off.
The authenticated TV-local `POST /audio` endpoint accepts `{"mode":0}` through
`{"mode":3}`:

| Mode | Behavior |
| --- | --- |
| 0 | Off |
| 1 | Observe and record scalar diagnostics only |
| 2 | Experimental trigger on YouTube TV, subject to quiet/cooldown gates and the existing short cover lease |
| 3 | Trigger a bounded burst of YouTube TV recognition checks; an audio splice alone does not cover |

The helper itself never mutes or covers. Engine actions are limited to YouTube TV;
regular YouTube remains on its local UI detector. The main Off control stops the
helper. A silent tap produces no usable decisions. Audio routing and firmware can
make the tested tap unavailable. A missing helper disables audio at startup.

PCM is processed in memory, not saved as recordings. Diagnostic logs contain
scalar events and keep one previous file after roughly 1 MB. Keep runtime logs
private. Mode 2 may mistake program edits for ads; use observation mode when
evaluating new sources rather than treating this experiment as a validated backup.

For an offline check, build the project and pass `--input PRIVATE.raw --t0 0`.
Input is stereo signed 16-bit little-endian PCM at 48 kHz. No real audio samples
or device configuration are distributed in this repository.
