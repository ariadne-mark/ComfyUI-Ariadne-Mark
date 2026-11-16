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

## Registry publishing

Use the manual **Publish Comfy Registry** workflow on `main`, with the exact
version from `pyproject.toml`. The workflow checks publisher/package identity and
qualified implementation hashes before accessing the publishing secret. All media
qualification stays on the project server. An implementation change requires new
qualification and updated source hashes before publishing a new immutable version.

The key is supplied to the official CLI through its hidden stdin prompt. Workflow
output is additionally redacted, and exit codes are preserved. Never pass a key
via `--token`, print it, or add it to a workflow example. The uploaded `node.zip`
and `REGISTRY_PACKAGE.json` are retained as run artifacts for 30 days; archive
release evidence in the project records before expiry.
