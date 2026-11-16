"""Pass the Registry key to the official CLI through stdin, never argv/files."""
import os
import subprocess
import sys

key = os.environ.pop("REGISTRY_ACCESS_TOKEN", "")
if not key.startswith("pat-") or "\n" in key or "\r" in key:
    raise SystemExit("A valid REGISTRY_ACCESS_TOKEN repository secret is required")

try:
    result = subprocess.run(
        ["comfy", "--skip-prompt", "--no-enable-telemetry", "node", "publish"],
        input=(key + "\n").encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=600,
        check=False,
    )
except subprocess.TimeoutExpired:
    raise SystemExit("Registry publication timed out; inspect Registry status before retrying") from None

# Also redact an unexpected API error echo before releasing captured CLI output.
output = result.stdout.decode("utf-8", errors="replace").replace(key, "[REDACTED]")
key = ""
sys.stdout.write(output)
raise SystemExit(result.returncode)
