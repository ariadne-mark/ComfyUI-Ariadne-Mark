# Contributing

Describe a concrete workflow, ComfyUI/adapter/SDK versions and a reproducible
integration problem. Keep SDK algorithms and profile semantics in the SDK project;
this repository owns the Comfy export boundary, packaging and examples.

Run bridge tests in an isolated environment with `filelock`:

```sh
python -m unittest discover -s tests -v
```

Qualification for a release also needs the real Comfy queue and real SDK kit on
the qualified Linux runtime, download-to-receipt hash checks, and separate media
verification. Mock runner tests do not replace this. Server results for the first
release are recorded in `qualification/`.

Never add runtime package/model downloads, silent unmarked fallback, telemetry,
or signing credentials to node widgets/workflows.
