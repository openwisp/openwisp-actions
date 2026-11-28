"""Verify that restored APT archives match trusted package metadata."""

import hashlib
import importlib.util
import subprocess
import sys
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
    directory = staging / "directory_1.0_amd64.deb"
    epoch = staging / "epoch_1%3a1.0_all.deb"
    good.write_bytes(b"good")
    bad.write_bytes(b"evil")
    missing.write_bytes(b"data")
    symlink.symlink_to(good)
    directory.mkdir()
    epoch.write_bytes(b"good")
    digest = hashlib.sha256(b"good").hexdigest()

    def metadata(package, version, architecture):
        if package == "missing":
            return ""
        return (
            f"Package: {package}\nVersion: {version}\nArchitecture: {architecture}\n"
            f"Size: 4\nSHA256: {digest}\n"
        )

    monkeypatch.setattr(verifier, "package_metadata", metadata)
    verifier.verify_archives(staging, active)
    assert (active / good.name).read_bytes() == b"good"
    assert (active / epoch.name).read_bytes() == b"good"
    assert not (active / bad.name).exists()
    assert not (active / missing.name).exists()
    assert not bad.exists()
    assert not missing.exists()
    assert not symlink.is_symlink()
    assert not directory.exists()


def test_script_rejects_malformed_archives(tmp_path):
    staging = tmp_path / "staging"
    active = tmp_path / "active"
    staging.mkdir()
    active.mkdir()
    invalid = staging / "-invalid_1.0_amd64.deb"
    invalid.write_bytes(b"data")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(staging), str(active)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not invalid.exists()
    assert not list(active.iterdir())
