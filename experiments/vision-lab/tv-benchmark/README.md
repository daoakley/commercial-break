# Target-TV MobileCLIP feasibility experiment

This is an isolated, bounded performance experiment, not a detector installer.
It does not capture the screen, send recognition requests, control the overlay,
change channels, or train a model. Synthetic input separates runtime feasibility
from commercial-recognition accuracy. See `RESULTS.md` for measured findings.

## Components

- `export_mobileclip.py`: export the frozen MobileCLIP2-S0 image encoder to ncnn,
  verify FP32 and FP16-stored weights against the original PyTorch model on three
  synthetic inputs, and record hashes and operator requirements.
- `export-verification.json`: aggregate synthetic verification; no viewing data.
- `bench.cpp`: single-process native inference timer with a 25-second alarm,
  20-second CPU soft limit, 192 MiB additional virtual-address-space cap, low
  scheduling priority, and output-vector correctness checks.
- `managed/`: .NET Core 3.1 host with an absolute native-library resolver, detailed
  loader errors, and a separate 30-second / 192 MiB RSS watchdog. These limits
  apply to the benchmark process, not to the active TV application.
- `stock-managed/`: probe Samsung's installed ncnn C API without loading a custom
  native library. No arguments inspects capability; `--graph-only <param>` tests
  graph parsing without weights/inference. The tested full MobileCLIP graph
  crashed this isolated probe; the tiny control passed. Read the results before
  repeating it. Modern API presence is not a guarantee of firmware ABI support.
- `Dockerfile.toolchain` and `build-arm.sh`: isolated ARMv7 softfp cross-build.
- `tv_command.py`: explicit command-file transport through an already authorized
  `samsung-tv-root` installation. It does not discover, reboot, or configure TVs.
  Raw command output must remain in private work storage.

The native build disables OpenMP and is single-threaded. Passing a larger thread
number does not make this particular build parallel; all reported tests use one.
The watchdog is a sampled guard, not an absolute instantaneous RSS ceiling.

## Reproduce the export and build

Obtain the official checkpoint under its upstream model license. The tested
checkpoint revision/hash and exact Python package versions are recorded in
`export-verification.json`. Use an isolated Python environment with those
versions; do not modify the collector's runtime. Python 3.11+ is required by the
export helper. No text encoder is included in the exported graph; prompt vectors
can be computed once on a development machine and stored separately.

```sh
python export_mobileclip.py --checkpoint /private/work/mobileclip2_s0.pt \
  --output /private/work/export

git clone https://github.com/Tencent/ncnn.git /private/work/ncnn
git -C /private/work/ncnn checkout 9fc8106e6634a60f39945d63e5ed2dd0704ac9fc
docker build -f Dockerfile.toolchain -t mobileclip-tv-toolchain .
docker run --rm --memory 2g --cpus 4 \
  -v /private/work:/work -v "$PWD":/benchsrc:ro \
  mobileclip-tv-toolchain sh /benchsrc/build-arm.sh \
  /work/ncnn /work/build /work/libmobileclip-bench.so
dotnet build managed/MobileClipBench.csproj -c Release -o /private/work/managed
```

The archived Debian toolchain is for cross-compilation only. The result links
libstdc++/libgcc statically while using the TV's glibc, libm and libdl. An ARM hard
float build is not interchangeable with this TV's softfp calling convention,
even though both can use NEON instructions. The host .NET SDK must be able to
target .NET Core 3.1; the TV uses its existing 3.1 runtime.

Only the DLL, `.deps.json`, `.runtimeconfig.json`, native library, ncnn graph and
weights, input tensor and reference tensor belong in a temporary test directory.
Do not deploy `.runtimeconfig.dev.json`, host caches, credentials or toolchains.
The six managed-host arguments are graph, weights, input, reference, measured
iteration count and thread count. Use three iterations and one thread initially.
Never install this experiment over the active blocker.

The tested firmware may reject unsigned native code even through a managed host.
Successful conversion or a host benchmark does not establish that the TV can load
the runtime. A failed load is a compatibility result, not an inference timing.
Leave system security policy unchanged; remove all temporary files after testing.

## Measurement boundaries

Measure model loading, first inference, subsequent inference and peak process RSS
separately. Loading happens once for a future resident worker, not once per frame.
Inference timing excludes capture, decoding, resize/crop, metadata retrieval,
decision policy and overlay latency. A numerical embedding match does not measure
ad accuracy. FP16-stored weights still use FP32 computation in this experiment;
the smaller file does not establish smaller working memory or faster execution.

Keep raw TV diagnostics, recordings, weights, proprietary libraries and binaries
outside Git. Publish source, synthetic checks and aggregate resource results only.
No NPU/GPU acceleration is claimed merely because related libraries exist.

Primary references: [Apple MobileCLIP](https://github.com/apple-aiml-research/ml-mobileclip),
[ncnn ARM build documentation](https://github.com/Tencent/ncnn/wiki/how-to-build),
and the upstream model's `LICENSE_MODELS` for weight usage/redistribution terms.
