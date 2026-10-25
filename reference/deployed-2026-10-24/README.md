# Deployed detector reference

The owner container's `/app/server.py` SHA-256 was read directly at handoff and matched this file:
`fe955a6d4e86cb88969f099b1db1503a6aa3703f0e159f1674f5317b0a484f3f`.

The running image ID was `sha256:45c8fef36d017f40e4b957ebedafcd2ca0919de3225629f0f5df168ae8480a77`. It is a local image, not a published registry artifact. This directory preserves source, not private configuration or proprietary binaries. Its server implements sequential behavior and latest-frame caching; it has no native-event ingestion and retains the longer idle policy.

`CaptureProgram.cs` is the owner's rolled-back one-shot source, retained separately from the experimental root capture source. It is not a compiled or attested TV binary. Its Samsung API must be tested on the target firmware. Use the original capture csproj in a separate build directory to compile it as `Program.cs`.

Build the reference detector with `docker build -t commercial-break-reference:20261024 reference/deployed-2026-10-24` from repository root. That only builds an image. It does not configure, deploy, pair, or start anything. For live behavior and rollback rules see `docs/PROJECT_STATUS.md` and `docs/OPERATIONS.md`.
