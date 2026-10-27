# Native-first local commercial detection

Updated 2026-10-27. This is the agreed research plan, not a claim that the planned features are already active. Priority: use a verified native answer when available; otherwise make a small, local visual decision using current TV context. The current TV blocker remains independent of the observation-only lab.

GitHub tracking: [issue #8](https://github.com/daoakley/commercial-break/issues/8). Update the issue and this register together as each path progresses.

## Implemented and measured

- [Docker lab and review UI](../experiments/vision-lab/README.md): authenticated ingestion of existing debug screenshots, contamination exclusion, metadata provenance, human frame labels, original 48-hour deadline, storage cap, and deletion of derived artifacts with source data.
- [Samsung-positive learning](../experiments/vision-lab/teacher_train.py): weak-label exemplar baseline. Unknown does not mean program. Chronological burst holdout, source binding, capture alignment checks, separate full-data candidate, no model promotion.
- [MobileCLIP zero-shot benchmark](../experiments/vision-lab/mobileclip_benchmark.py): pretrained image/text model, text features computed once, no custom training or external inference uploads. Original image preprocessing and fixed prompt variants.
- [Results and limitations](../experiments/vision-lab/ML_EVALUATION.md): exemplar model recovered 0/7 later teacher positives; MobileCLIP simple descriptions recovered 33/40 Samsung-positive frames in a different 340-frame snapshot. These are teacher agreement, not human accuracy. Targeted assistant review found apparent program false positives and missed ads.
- Existing host-feed adapter can attach fresh, source-bound native metadata from the local dashboard. The lab can run without that optional feed; missing show/channel/category information stays unknown.

## Work paths

| ID | Path | Current state | Next deliverable / evidence |
|---|---|---|---|
| L1 | Human labels and trustworthy evaluation | Individual frame labelling exists; live transition/correction controls planned | Commercial started, program resumed, wrongly blocked, unsure; click time plus onset uncertainty; entire breaks/sessions held out |
| L2 | Program profiles per channel/content session | Planned | Several confirmed program examples; visual diversity; freshness and source identity; reset/revalidation on changes; no learning from covered frames or unconfirmed ads |
| L3 | Specific commercial visual cues | Sponsored-pill matcher exists; broader cues planned | Brand/product prominence, medical-ad layouts/disclaimers, prices, phone/URL calls to action, brand-color screens; evaluate sports sponsorships and documentary product shots as counterexamples |
| L4 | Pretrained visual model plus native context | Initial zero-shot benchmark complete; fusion planned | Compare full-frame preprocessing with original center crop on a fixed evaluation set; then compare verified metadata alone, images alone, and their combination |
| L5 | Small TV-only deployment | Image-only export verified; target-TV runtime compatibility blocked | [Measured feasibility report](../experiments/vision-lab/tv-benchmark/RESULTS.md): custom native mapping rejected; stock ncnn accepts a control graph but crashes on the MobileCLIP graph. Resolve runtime compatibility before claiming TV inference speed or model RAM. |
| L6 | Iteration and regression checks | Offline experiment reports exist; automated recurring learning planned | Versioned data manifests, frozen test partitions, changes tied to errors, repeatable acceptance report, no silent promotion to playback control |

## Target-TV feasibility gate

The [26–27 October TV test](../experiments/vision-lab/tv-benchmark/RESULTS.md) verified four ARM cores, NEON, 1.74 GiB total RAM and limited variable available RAM. The image-only model exports to 43.3 MiB FP32 or 21.7 MiB FP16-stored weights, with synthetic numerical checks passing. The test did not complete an inference on the TV: the custom native runtime could not map, and the stock runtime crashed its isolated helper while loading the full graph. A tiny stock control graph passed. These are compatibility findings, not evidence that the CPU is too slow or that a particular operator is unsupported.

Keep the native/context and offline evaluation paths moving; gate sustained TV ML deployment on one correct, bounded target inference followed by resource measurements. Weight quantization alone cannot fix the observed loading/graph failures. Temporary files were removed and the existing blocker was still operating at the final checks. No model was promoted.

## L1: label now, do not wait for fine-tuning

Human corrections serve model diagnosis and evaluation immediately. Preserve the difference between human labels, Samsung teacher labels, native events, assistant review, and model predictions. Never silently promote one provenance into another.

Transition controls should store the click timestamp and a reviewable interval around it, with the observer's timing uncertainty. A late click must not automatically label every preceding frame. Retain data only within the existing debug retention policy. Do not preserve screenshots beyond that deadline merely because they were labelled.

Split by complete breaks/viewing sessions, and by creative when known. Neighboring frames and alternate edits of one ad must not be presented as independent test examples. Keep a final untouched set while adjusting descriptions, thresholds, and features. Report missed ads and falsely blocked program time, not just agreement with Samsung.

## L2: program profile lifecycle

Proposed progression: identify source → collect confirmed program examples → establish the profile → inspect departures → revalidate periodically. Identity comes from verified native context when available. Missing title, category, scheduled start, or channel names remain unknown with provenance; model guesses must be distinguished from metadata.

Use several examples of people, settings, graphics, logo positions, colors and scene transitions. A program is visually diverse, so a single screenshot is not its fingerprint. A visual departure is a reason to inspect, not proof of an ad.

Reset the active profile on a confirmed source/content change; do not carry ad-block state into a new channel. Native navigation counters alone have not reliably represented every observed channel switch, so identity/freshness validation needs additional evidence. If watching begins during an ad, wait for confirmed programming before learning the profile. Revalidate program return after a break and after prolonged uncertainty. No profile update from card-contaminated images or unconfirmed commercials.

## L3: commercial cues in context

Candidate evidence includes a suddenly prominent trademark/product; pharmaceutical brand plus medical disclaimer layout; purchase price, phone number or URL call to action; and full-screen brand-colored graphics replacing expected documentary imagery. Maintain a growing brand/ad-graphic catalog rather than assuming the catalog is complete or fixed.

Measure size, location, onset and co-occurrence. Sports sponsor graphics, news tickers, shopping segments, documentary product shots and program title cards are required counterexamples. Logo presence or bright/full-color imagery alone must not be treated as definitive ad evidence.

## L4–L6: efficient learning and deployment

Use fresh native signals first when their meaning and session binding are verified. Use inexpensive cue checks next, and the pretrained visual model for unresolved observations. Track a deliberate uncertain state rather than forcing every screenshot into ad or program. Compare these stages on the same samples and include channel changes and break endings.

Keep the pretrained encoder frozen initially. Improve descriptions, image framing and context, then evaluate a small classifier over frozen features using reviewed examples. Use Samsung positives as weak supervision; no-match results remain unlabelled. Review informative disagreements and novel cases rather than labelling many near-duplicate frames.

For TV deployment, omit the text encoder by calculating reference vectors in advance; retain only the image encoder and decision layer. Quantization and smaller-student training are later experiments, contingent on measured performance and supported TV operations. No downloadable weights or runtime speed claims are implied by this roadmap; the exact model license must also be respected before redistribution.

Promotion requires an explicit report of onset latency, false blocking, restoration delay, missed breaks, uncertainty, memory, and compute cost on relevant footage. A model that agrees with its own teacher on training frames has not passed validation. Existing fail-open behavior and independent TV playback must be preserved.

## Tracking and source layout

- `experiments/vision-lab/`: reusable lab code, tests, aggregate benchmark results and reproduction notes.
- `docs/LOCAL-LEARNING-ROADMAP.md`: this status/decision register; update it as work changes from planned to implemented to validated.
- Detailed frames, fingerprints, per-frame predictions, labels, tokens and device records stay in private retained storage. Public Git history contains source and aggregate results only.
- The live debug exporter currently expects the separate standalone TV debug producer's status/record schema. This research directory is not a standalone TV app installer. Root-level runtime documentation describes the earlier computer-assisted blocker.
