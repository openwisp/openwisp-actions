"""Verify maintained JSON and GraphQL files are parsed during QA."""

import subprocess
import sys
from pathlib import Path

import pytest

ENTRY_POINT = Path(__file__).resolve().parents[1] / "scripts/__main__.py"


@pytest.mark.parametrize(
    ("filename", "content"),
    [("config.json", '{"valid": }'), ("query.graphql", "query { field(")],
)
def test_rejects_invalid_source_file(tmp_path, filename, content):
    (tmp_path / filename).write_text(content)
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "source-formats", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert filename in result.stdout


def test_accepts_valid_source_files(tmp_path):
    (tmp_path / "config.json").write_text('{"valid": true}')
    (tmp_path / "query.graphql").write_text("query { viewer { login } }")
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "source-formats", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout
