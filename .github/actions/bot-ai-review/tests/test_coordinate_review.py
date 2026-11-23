"""Test the workflow adapter for CI-aware review requests."""

import os
import sys
from unittest.mock import patch

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "reusable"))

from coordinate_review import prepare  # noqa: E402


def test_disabled_integration_runs_original_request_without_ci():
    request = {"stage": "review", "head_sha": "a" * 40, "comment_id": 10}
    with patch(
        "coordinate_review.GitHub", side_effect=AssertionError("unexpected API call")
    ):
        assert prepare(False, request, {}, "openwisp/repo", 1, 42) == request


def test_enabled_integration_delegates_to_serialized_coordinator():
    request = {"stage": "review", "head_sha": "a" * 40, "comment_id": 10}
    event = {"body": "/review"}
    with patch("coordinate_review.GitHub") as github, patch(
        "coordinate_review.coordinate", return_value={"stage": "review", "run_id": 7}
    ) as coordinate:
        result = prepare(True, request, event, "openwisp/repo", 1, 42)
    assert result["run_id"] == 7
    coordinate.assert_called_once_with(
        github.return_value, 42, "openwisp/repo", 1, request, None, None
    )


def test_internal_dispatch_is_not_treated_as_a_new_request():
    event = {"body": "/ai-review-resume 12"}
    with patch("coordinate_review.GitHub") as github, patch(
        "coordinate_review.coordinate", return_value={}
    ) as coordinate:
        assert prepare(True, {}, event, "openwisp/repo", 1, 42) == {}
    coordinate.assert_called_once_with(
        github.return_value, 42, "openwisp/repo", 1, {}, event, None
    )


def test_invalid_command_cannot_register_a_request():
    with patch(
        "coordinate_review.GitHub", side_effect=AssertionError("unexpected API call")
    ):
        assert (
            prepare(True, {"stage": ""}, {"body": "hello"}, "openwisp/repo", 1, 42)
            == {}
        )


def test_gate_serializes_registration_and_only_runs_approved_requests():
    path = os.path.join(
        os.path.dirname(__file__), "../../../workflows/reusable-bot-ai-review.yml"
    )
    with open(path) as workflow:
        jobs = yaml.safe_load(workflow)["jobs"]
    gate = jobs["gate"]
    assert gate["concurrency"]["queue"] == "max"
    assert gate["outputs"]["stage"] == "${{ steps.coordinate.outputs.stage }}"
    assert any(step.get("id") == "coordinate" for step in gate["steps"])


def test_completion_handler_only_runs_for_opted_in_primary_ci():
    path = os.path.join(
        os.path.dirname(__file__), "../../../workflows/reusable-bot-ai-review.yml"
    )
    with open(path) as workflow:
        jobs = yaml.safe_load(workflow)["jobs"]
    completion = jobs["ci-completion"]
    assert "inputs.wait_for_ci" in completion["if"]
    assert "github.event.workflow_run.path" in completion["if"]
    assert any(
        "ci_completion.py" in step.get("run", "") for step in completion["steps"]
    )


def test_request_state_key_is_only_passed_to_trusted_coordinator_steps():
    path = os.path.join(
        os.path.dirname(__file__), "../../../workflows/reusable-bot-ai-review.yml"
    )
    with open(path) as workflow:
        jobs = yaml.safe_load(workflow)["jobs"]
    steps = [
        (job, step["name"])
        for job, config in jobs.items()
        for step in config.get("steps", [])
        if "CI_STATE_KEY" in step.get("env", {})
    ]
    assert steps == [
        ("gate", "Coordinate review request"),
        ("finish-ci-request", "Finish request"),
        ("ci-completion", "Wake pending requests"),
    ]


def test_resume_dispatch_requires_bot_author_before_entering_the_gate():
    root = os.path.join(os.path.dirname(__file__), "../../../workflows")
    for name, job in (
        ("bot-ai-review.yml", "ai-review"),
        ("reusable-bot-ai-review.yml", "gate"),
    ):
        with open(os.path.join(root, name)) as workflow:
            condition = yaml.safe_load(workflow)["jobs"][job]["if"]
        assert "github.event.comment.user.type == 'Bot'" in condition
        assert (
            "startsWith(github.event.comment.body, '/ai-review-resume ')" in condition
        )
    with open(os.path.join(root, "reusable-bot-ai-review.yml")) as workflow:
        gate = yaml.safe_load(workflow)["jobs"]["gate"]
    for name in (
        "Generate read-only app token",
        "Generate CI coordinator token",
        "Coordinate review request",
    ):
        condition = next(
            step["if"] for step in gate["steps"] if step.get("name") == name
        )
        assert "github.event.comment.user.type == 'Bot'" in condition


def test_completion_trigger_matches_names_with_slashes():
    root = os.path.join(os.path.dirname(__file__), "../../../workflows")
    with open(os.path.join(root, "bot-ai-review.yml")) as workflow:
        config = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert config["on"]["workflow_run"]["workflows"] == ["**"]
