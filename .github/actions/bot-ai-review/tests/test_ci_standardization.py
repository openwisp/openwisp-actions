"""Test the lightweight CI convention check against the trusted base tree."""

import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "reusable"))

from ci_standardization import check, main, tree  # noqa: E402


def test_finds_standard_files_in_base_tree():
    trees = {
        "base": {
            "tree": [
                {"path": "install-ci-deps.sh", "type": "blob"},
                {"path": ".github", "type": "tree", "sha": "github"},
            ]
        },
        "github": {"tree": [{"path": "workflows", "type": "tree", "sha": "workflows"}]},
        "workflows": {"tree": [{"path": "ci.yml", "type": "blob"}]},
    }
    with patch("ci_standardization.tree", side_effect=lambda repo, sha: trees[sha]):
        assert check("openwisp/repo", "base") == []


def test_reports_missing_files_without_guessing():
    with patch("ci_standardization.tree", return_value={"tree": []}):
        assert check("openwisp/repo", "base") == [
            ".github/workflows/ci.yml",
            "install-ci-deps.sh",
        ]


def test_tree_error_is_not_reported_as_missing_files():
    with patch(
        "ci_standardization.tree", side_effect=subprocess.CalledProcessError(1, "gh")
    ):
        try:
            check("openwisp/repo", "base")
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError("API failure must not be treated as missing files")


def test_does_not_accept_directories_as_files():
    root = {
        "tree": [
            {"path": "install-ci-deps.sh", "type": "tree"},
            {"path": ".github", "type": "blob"},
        ]
    }
    with patch("ci_standardization.tree", return_value=root):
        assert check("openwisp/repo", "base") == [
            ".github/workflows/ci.yml",
            "install-ci-deps.sh",
        ]


def test_workflow_checks_base_revision_and_passes_result_to_publisher():
    path = os.path.join(
        os.path.dirname(__file__), "../../../workflows/reusable-bot-ai-review.yml"
    )
    with open(path) as workflow:
        jobs = yaml.safe_load(workflow)["jobs"]
    gate = jobs["gate"]
    step = next(
        item for item in gate["steps"] if item.get("id") == "ci-standardization"
    )
    assert step["env"]["BASE_SHA"] == "${{ steps.coordinate.outputs.base_sha }}"
    assert "ci_standardization.py" in step["run"]
    assert (
        gate["outputs"]["ci_standard_status"]
        == "${{ steps.ci-standardization.outputs.status }}"
    )
    publish = next(
        item
        for item in jobs["publish"]["steps"]
        if item.get("name") == "Publish review"
    )
    assert (
        publish["env"]["CI_STANDARD_STATUS"]
        == "${{ needs.gate.outputs.ci_standard_status }}"
    )
    assert (
        publish["env"]["CI_STANDARD_MISSING"]
        == "${{ needs.gate.outputs.ci_standard_missing }}"
    )


def test_incomplete_tree_is_an_error():
    with patch(
        "ci_standardization.subprocess.check_output", return_value='{"truncated": true}'
    ):
        try:
            tree("openwisp/repo", "base")
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Incomplete GitHub trees must not be treated as complete"
            )


def test_api_failure_outputs_unknown_status(capsys):
    with tempfile.NamedTemporaryFile() as output, patch.dict(
        os.environ,
        {
            "REPOSITORY": "openwisp/repo",
            "BASE_SHA": "base",
            "GITHUB_OUTPUT": output.name,
        },
    ), patch(
        "ci_standardization.check", side_effect=subprocess.CalledProcessError(1, "gh")
    ):
        main()
        assert output.read().decode() == "status=unknown\nmissing=\n"
    assert "Could not check CI entry points" in capsys.readouterr().err
