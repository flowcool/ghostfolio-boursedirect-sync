"""Offline publication guards. These do not establish registry or lab proof."""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("bd_promotion", ROOT / "scripts/promote_release_image.py")
promotion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promotion)

COMMIT = "a" * 40
NATIVE = {"amd64": "sha256:" + "b" * 64, "arm64": "sha256:" + "c" * 64}
RAW = json.dumps({"manifests": [
    {"platform": {"os": "linux", "architecture": arch}, "digest": digest}
    for arch, digest in NATIVE.items()]}).encode()
DIGEST = "sha256:" + hashlib.sha256(RAW).hexdigest()


def record():
    return {"schema": 1, "repository": "o/r", "tag": "v1.0.0", "commit": COMMIT,
            "digest": DIGEST, "native": dict(NATIVE), "labs": {
                name: {"status": "PASS", "cleanup": "stopped", "evidence_sha256": "d" * 64}
                for name in ("empty", "golden")}}


def test_qualified_stable_needs_no_rc():
    assert promotion.qualification(record(), "o/r", "v1.0.0", COMMIT) == record()


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(schema=True),
    lambda r: r.update(commit="f" * 40),
    lambda r: r.update(repository="wrong/repo"),
    lambda r: r.update(tag="v1.0.1"),
    lambda r: r.update(digest="bad"),
    lambda r: r["native"].pop("arm64"),
    lambda r: r["native"].update(arm64=r["native"]["amd64"]),
    lambda r: r["labs"].pop("golden"),
    lambda r: r["labs"]["empty"].update(status="pending"),
    lambda r: r["labs"]["golden"].update(cleanup="running"),
    lambda r: r["labs"]["golden"].update(evidence_sha256="bad"),
])
def test_incomplete_or_changed_qualification_refuses(mutation):
    value = record()
    mutation(value)
    with pytest.raises(RuntimeError):
        promotion.qualification(value, "o/r", "v1.0.0", COMMIT)


def test_duplicate_qualification_keys_refuse():
    with pytest.raises(RuntimeError, match="Duplicate"):
        json.loads('{"schema":1,"schema":1}', object_pairs_hook=promotion.unique_object)


@pytest.mark.parametrize("failure", [None, "signature", "digest", "identity", "qualification", "version_readback"])
def test_exact_promotion_or_stop_without_retry(monkeypatch, tmp_path, failure):
    monkeypatch.chdir(tmp_path)
    selected = ("v1.0.0", "1.0.0", record())
    calls = []
    reads = []

    def output(*args):
        reads.append(args)
        if args[0] == "gh":
            return b"v1.0.0\n"
        if "--raw" in args:
            if (failure == "digest" and "@" in args[-1]
                    or failure == "version_readback" and args[-1].endswith(":1.0.0")):
                return b"{}"
            return RAW
        arch = next(a for a, d in NATIVE.items() if args[-1].endswith(d))
        return json.dumps({"architecture": arch, "os": "linux", "config": {
            "Labels": {"org.opencontainers.image.source": "https://github.com/o/r",
                       "org.opencontainers.image.version": "1.0.0",
                       "org.opencontainers.image.revision": COMMIT},
            "Env": ["APP_VERSION=1.0.0", "APP_REVISION=" + ("f" * 40 if failure == "identity" else COMMIT)]}}).encode()

    def run(command, **kwargs):
        calls.append(command)
        if failure == "signature" and command[:2] == ["cosign", "verify"]:
            raise RuntimeError("signature refused")

    monkeypatch.setattr(promotion, "output", output)
    monkeypatch.setattr(promotion.subprocess, "run", run)
    changed = copy.deepcopy(selected)
    changed[2]["labs"]["empty"]["evidence_sha256"] = "e" * 64
    monkeypatch.setattr(promotion, "plan", lambda: changed if failure == "qualification" else selected)
    progress = {"publication_attempted": False}
    if failure:
        with pytest.raises(RuntimeError):
            promotion.promote(selected, progress)
    else:
        promotion.promote(selected, progress)
        assert Path("release-manifest.json").read_bytes() == RAW
        assert Path("release-manifest-digest.txt").read_text() == DIGEST
        assert any(args[-1] == "ghcr.io/o/r:latest" for args in reads)
    writes = [c for c in calls if c[:4] == ["docker", "buildx", "imagetools", "create"]]
    assert len(writes) == (2 if failure is None else 1 if failure == "version_readback" else 0)
    assert all(c[-1] == "ghcr.io/o/r@" + DIGEST for c in writes)
    assert all("build" not in c for c in calls)
