"""Verify that restored APT archives match trusted package metadata."""

import hashlib
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "verify.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("apt_verify", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_keeps_only_archives_matching_selected_package_metadata(tmp_path, monkeypatch):
    verifier = load_verifier()
    staging = tmp_path / "staging"
    active = tmp_path / "active"
    staging.mkdir()
    active.mkdir()
    good = staging / "sample_1.0_amd64.deb"
    bad = staging / "other_1.0_amd64.deb"
    missing = staging / "missing_1.0_amd64.deb"
    symlink = staging / "linked_1.0_amd64.deb"
    good.write_bytes(b"good")
    bad.write_bytes(b"evil")
    missing.write_bytes(b"data")
    symlink.symlink_to(good)
    digest = hashlib.sha256(b"good").hexdigest()

    def metadata(package):
        if package == "missing":
            return ""
        return f"Filename: pool/{package}_1.0_amd64.deb\nSize: 4\nSHA256: {digest}\n"

    monkeypatch.setattr(verifier, "package_metadata", metadata)
    verifier.verify_archives(staging, active)
    assert (active / good.name).read_bytes() == b"good"
    assert not (active / bad.name).exists()
    assert not (active / missing.name).exists()
    assert not bad.exists()
    assert not missing.exists()
    assert not symlink.is_symlink()
