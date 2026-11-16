"""Publication checks only; media qualification runs on the project server."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tomllib
import zipfile

root = Path.cwd()
meta = tomllib.loads((root / "pyproject.toml").read_text())
assert meta["project"]["name"] == "ariadne-mark-nodes"
assert meta["tool"]["comfy"]["PublisherId"] == "ariadne-mark"
assert meta["project"]["version"] == os.environ["PUBLISH_VERSION"]
qualified = json.loads((root / "qualification/source-hashes.json").read_text())
for name, digest in qualified.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name

if "--archive" in sys.argv:
    archive = root / "node.zip"
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        assert {"__init__.py", "nodes.py", "bridge.py", "pyproject.toml", "LICENSE", "requirements.txt"} <= names
        assert not any(n.startswith((".git/", ".github/", "tests/", "qualification/")) for n in names)
        assert not any(n.endswith((".local.json", ".pem", ".key", ".env")) for n in names)
        for name, digest in qualified.items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest, name
    record = {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "node_id": meta["project"]["name"],
        "publisher_id": meta["tool"]["comfy"]["PublisherId"],
        "version": meta["project"]["version"],
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "archive_bytes": archive.stat().st_size,
        "files": sorted(names),
        "qualified_core_source_sha256": qualified,
    }
    (root / "REGISTRY_PACKAGE.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
else:
    print("Publishing metadata and qualified source hashes agree")
