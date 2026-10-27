# MobileCLIP on the 2022 Samsung Frame: feasibility results

Measured 26–27 October 2026 on a QN65LS03BAFXZA while video was playing.

**Outcome: the image-only model exports correctly, but this experiment did not
complete an inference on the TV. Runtime compatibility is the next gate. There
is no defensible on-TV latency or model working-memory number yet.**

## Verified device resources

| Item | Direct observation | Implication |
|---|---|---|
| Processor | Four logical ARM cores; ARMv7 userspace; NEON; softfp ABI | Build for this ABI, not generic ARM64 or ARM hard-float binaries |
| RAM | 1,825,688 KiB total, about 1.74 GiB | Most RAM is already used by the TV |
| Available RAM | Initially 277,764 KiB; later live readings varied, falling to 99,812 KiB after cleanup and recovering to 130,420 KiB on the next check | Memory headroom is variable; no allocation budget follows from total RAM alone |
| Swap | 912,660 KiB total; later check showed none free | Avoid assuming swap will absorb model allocations |
| Storage | About 7.1 GiB available on `/opt` at the hardware check | Weight-file storage is less constraining than active RAM |
| System | Linux 5.4.77, glibc 2.30, .NET Core 3.1 | A recent Linux ARM build is not automatically compatible |
| Native ML components | `libncnn.so`, NNStreamer and NPU-related libraries present | Presence does not prove usable acceleration or graph support |

A two-second `/proc/stat` baseline showed roughly 69% aggregate CPU busy during
the existing live workload. It is a short sample, not a sustained utilization
estimate. The reason for changing system memory headroom was not established;
these readings are not the model's RAM consumption.

## What ran and what failed

1. **Host export and correctness passed.** The frozen MobileCLIP2-S0 image tower
   contains 11,357,504 parameters. FP32 weights are 45,420,696 bytes (43.3 MiB);
   FP16-stored weights are 22,793,624 bytes (21.7 MiB). The text tower is omitted.
   FP16 storage still uses FP32 arithmetic in this test.
2. **Three synthetic export checks passed.** Against the original PyTorch image
   encoder, FP32 minimum cosine similarity was 0.9999999999957; FP16-stored
   minimum was 0.9997825. This verifies numerical conversion on those inputs,
   not ad-recognition quality. The attention graph was rewritten equivalently
   to avoid an unsupported five-dimensional intermediate; weights were unchanged.
3. **The custom native runtime could not load on the TV.** A static executable
   returned `Operation not permitted`. An ABI-correct ARMv7 softfp shared library
   through a separate managed host returned `failed to map segment from shared
   object`, both on the data partition and tmpfs with the tested file labels.
   No global policy, firmware, active application or blocker configuration was
   changed. The precise enforcement mechanism was not established.
4. **Samsung's installed ncnn library loaded.** Selected C APIs exist, but the
   modern options and operator-inspection APIs required by the general benchmark
   were missing. Missing introspection does not prove a particular operator is
   unsupported.
5. **The native control graph passed; the MobileCLIP graph failed.** A one-node
   Input control graph loaded successfully in 19.88 ms, with the managed probe
   using about 19.2 MiB RSS. The full MobileCLIP graph instead terminated its
   isolated helper with SIGSEGV before loading weights or attempting inference.
   The exact incompatibility remains unresolved. The control's 19.88 ms is a
   graph-parse measurement, **not MobileCLIP inference latency**.

The native helper had a 25-second alarm and CPU/address-space limits. Managed
helpers had a 30-second watchdog and sampled 192 MiB RSS guard. All test helpers
ended; the temporary TV directories, staged archives and staged library copy
were removed. The compiler container was stopped. Final status checks showed
the existing Samsung-only blocker enabled, no reported error, and recognition
query/match counts advancing. There was no new detector deployment.

Aggregate machine-readable evidence: [tv-results.json](tv-results.json) and
[export-verification.json](export-verification.json). Raw diagnostics remain
private. No TV libraries, recordings, credentials or model weights are included.

## Break the remaining work into separate decisions

| Work item | Smallest useful next step | Where it runs | Evidence needed before going further |
|---|---|---|---|
| Verified native context | Reuse source-bound app/channel/show/ad evidence with timestamps and provenance; leave unavailable fields unknown | Existing TV producer and lab | Freshness, channel-change and show-change checks |
| Human labels / evaluation (L1) | Mark ad start, program return and wrong blocks; reserve whole breaks/sessions | Lab UI / computer | Reviewed transition timing and independent program negatives |
| Program profiles (L2) | Several confirmed program embeddings per content session; reset/revalidate after a source change | Lab first; tiny comparison head can later run on TV | Fewer false blocks without missing transitions; no learning from ads or overlay frames |
| Specific ad cues (L3) | Test sponsor pills, product/brand prominence and disclaimer/call-to-action layouts against sports/news counterexamples | Local image preprocessing | Incremental gain on held-out material; measured TV preprocessing cost |
| Context plus vision (L4) | Keep the encoder frozen; compare full-frame images, verified metadata and combined decisions | Docker / development computer | Missed-break, false-block, onset and restoration metrics; no forced unknown-to-program labels |
| TV runtime and deployment (L5) | Resolve a compatible graph/runtime route, then run one numerically verified image inference | Isolated TV helper | Actual latency, peak RSS, sustained playback impact and predictable release on channel changes |
| Iteration (L6) | Preserve experiment versions and a final untouched test set within retention limits | Lab / GitHub aggregate reports | Regressions, independent evidence and explicit promotion decision |

The image encoder is the expensive part. For scale, twenty 512-element float32
program exemplars require only 40 KiB, and twenty-four precomputed prompt vectors
require 48 KiB, excluding container overhead. Such small comparison heads do not
remove the need to generate the image embedding.

**Recommended order:** continue native metadata and offline accuracy experiments,
but treat TV runtime compatibility as a short, separate feasibility milestone
before spending heavily on fine-tuning or distillation. Quantizing a weight file
does not by itself fix native code loading or graph incompatibility. If this
encoder cannot be hosted efficiently, benchmark a smaller network using verified
stock operators before training it. NPU access and alternative app packaging are
unverified possibilities, not promised fixes.

The earlier Mac CPU result (85.4 ms median) remains a host-only measurement. It
must not be advertised as TV speed or end-to-end commercial-blocking latency.
