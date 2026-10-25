# Private, bounded audio research (observation only)

These tools record PCM and score acoustic transitions/known-ad fingerprints; none can command TV mute. No samples, templates from private recordings, raw labels or credentials are distributed. Read the historical findings and validation limits in `../../docs/RESEARCH.md`.

Use one collector only, after confirming that no collector already owns the TV audio device. TV capture was tested on `hw:0,5`, 48 kHz stereo S16_LE. Do not assume that device mapping on another TV. `tv-audio-stream-study.sh` uses bounded continuous capture and two- or three-second uploads; `tv-audio-study.sh` is the older bounded chunked version.

Configuration (private environment):

- `FRAME_TOKEN`: matching study receiver/TV token; never print it.
- `AUDIO_STUDY_URL`: TV upload URL, e.g. `http://YOUR_COMPUTER_LAN_IP:28975/pcm`.
- `AUDIO_STUDY_HOST`, `AUDIO_STUDY_PORT`: receiver bind address/port (default localhost/28975; set a trusted LAN address for the TV).
- `AUDIO_STUDY_DIR`: private output directory (default `audio-study`).
- `DETECTOR_PROJECT`, `DETECTOR_ENV`: Compose project and private env for read-only verdict log association.
- `AUDIO_CHUNK_SECONDS`: receiver chunk length; must match TV `AUDIO_STUDY_CHUNK_SECONDS`.
- `AUDIO_STUDY_CHUNKS`: bounded TV slice count; inspect the script before choosing a duration.
- `AUDIO_FINGERPRINT_LIBRARY`: optional private validated template library; inspect `fingerprint_shadow.py` for its format.

The receiver watches detector labels to associate clips; those labels are not independent ground truth. Validate against timestamped screenshots/human labels and treat intervals between contradictory screenshots as transitions. No auto-collection is started by the Docker app or dashboard. Study files may contain viewing history and audio; keep them out of Git and apply an explicit retention policy.

Core analysis uses Python; spectral fingerprints need NumPy. Run `python3 -m unittest discover -s . -p 'test_*.py' -q` here. CLI analyzers expose `--help`; starting `audio_study_receiver.py` starts a private receiver, so configure it deliberately rather than using it for a help probe.
