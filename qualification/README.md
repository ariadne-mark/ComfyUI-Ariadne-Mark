# Server qualification · 16 November 2026

ComfyUI 0.45.0 (`989d93d0d968e704c589ce0146bb18c77f6b50cc`), Linux x86-64 CPU; exact SDK 0.7.3a4 image recorded in `validation.json`.

- 10 bridge tests passed, including partial batch failure, wrong receipt, private-path protection and process-group termination on timeout.
- 10 real Comfy queue cases met their expected outcomes: seven successful workflows (eight files) and three expected failures.
- All three video profiles were exported through the visual watermark SDK.
- Every file fetched through Comfy's `/view` matched its SDK receipt hash.
- A separate SDK process recovered each expected watermark ID and validated its development C2PA signature without receiving an expected ID.

Fixtures were deterministic procedural inputs; no generation model weights were loaded. This is a functional integration test, not a production-identity qualification or a throughput benchmark. Node execution includes SDK startup; it does not inherit resident-worker timing claims.

The first independent-verification harness used a container UID that could not read the owner-private output folder. It was corrected to use the file owner's UID, then resumed from the same exported artifacts; permissions were not widened and media were not regenerated.

Registry publishing is not part of this report. Public listing requires an authenticated publisher account and Registry acceptance.

The supplied image UI workflow was also imported and run through the real browser interface: job completed with a native saved-image preview. `source-hashes.json` identifies the exact server-qualified node implementation.

A final packaging invocation used pytest without Comfy on its import path and failed collection before running tests. The documented unittest command was then repeated successfully (10/10). Native Comfy registration and actual queue/UI execution passed independently.
