"""Test selection of a single existing CI matrix row for review."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "reusable" / "select_matrix.py"


def select(matrix, override=None):
    command = [sys.executable, str(SCRIPT)]
    if override is not None:
        command.append(json.dumps(override))
    return subprocess.run(
        command,
        input=json.dumps(matrix),
        capture_output=True,
        text=True,
        check=False,
    )


def test_selects_marked_row_from_matrix():
    matrix = {
        "python": ["3.12", "3.13"],
        "django": ["5.2", "6.0"],
        "exclude": [{"python": "3.12", "django": "6.0"}],
        "include": [{"python": "3.13", "django": "6.0", "review_default": True}],
    }
    result = select(matrix)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "python": "3.13",
        "django": "6.0",
        "review_default": True,
    }


def test_rejects_missing_or_multiple_default_rows():
    for matrix in (
        {"python": ["3.12"]},
        {"python": ["3.12", "3.13"], "include": [{"review_default": True}]},
    ):
        result = select(matrix)
        assert result.returncode != 0
        assert "exactly one" in result.stderr


def test_override_selects_existing_row_but_not_excluded_row():
    matrix = {
        "python": ["3.12", "3.13"],
        "django": ["5.2", "6.0"],
        "exclude": [{"python": "3.12", "django": "6.0"}],
        "include": [{"python": "3.13", "django": "6.0", "review_default": True}],
    }
    result = select(matrix, {"python": "3.12", "django": "5.2"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"python": "3.12", "django": "5.2"}
    result = select(matrix, {"python": "3.12", "django": "6.0"})
    assert result.returncode != 0
    assert "valid matrix row" in result.stderr


def test_ambiguous_override_is_rejected():
    matrix = {
        "python": ["3.12", "3.13"],
        "django": ["5.2", "6.0"],
        "include": [{"python": "3.13", "django": "6.0", "review_default": True}],
    }
    result = select(matrix, {"python": "3.12"})
    assert result.returncode != 0
    assert "exactly one" in result.stderr


def test_include_can_add_a_distinct_row():
    matrix = {
        "python": ["3.12"],
        "include": [{"python": "3.13", "review_default": True}],
    }
    result = select(matrix)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["python"] == "3.13"


def test_include_only_matrix_preserves_separate_rows():
    matrix = {
        "include": [
            {"python": "3.12"},
            {"python": "3.13", "review_default": True},
        ]
    }
    result = select(matrix, {"python": "3.12"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"python": "3.12"}
